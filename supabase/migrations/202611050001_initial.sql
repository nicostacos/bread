-- Bread Bot schema. Runtime API access is service-role only.
create schema if not exists bread_private;
revoke all on schema bread_private from public, anon, authenticated;
create table bread_private.source_documents (
 source_collection text not null, source_id text not null, document text not null,
 primary key(source_collection,source_id)
);
create table public.guild_settings (
 guild_id text primary key check(guild_id ~ '^[0-9]+$'), active boolean not null default true,
 log_channel text, welcome_channel text, automod_rule_id text
);
create table public.guild_filter_settings (
 guild_id text primary key references public.guild_settings, enabled boolean not null default true,
 updated_at timestamptz
);
create table public.filter_words (
 guild_id text references public.guild_settings, word text not null check(length(word)>0),
 primary key(guild_id,word)
);
create table public.warnings (
 id uuid primary key default gen_random_uuid(), source_id text unique,
 guild_id text not null references public.guild_settings, user_id text not null, moderator_id text not null,
 reason text not null, evidence text not null default '', created_at timestamptz default now(),
 warning_number integer not null check(warning_number>0), legacy_warning_number integer,
 escalation text check(escalation in ('kick','ban')),
 unique(guild_id,user_id,warning_number)
);
create table public.moderation_cases (
 id uuid primary key default gen_random_uuid(), source_id text unique,
 guild_id text not null references public.guild_settings, user_id text not null, moderator_id text not null,
 reason text not null, evidence text not null default '', action text not null, duration text not null default '',
 outcome text not null default 'succeeded', created_at timestamptz default now()
);
create table public.scheduled_invites (
 id uuid primary key default gen_random_uuid(), source_id text unique,
 guild_id text not null references public.guild_settings, user_id text not null, reason text not null default '',
 created_at timestamptz default now(), send_at timestamptz not null,
 status text not null default 'pending' check(status in ('pending','processing','sent','failed','suspended')),
 attempts int not null default 0, lease_token uuid, lease_until timestamptz, invite_url text, last_error text
);
create table public.guild_blacklist_entries (
 guild_id text references public.guild_settings, user_id text not null, primary key(guild_id,user_id)
);
create index on public.warnings(guild_id,user_id,created_at);
create index on public.moderation_cases(guild_id,user_id,created_at);
create index on public.scheduled_invites(status,send_at);

