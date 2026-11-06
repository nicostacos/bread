import copy
import unittest
from scripts.validate_migration import compare_rows
from scripts.migrate_supabase import import_sql


class ValidationTests(unittest.TestCase):
    def test_wrong_destination_content_rejected(self):
        expected={'warnings':[{'id':'abc','reason':'original','created_at':'2026-01-01T00:00:00+00:00'}]}
        actual=copy.deepcopy(expected)
        actual['warnings'][0]['created_at']='2026-01-01T00:00:00Z'
        compare_rows(expected,actual)
        actual['warnings'][0]['reason']='changed'
        with self.assertRaises(ValueError):compare_rows(expected,actual)
        with self.assertRaises(ValueError):compare_rows(expected,{'warnings':[]})

    def test_import_encodes_data_instead_of_executable_sql(self):
        sql=import_sql({'warnings':[{'id':'abc','reason':"'); drop table warnings; --"}]})
        self.assertNotIn('drop table',sql)
        self.assertIn('base64',sql)
        self.assertIn('on conflict',sql)
