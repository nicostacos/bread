"""Exercise SQL in isolated temporary schemas; never reset the imported project."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from scripts.supabase_cli import query,ROOT

SCHEMA='bread_verify_20261105'
PRIVATE='bread_verify_private_20261105'


def main():
    migration='\n'.join(p.read_text() for p in sorted((ROOT/'supabase/migrations').glob('*.sql')))
    migration=migration.replace('bread_private',PRIVATE).replace('public.',SCHEMA+'.')
    checks=(ROOT/'tests/integration/schema_checks.sql').read_text().replace('public.',SCHEMA+'.')
    # Do not delete an existing schema left by another run; investigate it first.
    setup='create schema '+SCHEMA+';grant usage on schema '+SCHEMA+' to service_role;\n'+migration
    query('begin;\n'+setup+'\n'+checks+'\nrollback;')
    query('begin;\n'+setup+'\ncommit;')
    try:
        def warn(_):
            return query(f"select {SCHEMA}.bread_add_warning('123','456','789','integration test','') as value;")[0]['value']
        with ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(warn,range(6)))
        assert sorted(row['warning_number'] for row in rows)==[1,2,3,4,5,6]
        assert sorted(row['escalation'] for row in rows if row['escalation'])==['ban','kick']
        def add(word):query(f"select {SCHEMA}.bread_mutate_filter('123','add','{word}','[]');")
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(add,['alpha','beta']))
        result=query(f"select {SCHEMA}.bread_mutate_filter('123','status',null,'[]') as value;")[0]['value']
        assert result['words']==['alpha','beta']
        query(f"insert into {SCHEMA}.scheduled_invites(guild_id,user_id,send_at) select '123',n::text,now()-interval '1 minute' from generate_series(1,4) n;")
        def claim(_):return query(f'select {SCHEMA}.bread_claim_invites(2) as value;')[0]['value']
        with ThreadPoolExecutor(max_workers=2) as pool:claimed=list(pool.map(claim,range(2)))
        ids=[row['id'] for batch in claimed for row in batch]
        assert len(ids)==4 and len(set(ids))==4
        job=claimed[0][0]
        stale=query(f"select {SCHEMA}.bread_finish_invite('{job['id']}','00000000-0000-0000-0000-000000000000','sent',null) as value;")[0]['value']
        assert stale is False
        query(f"update {SCHEMA}.scheduled_invites set attempts=5,lease_until=now()-interval '1 minute'; select {SCHEMA}.bread_claim_invites(10);")
        failed=query(f"select count(*)::int as count from {SCHEMA}.scheduled_invites where status='failed';")[0]['count']
        assert failed==4
        print('SQL checks passed: privileges, warnings, filter concurrency, job concurrency, stale leases, exhausted retries, history retention')
    finally:
        # Fixed test-only names; never target public or bread_private.
        query('drop schema '+SCHEMA+' cascade;drop schema '+PRIVATE+' cascade;')


if __name__=='__main__':main()
