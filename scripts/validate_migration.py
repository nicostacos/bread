import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from scripts.migrate_supabase import normalize,TABLES
from scripts.mongo_snapshot import read_snapshot
from scripts.supabase_cli import query


def canonical(value,key):
    if key in ('created_at','updated_at','send_at') and value is not None:
        return datetime.fromisoformat(value.replace('Z','+00:00')).isoformat()
    return value


def compare_rows(expected,actual):
    for table,records in expected.items():
        keys=TABLES[table]
        index={tuple(row.get(key) for key in keys):row for row in actual.get(table,[])}
        if len(index)!=len(records):raise ValueError('Row count mismatch: '+table)
        for record in records:
            row=index.get(tuple(record.get(key) for key in keys))
            if row is None:raise ValueError('Missing imported row: '+table)
            for key,value in record.items():
                if canonical(row.get(key),key)!=canonical(value,key):raise ValueError('Field mismatch: '+table+'.'+key)


def validate(folder):
    expected=normalize(read_snapshot(folder))
    # Aggregate to one returned row so CLI/API result limits cannot truncate records.
    sql='select jsonb_build_object('+','.join("'"+table+"',coalesce((select jsonb_agg(to_jsonb(t)) from "+
        ('bread_private.source_documents' if table=='raw_documents' else 'public.'+table)+" t),'[]'::jsonb)" for table in TABLES)+') as data;'
    response=query(sql,read_only=True)
    actual=response[0]['data']
    compare_rows(expected,actual)
    report={'verified':True,'project':'stzbjhimxmzpvmrbnlxg','snapshot':str(folder),
            'counts':{table:len(records) for table,records in actual.items()},
            'manifest_sha256':hashlib.sha256((Path(folder)/'manifest.json').read_bytes()).hexdigest()}
    (Path(folder)/'validation-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('snapshot',type=Path)
    print(json.dumps(validate(parser.parse_args().snapshot)))