do $$ declare t text; begin
 foreach t in array array['guild_settings','guild_filter_settings','filter_words','warnings','moderation_cases','scheduled_invites','guild_blacklist_entries'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public, anon, authenticated',t);
  execute format('grant select, insert, update, delete on public.%I to service_role',t);
 end loop;
end $$;

create function public.bread_add_warning(p_guild text,p_user text,p_moderator text,p_reason text,p_evidence text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare n int; result jsonb;
begin
 perform pg_advisory_xact_lock(hashtextextended('warning:'||p_guild||':'||p_user,0));
 insert into public.guild_settings(guild_id) values(p_guild) on conflict do nothing;
 select coalesce(max(warning_number),0)+1 into n from public.warnings where guild_id=p_guild and user_id=p_user;
 insert into public.warnings(guild_id,user_id,moderator_id,reason,evidence,warning_number,escalation)
 values(p_guild,p_user,p_moderator,p_reason,p_evidence,n,case n when 3 then 'kick' when 4 then 'ban' else null end)
 returning to_jsonb(warnings.*) into result;
 return result;
end $$;

create function public.bread_mutate_filter(p_guild text,p_action text,p_word text,p_defaults jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare result jsonb; initialized boolean;
begin
 perform pg_advisory_xact_lock(hashtextextended('filter:'||p_guild,0));
 insert into public.guild_settings(guild_id) values(p_guild) on conflict do nothing;
 initialized := exists(select 1 from public.guild_filter_settings where guild_id=p_guild);
 insert into public.guild_filter_settings(guild_id) values(p_guild) on conflict do nothing;
 if not initialized or p_action='reset' then
  if p_action='reset' then delete from public.filter_words where guild_id=p_guild; end if;
  insert into public.filter_words(guild_id,word) select p_guild,lower(trim(value)) from jsonb_array_elements_text(p_defaults) on conflict do nothing;
 end if;
 if p_action='add' then
  if p_word is null or length(trim(p_word))=0 then raise exception 'A word is required'; end if;
  insert into public.filter_words(guild_id,word) values(p_guild,lower(trim(p_word))) on conflict do nothing;
 elsif p_action='remove' then delete from public.filter_words where guild_id=p_guild and word=lower(trim(p_word));
 elsif p_action='enable' or p_action='reset' then update public.guild_filter_settings set enabled=true where guild_id=p_guild;
 elsif p_action='disable' then update public.guild_filter_settings set enabled=false where guild_id=p_guild;
 elsif p_action<>'status' then raise exception 'Unknown filter operation'; end if;
 update public.guild_filter_settings set updated_at=now() where guild_id=p_guild and p_action<>'status';
 select jsonb_build_object('enabled',s.enabled,'words',coalesce((select jsonb_agg(word order by word) from public.filter_words where guild_id=p_guild),'[]'::jsonb)) into result
 from public.guild_filter_settings s where guild_id=p_guild;
 return result;
end $$;

create function public.bread_claim_invites(p_limit int default 25)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare result jsonb;
begin
 update public.scheduled_invites set status='failed',lease_token=null,lease_until=null
 where attempts>=5 and (status='pending' or (status='processing' and lease_until<now()));
 with candidates as (
  select j.id from public.scheduled_invites j join public.guild_settings g using(guild_id)
  where g.active and j.attempts<5 and j.send_at<=now() and
   (j.status='pending' or (j.status='processing' and j.lease_until<now()))
  order by j.send_at for update of j skip locked limit greatest(1,least(p_limit,100))
 ), claimed as (
  update public.scheduled_invites j set status='processing',attempts=attempts+1,
   lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes'
  from candidates c where j.id=c.id returning j.*
 ) select coalesce(jsonb_agg(to_jsonb(claimed.*)),'[]'::jsonb) into result from claimed;
 return result;
end $$;

create function public.bread_finish_invite(p_id uuid,p_lease uuid,p_action text,p_value text default null)
returns boolean language plpgsql security invoker set search_path='' as $$
declare changed int;
begin
 if p_action='url' then
  update public.scheduled_invites set invite_url=p_value where id=p_id and lease_token=p_lease and status='processing' and lease_until>now();
 elsif p_action='sent' then
  update public.scheduled_invites set status='sent',lease_until=null,lease_token=null where id=p_id and lease_token=p_lease and status='processing' and lease_until>now();
 elsif p_action='fail' then
  update public.scheduled_invites set status=case when attempts>=5 then 'failed' else 'pending' end,
   send_at=now()+make_interval(secs=>least(3600,60*power(2,attempts)::int)),
   last_error=p_value,lease_until=null,lease_token=null
  where id=p_id and lease_token=p_lease and status='processing' and lease_until>now();
 else raise exception 'Unknown job operation'; end if;
 get diagnostics changed=row_count;
 return changed=1;
end $$;

create function public.bread_deactivate_guild(p_guild text)
returns void language plpgsql security invoker set search_path='' as $$
begin
 update public.guild_settings set active=false where guild_id=p_guild;
 update public.scheduled_invites set status='suspended',lease_token=null,lease_until=null where guild_id=p_guild and status in ('pending','processing');
end $$;

revoke all on function public.bread_add_warning(text,text,text,text,text),
 public.bread_mutate_filter(text,text,text,jsonb),public.bread_claim_invites(int),
 public.bread_finish_invite(uuid,uuid,text,text),public.bread_deactivate_guild(text) from public,anon,authenticated;
grant execute on function public.bread_add_warning(text,text,text,text,text),
 public.bread_mutate_filter(text,text,text,jsonb),public.bread_claim_invites(int),
 public.bread_finish_invite(uuid,uuid,text,text),public.bread_deactivate_guild(text) to service_role;
