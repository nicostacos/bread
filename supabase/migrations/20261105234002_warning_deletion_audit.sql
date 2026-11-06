alter table public.warnings add column deleted_at timestamptz,
 add column deleted_by text;

create function public.bread_delete_warning(p_guild text,p_id uuid,p_actor text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare result jsonb;
begin
 update public.warnings set deleted_at=now(),deleted_by=p_actor
 where id=p_id and guild_id=p_guild and deleted_at is null returning to_jsonb(warnings.*) into result;
 if result is not null then
  insert into public.moderation_cases(guild_id,user_id,moderator_id,action,reason,evidence,outcome)
  values(p_guild,result->>'user_id',p_actor,'warning_deleted','Removed warning '||p_id::text,'','succeeded');
 end if;
 return result;
end $$;
revoke all on function public.bread_delete_warning(text,uuid,text) from public,anon,authenticated;
grant execute on function public.bread_delete_warning(text,uuid,text) to service_role;

-- Historical display numbers remain stable. Deleted warnings do not count toward
-- escalation; each escalation action is issued at most once per member history.
create or replace function public.bread_add_warning(p_guild text,p_user text,p_moderator text,p_reason text,p_evidence text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare n int; active_count int; action text; result jsonb;
begin
 perform pg_advisory_xact_lock(hashtextextended('warning:'||p_guild||':'||p_user,0));
 insert into public.guild_settings(guild_id) values(p_guild) on conflict do nothing;
 select coalesce(max(warning_number),0)+1,count(*) filter(where deleted_at is null)+1
 into n,active_count from public.warnings where guild_id=p_guild and user_id=p_user;
 action := case active_count when 3 then 'kick' when 4 then 'ban' else null end;
 if exists(select 1 from public.warnings where guild_id=p_guild and user_id=p_user and escalation=action) then action:=null; end if;
 insert into public.warnings(guild_id,user_id,moderator_id,reason,evidence,warning_number,escalation)
 values(p_guild,p_user,p_moderator,p_reason,p_evidence,n,action)
 returning to_jsonb(warnings.*) into result;
 return result;
end $$;
