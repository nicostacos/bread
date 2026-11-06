-- Run after the migration text inside one transaction, then roll back everything.
do $$
declare r jsonb; a jsonb; b jsonb;
begin
 if has_table_privilege('anon','public.warnings','SELECT') then raise exception 'Anonymous data exposure'; end if;
 if has_function_privilege('authenticated','public.bread_add_warning(text,text,text,text,text)','EXECUTE') then raise exception 'Public RPC execution'; end if;
 insert into public.guild_settings(guild_id) values ('18446744073709551001');
 r := public.bread_add_warning('18446744073709551001','123','456','reason','evidence');
 if (r->>'warning_number')::int <> 1 or r->>'escalation' is not null then raise exception 'First warning incorrect'; end if;
 perform public.bread_add_warning('18446744073709551001','123','456','reason','');
 r := public.bread_add_warning('18446744073709551001','123','456','reason','');
 if r->>'escalation' <> 'kick' then raise exception 'Kick escalation missing'; end if;
 r := public.bread_add_warning('18446744073709551001','123','456','reason','');
 if r->>'escalation' <> 'ban' then raise exception 'Ban escalation missing'; end if;
 r := public.bread_add_warning('18446744073709551001','123','456','reason','');
 if r->>'escalation' is not null then raise exception 'Escalation repeated'; end if;
 perform public.bread_mutate_filter('18446744073709551001','add','alpha','[]');
 perform public.bread_mutate_filter('18446744073709551001','add','beta','[]');
 r := public.bread_mutate_filter('18446744073709551001','status',null,'[]');
 if jsonb_array_length(r->'words') <> 2 then raise exception 'Filter lost word'; end if;
 insert into public.scheduled_invites(guild_id,user_id,send_at) values ('18446744073709551001','123',now()-interval '1 minute');
 a := public.bread_claim_invites(10); b := public.bread_claim_invites(10);
 if jsonb_array_length(a) <> 1 or jsonb_array_length(b) <> 0 then raise exception 'Job claimed twice'; end if;
 perform public.bread_deactivate_guild('18446744073709551001');
 if (select count(*) from public.warnings where guild_id='18446744073709551001') <> 5 then raise exception 'History deleted'; end if;
 if exists(select 1 from public.scheduled_invites where guild_id='18446744073709551001' and status <> 'suspended') then raise exception 'Jobs not suspended'; end if;
end $$;

do $$
declare id uuid; r jsonb; n int;
begin
 select warnings.id into id from public.warnings where guild_id='18446744073709551001' and warning_number=1;
 r:=public.bread_delete_warning('999',id,'456');
 if r is not null then raise exception 'Cross-server deletion'; end if;
 r:=public.bread_delete_warning('18446744073709551001',id,'456');
 if r->>'deleted_by'<>'456' then raise exception 'Missing deletion moderator'; end if;
 if public.bread_delete_warning('18446744073709551001',id,'456') is not null then raise exception 'Repeated deletion'; end if;
 select count(*) into n from public.moderation_cases where guild_id='18446744073709551001' and action='warning_deleted';
 if n<>1 then raise exception 'Deletion audit count incorrect'; end if;
 if has_function_privilege('anon','public.bread_delete_warning(text,uuid,text)','EXECUTE') then raise exception 'Deletion RPC public'; end if;
 select count(*) into n from public.warnings where guild_id='18446744073709551001' and deleted_at is null;
 if n<>4 then raise exception 'Deleted warning still active'; end if;
end $$;
