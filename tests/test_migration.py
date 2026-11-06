import copy
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from bson import ObjectId

from scripts.mongo_snapshot import write_snapshot, read_snapshot
from scripts.migrate_supabase import normalize


class MigrationTests(unittest.TestCase):
    def source(self):
        return {name: [] for name in (
            'server_configs', 'word_filters', 'moderation_warnings',
            'moderation_cases', 'scheduled_invites', 'guild_blacklists', 'automod_rule_ids')}

    def test_snapshot_preserves_bson_and_unknown_fields(self):
        source = self.source()
        source['server_configs'] = [{'_id': ObjectId(), 'guild_id': 987654321098765432,
                                     'unknown': {'nested': [1, 'text']}}]
        with tempfile.TemporaryDirectory() as tmp:
            write_snapshot(source, Path(tmp))
            self.assertEqual(read_snapshot(Path(tmp)), source)
            file = Path(tmp)/'server_configs.json'
            file.write_text('[]')
            with self.assertRaises(ValueError):
                read_snapshot(Path(tmp))

    def test_legacy_automod_and_large_ids(self):
        source = self.source()
        source['server_configs'] = [{'_id': ObjectId(), 'guild_id': 987654321098765432,
                                     'log_channel': 876543210987654321, 'automod_rule_id': '765432109876543210'}]
        rows = normalize(source)
        self.assertEqual(rows['guild_settings'][0]['guild_id'], '987654321098765432')
        self.assertEqual(rows['guild_settings'][0]['automod_rule_id'], '765432109876543210')
        self.assertEqual(len(rows['raw_documents']), 1)

    def test_conflicting_automod_rejected(self):
        source = self.source()
        source['server_configs'] = [{'_id': ObjectId(), 'guild_id': 123, 'automod_rule_id': '456'}]
        source['automod_rule_ids'] = [{'_id': ObjectId(), 'guild_id': 123, 'automod_rule_id': '789'}]
        with self.assertRaises(ValueError): normalize(source)

    def test_duplicate_settings_rejected(self):
        source = self.source()
        source['server_configs'] = [{'_id': ObjectId(), 'guild_id': 123}, {'_id': ObjectId(), 'guild_id': 123}]
        with self.assertRaises(ValueError): normalize(source)

    def test_warning_dates_and_idempotent_ids(self):
        source = self.source()
        source['moderation_warnings'] = [{'_id': ObjectId(), 'guild_id': 123, 'user_id': 456,
            'moderator_id': 789, 'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
            'reason': 'test', 'evidence': 'evidence', 'warning_number': 4}]
        rows = normalize(source)
        self.assertEqual(rows, normalize(copy.deepcopy(source)))
        self.assertEqual(rows['warnings'][0]['created_at'], '2026-01-01T00:00:00+00:00')
        self.assertEqual(rows['warnings'][0]['warning_number'], 1)
        self.assertEqual(rows['warnings'][0]['legacy_warning_number'], 4)
        self.assertEqual(rows['warnings'][0]['evidence'], 'evidence')

    def test_missing_historical_numbers_derive_chronologically(self):
        source=self.source()
        source['moderation_warnings']=[{'_id':ObjectId(),'guild_id':123,'user_id':456,'moderator_id':789,
            'reason':'later','created_at':datetime(2026,2,1,tzinfo=timezone.utc)},
            {'_id':ObjectId(),'guild_id':123,'user_id':456,'moderator_id':789,
            'reason':'earlier','created_at':datetime(2026,1,1,tzinfo=timezone.utc)}]
        rows=normalize(source)['warnings']
        self.assertEqual([(r['reason'],r['warning_number']) for r in rows],[('earlier',1),('later',2)])
        self.assertTrue(all(r['legacy_warning_number'] is None for r in rows))

    def test_malformed_ids_and_dates_rejected(self):
        source = self.source()
        source['scheduled_invites'] = [{'_id': ObjectId(), 'guild_id': 123, 'user_id': 456,
                                       'send_at': 'yesterday'}]
        with self.assertRaises(ValueError): normalize(source)
        source['scheduled_invites'][0]['guild_id'] = -1
        with self.assertRaises(ValueError): normalize(source)
