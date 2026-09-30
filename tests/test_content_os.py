import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import content_os as os


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.db = os.connect(':memory:')

    def tearDown(self):
        self.db.close()

    def seed(self):
        return os.import_seed(self.db, os.ROOT / 'data/seed_content.csv', os.ROOT / 'data/content_schema.csv')

    def test_seed_preserves_values_raw_and_unknowns(self):
        self.assertEqual(self.seed(), 5)
        rows = dict(self.db.execute('SELECT content_id,payload FROM snapshots'))
        maybach = json.loads(rows['seed-maybach-ep1'])
        self.assertEqual(maybach['views'], '174.0')
        self.assertEqual(maybach['total_interactions'], '0.0')
        self.assertIsNone(maybach['likes'])
        self.assertIsNone(maybach['data_captured_at'])
        self.assertEqual(json.loads(rows['seed-available-credit'])['avg_watch_time_seconds'], '9.16')
        self.assertEqual(self.db.execute('SELECT raw_bytes FROM imports').fetchone()[0],
                         (os.ROOT / 'data/seed_content.csv').read_bytes())
        self.assertEqual(self.seed(), 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 5)

    def test_invalid_analytics(self):
        for field, value in [('views', -1), ('likes', 1.2), ('reach', True),
                             ('shares', 'NaN'), ('avg_watch_time_seconds', 'Infinity'),
                             ('skip_rate_pct', 101), ('views', 'abc'), ('likes', '')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                os.validate({field: value}, os.SNAPSHOT_FIELDS, [])
        os.validate({'views': 0, 'likes': None, 'skip_rate_pct': 100,
                     'avg_watch_time_seconds': 1000}, os.SNAPSHOT_FIELDS, [])

    def test_content_validation(self):
        for record in [{}, {'content_id': 'a', 'creative_id': 'a', 'platform': 'instagram',
                            'title': 'a', 'duration_seconds': 0}, {'bogus': 1}]:
            with self.assertRaises(ValueError):
                os.add_content(self.db, record)

    def test_history_platform_separation_and_constraints(self):
        for platform in ['instagram', 'tiktok']:
            os.add_content(self.db, dict(content_id=platform, creative_id='same', platform=platform,
                                         title='Test', published_at='2026-09-01T12:00:00Z'))
        snapshot = dict(data_source='manual platform export', data_captured_at='2026-09-02T12:00:00Z', views=10)
        os.add_snapshot(self.db, 'instagram', snapshot)
        os.add_snapshot(self.db, 'instagram', dict(snapshot, views=8, data_captured_at='2026-09-03T12:00:00Z'))
        os.add_snapshot(self.db, 'tiktok', dict(snapshot, views=2))
        self.assertEqual(self.db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 3)
        for sql in ['UPDATE snapshots SET payload=\'{}\'', 'DELETE FROM snapshots']:
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        for record in [dict(snapshot, data_captured_at=None), dict(snapshot, data_captured_at='bad'),
                       dict(snapshot, data_captured_at='2026-09-02'),
                       dict(snapshot, data_captured_at='2026-08-01T12:00:00Z')]:
            with self.assertRaises(ValueError):
                os.add_snapshot(self.db, 'instagram', record)
        with self.assertRaises(ValueError):
            os.add_snapshot(self.db, 'missing', snapshot)
        with self.assertRaises(sqlite3.IntegrityError):
            os.add_content(self.db, dict(content_id='instagram', creative_id='same', platform='instagram', title='Test'))

    def test_bad_import_rolls_back(self):
        source = (os.ROOT / 'data/seed_content.csv').read_text()
        for invalid in [source.replace('41.8', '101'), source + '\nbad,row\n', source.replace('content_id,', 'wrong,', 1)]:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'bad.csv'
                path.write_text(invalid)
                with self.assertRaises(ValueError):
                    os.import_seed(self.db, path, os.ROOT / 'data/content_schema.csv')
                self.assertEqual(self.db.execute('SELECT count(*) FROM content').fetchone()[0], 0)
                self.assertEqual(self.db.execute('SELECT count(*) FROM imports').fetchone()[0], 0)

    def test_bad_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            schema = Path(folder) / 'schema.csv'
            schema.write_text('content_id,content_id\n')
            with self.assertRaises(ValueError):
                os.import_seed(self.db, os.ROOT / 'data/seed_content.csv', schema)


if __name__ == '__main__':
    unittest.main()
