"""Private, lossless MongoDB exports. Never imports runtime bot configuration."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from bson import json_util
from dotenv import load_dotenv
from pymongo import MongoClient

COLLECTIONS = ('server_configs', 'word_filters', 'moderation_warnings',
               'moderation_cases', 'scheduled_invites', 'guild_blacklists', 'automod_rule_ids')


def write_snapshot(source, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'collections': {}}
    for name in COLLECTIONS:
        docs = source.get(name, [])
        payload = json_util.dumps(docs, json_options=json_util.CANONICAL_JSON_OPTIONS).encode('utf-8')
        with (folder / (name + '.json')).open('xb') as stream:
            stream.write(payload)
        manifest['collections'][name] = {'count': len(docs), 'sha256': hashlib.sha256(payload).hexdigest()}
    with (folder/'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2)
    return manifest


def read_snapshot(folder):
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    result = {}
    for name in COLLECTIONS:
        payload = (folder/(name+'.json')).read_bytes()
        expected = manifest['collections'][name]
        if hashlib.sha256(payload).hexdigest() != expected['sha256']:
            raise ValueError('Snapshot hash mismatch: ' + name)
        docs = json_util.loads(payload, json_options=json_util.CANONICAL_JSON_OPTIONS)
        if len(docs) != expected['count']:
            raise ValueError('Snapshot count mismatch: ' + name)
        result[name] = docs
    return result


def export_mongo(folder):
    load_dotenv(Path(__file__).resolve().parents[1]/'.env')
    if os.getenv('MONGO_URI'):
        uri = os.environ['MONGO_URI']
    else:
        required = ('MONGO_USER', 'MONGO_PASS', 'MONGO_HOST', 'MONGO_DB')
        if not all(os.getenv(key) for key in required):
            raise ValueError('Mongo export settings are incomplete')
        uri = 'mongodb+srv://{}:{}@{}/{}?retryWrites=true&w=majority'.format(
            quote_plus(os.environ['MONGO_USER']), quote_plus(os.environ['MONGO_PASS']),
            os.environ['MONGO_HOST'], quote_plus(os.environ['MONGO_DB']))
    with MongoClient(uri, serverSelectionTimeoutMS=10000, socketTimeoutMS=15000) as client:
        db = client[os.environ['MONGO_DB']]
        # The deployed writer must remain stopped throughout this export.
        source = {name: list(db[name].find({})) for name in COLLECTIONS}
    manifest = write_snapshot(source, folder)
    read_snapshot(folder)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    manifest = export_mongo(args.output)
    print(json.dumps({name: info['count'] for name, info in manifest['collections'].items()}))
