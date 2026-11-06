"""Strict, deterministic normalization; SQL execution added by migration runner."""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5
from bson import json_util

TABLES={'guild_settings':('guild_id',),'guild_filter_settings':('guild_id',),
        'filter_words':('guild_id','word'),'warnings':('id',),'moderation_cases':('id',),
        'scheduled_invites':('id',),'guild_blacklist_entries':('guild_id','user_id'),
        'raw_documents':('source_collection','source_id')}


def snowflake(value, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, bool) or not str(value).isdigit() or not 0 < int(value) < 2**64:
        raise ValueError('Invalid Discord ID')
    return str(int(value))


def date(value, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, datetime):
        raise ValueError('Expected BSON datetime')
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()


def identity(collection, doc):
    if '_id' not in doc:
        raise ValueError('Source document missing ID')
    return str(uuid5(NAMESPACE_URL, 'bread-bot/'+collection+'/'+str(doc['_id'])))


def normalize(source):
    rows = {name: [] for name in ('guild_settings', 'guild_filter_settings', 'filter_words',
                                  'warnings', 'moderation_cases', 'scheduled_invites',
                                  'guild_blacklist_entries', 'raw_documents')}
    guilds, seen = {}, set()
    for collection, docs in source.items():
        for doc in docs:
            key = (collection, str(doc.get('_id')))
            if key in seen:
                raise ValueError('Duplicate source document')
            seen.add(key)
            source_id = str(doc['_id'])
            gid = snowflake(doc['guild_id'])
            guilds.setdefault(gid, {'guild_id': gid, 'active': True})
            rows['raw_documents'].append({'source_collection': collection, 'source_id': source_id,
                'document': json_util.dumps(doc, json_options=json_util.CANONICAL_JSON_OPTIONS)})
            base = {'id': identity(collection, doc), 'source_id': source_id}
            if collection in ('server_configs', 'word_filters', 'guild_blacklists', 'automod_rule_ids'):
                singleton = (collection, gid)
                if singleton in seen:
                    raise ValueError('Conflicting duplicate guild configuration')
                seen.add(singleton)
            if collection == 'server_configs':
                guilds[gid].update(log_channel=snowflake(doc.get('log_channel'), True),
                                   welcome_channel=snowflake(doc.get('welcome_channel'), True))
            if collection in ('server_configs', 'automod_rule_ids'):
                rule = snowflake(doc.get('automod_rule_id'), True)
                existing = guilds[gid].get('automod_rule_id')
                if existing and rule and existing != rule:
                    raise ValueError('Conflicting AutoMod rule IDs')
                if rule:
                    guilds[gid]['automod_rule_id'] = rule
            elif collection == 'word_filters':
                enabled = doc.get('enabled', True)
                if not isinstance(enabled, bool): raise ValueError('Invalid filter enabled flag')
                words = doc.get('filter_words', [])
                if not isinstance(words, list) or any(not isinstance(w, str) or not w.strip() for w in words):
                    raise ValueError('Invalid filter words')
                normalized = [w.strip().lower() for w in words]
                if len(set(normalized)) != len(normalized): raise ValueError('Duplicate normalized words')
                rows['guild_filter_settings'].append({'guild_id': gid, 'enabled': enabled,
                    'updated_at': date(doc.get('updated_at'), True)})
                rows['filter_words'].extend({'guild_id': gid, 'word': word} for word in normalized)
            elif collection == 'guild_blacklists':
                members = [snowflake(uid) for uid in doc.get('user_ids', [])]
                if len(set(members)) != len(members): raise ValueError('Duplicate blacklist membership')
                rows['guild_blacklist_entries'].extend({'guild_id': gid, 'user_id': uid} for uid in members)
            elif collection in ('moderation_warnings', 'moderation_cases', 'scheduled_invites'):
                row = {**base, 'guild_id': gid, 'user_id': snowflake(doc['user_id']),
                       'reason': str(doc.get('reason', '')), 'created_at': date(doc.get('created_at'), True)}
                if collection == 'scheduled_invites':
                    status = doc.get('status', 'pending')
                    if status not in ('pending', 'sent', 'failed', 'suspended'): raise ValueError('Unknown invite status')
                    row.update(send_at=date(doc['send_at']), status=status)
                    rows['scheduled_invites'].append(row)
                else:
                    row.update(moderator_id=snowflake(doc['moderator_id']), evidence=str(doc.get('evidence', '')))
                    if collection == 'moderation_warnings':
                        number = doc.get('warning_number')
                        if number is not None and (isinstance(number, bool) or not isinstance(number, int) or number < 1):
                            raise ValueError('Invalid historical warning number')
                        row['legacy_warning_number'] = number
                        row['escalation'] = None
                        rows['warnings'].append(row)
                    else:
                        row.update(action=str(doc['action']), duration=str(doc.get('duration') or ''), outcome='historical')
                        rows['moderation_cases'].append(row)
    rows['guild_settings'] = list(guilds.values())
    counters={}
    rows['warnings'].sort(key=lambda row:(row['guild_id'],row['user_id'],row['created_at'] or '',row['source_id']))
    for row in rows['warnings']:
        key=(row['guild_id'],row['user_id'])
        counters[key]=counters.get(key,0)+1
        row['warning_number']=counters[key]
    return rows


def import_sql(rows):
    import base64,json
    statements=['begin;']
    for table,records in rows.items():
        if table not in TABLES:raise ValueError('Unknown import table')
        if not records:continue
        name='bread_private.source_documents' if table=='raw_documents' else 'public.'+table
        columns=sorted({key for row in records for key in row})
        if any(not key.replace('_','').isalnum() for key in columns):raise ValueError('Invalid import column')
        payload=base64.b64encode(json.dumps(records).encode()).decode()
        fields=','.join('"'+key+'"' for key in columns)
        updates=','.join('"'+key+'"=excluded."'+key+'"' for key in columns if key not in TABLES[table])
        conflict=','.join(TABLES[table])
        statements.append(f"insert into {name} ({fields}) select {fields} from jsonb_populate_recordset(null::{name},convert_from(decode('{payload}','base64'),'UTF8')::jsonb) on conflict ({conflict}) "+('do update set '+updates if updates else 'do nothing')+';')
    statements.append('commit;')
    return '\n'.join(statements)


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    from scripts.mongo_snapshot import read_snapshot
    from scripts.supabase_cli import query
    parser=argparse.ArgumentParser()
    parser.add_argument('snapshot',type=Path)
    parser.add_argument('--apply',action='store_true',help='Import into the selected project; the bot must remain offline')
    args=parser.parse_args()
    rows=normalize(read_snapshot(args.snapshot))
    if args.apply:query(import_sql(rows))
    print(json.dumps({'applied':args.apply,'counts':{table:len(data) for table,data in rows.items()}}))
