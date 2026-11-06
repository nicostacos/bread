"""Authenticated SQL transport. Data payloads and CLI responses stay private."""
import json
import subprocess
from pathlib import Path

PROJECT='stzbjhimxmzpvmrbnlxg'
ROOT=Path(__file__).resolve().parents[1]


def query(sql,read_only=False):
    linked=(ROOT/'supabase/.temp/project-ref').read_text().strip()
    if linked!=PROJECT:raise RuntimeError('Unexpected linked Supabase project')
    folder=ROOT/'backups';folder.mkdir(exist_ok=True)
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w',suffix='.sql',dir=folder,delete=False,encoding='utf-8') as f:
        f.write(sql);path=Path(f.name)
    args=['npx.cmd','--yes','supabase','db','query','--remote='+PROJECT,'--file',str(path)]
    args.append('--read-only' if read_only else '--yes')
    try:
        result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        if result.returncode:raise RuntimeError('Supabase SQL command failed; inspect schema/data locally without exposing private records')
        data=json.loads(result.stdout)
        if not isinstance(data,dict) or 'rows' not in data:raise RuntimeError('Unexpected SQL response shape')
        return data['rows']
    finally:path.unlink(missing_ok=True)
