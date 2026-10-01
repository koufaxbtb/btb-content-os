import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from content_os import ROOT, add_content, connect
from ingestion import checkpoint, sync_provider
from providers import Fetch, InstagramProvider, Observation


def response(fetch='2026-09-01T01:00:00Z', observed='2026-09-01T01:00:00Z', **changes):
    reel = dict(media_product_type='REELS', platform_media_id='123',
                published_at='2026-09-01T00:00:00Z', title='Test Reel',
                metrics={'views': 10, 'likes': 0}, metrics_observed_at=observed)
    reel.update(changes)
    return dict(source='test connector', fetched_at=fetch, reels=[reel])


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')

    def tearDown(self):
        self.db.close()

    def sync(self, value, **kwargs):
        return sync_provider(self.db, InstagramProvider(value), **kwargs)

    def snapshots(self):
        return [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM snapshots ORDER BY snapshot_id')]

    def test_discovery_duplicate_and_nulls(self):
        self.assertEqual(self.sync(response())['content_created'], 1)
        first = self.snapshots()[0]
        self.assertEqual(first['likes'], 0)
        self.assertIsNone(first['reach'])
        self.assertIsNone(first['original_audio_uses'])
        self.assertEqual(first['data_source'], 'test connector')
        self.assertEqual(first['data_fetched_at'], '2026-09-01T01:00:00Z')
        self.assertEqual(first['checkpoint'], '1h')
        self.assertEqual(self.sync(response())['responses_skipped'], 1)
        self.sync(response('2026-09-01T06:00:00Z', '2026-09-01T06:00:00Z', metrics={'views': 8, 'likes': None}))
        self.assertEqual(self.db.execute('SELECT count(*) FROM content').fetchone()[0], 1)
        self.assertEqual(self.snapshots()[0], first)
        self.assertEqual(self.snapshots()[1]['views'], 8)
        self.assertEqual(self.snapshots()[1]['checkpoint'], '6h')
        for sql in ['DELETE FROM snapshots', "UPDATE snapshots SET payload='{}'"]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)

    def test_existing_manual_content_and_unique_external_id(self):
        record = dict(content_id='manual', creative_id='creative', platform='instagram',
                      platform_media_id='123', title='Human title')
        add_content(self.db, record)
        self.sync(response())
        self.assertEqual(self.db.execute('SELECT content_id FROM snapshots').fetchone()[0], 'manual')
        with self.assertRaises(sqlite3.IntegrityError):
            add_content(self.db, dict(record, content_id='duplicate'))
        add_content(self.db, dict(record, content_id='other-platform', platform='tiktok'))

    def test_cached_stale_and_unknown(self):
        self.sync(response())
        self.sync(response('2026-09-01T06:00:00Z', '2026-09-01T01:00:00Z'))
        self.sync(response('2026-09-01T07:00:00Z', '2026-09-01T06:00:00Z', cached=True))
        self.sync(response('2026-09-01T08:00:00Z', None))
        self.assertEqual([s['freshness'] for s in self.snapshots()], ['fresh', 'stale', 'cached', 'unknown'])
        self.assertTrue(all(s['checkpoint'] is None for s in self.snapshots()[1:]))
        self.assertEqual(len(self.snapshots()), 4)

    def test_checkpoint_windows(self):
        published = datetime(2026, 9, 1, tzinfo=timezone.utc)
        for label, hours in [('1h', 1), ('6h', 6), ('24h', 24), ('72h', 72), ('7d', 168)]:
            for factor in [.75, 1, 1.25]:
                self.assertEqual(checkpoint(published, published + timedelta(hours=hours * factor)), label)
        for hours in [0, .74, 2, 12, 40, 100, 211]:
            self.assertIsNone(checkpoint(published, published + timedelta(hours=hours)))

    def test_discovery_then_analytics_and_non_reels(self):
        value = response()
        value['reels'].append({'media_product_type': 'FEED'})
        self.assertEqual(self.sync(value, analytics=False)['content_created'], 1)
        self.assertEqual(self.snapshots(), [])
        self.assertEqual(self.sync(value)['snapshots_added'], 1)

    def test_invalid_response_rolls_back(self):
        for change in [dict(platform_media_id=None), dict(metrics={'views': -1}),
                       dict(metrics={'unsupported': 4}), dict(cached='yes'),
                       dict(metrics_observed_at='2026-09-02T00:00:00Z')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.sync(response(**change))
            self.assertEqual(self.db.execute('SELECT count(*) FROM content').fetchone()[0], 0)
        value = response()
        value['reels'].append(dict(value['reels'][0]))
        with self.assertRaises(ValueError):
            self.sync(value)
        self.assertEqual(self.db.execute('SELECT count(*) FROM content').fetchone()[0], 0)

    def test_generic_provider_contract(self):
        class OtherProvider:
            def fetch(self):
                return Fetch('other connector', '2026-09-01T01:00:00Z', [Observation(
                    'another-platform', 'abc', '2026-09-01T00:00:00Z', 'Other', {},
                    None, False, {'id': 'abc'})], '{"external": "response"}')
        self.assertEqual(sync_provider(self.db, OtherProvider())['snapshots_added'], 1)
        self.assertIsNone(self.snapshots()[0]['views'])

    def test_publication_conflict_and_later_bad_row_are_atomic(self):
        self.sync(response())
        with self.assertRaises(ValueError):
            self.sync(response('2026-09-01T06:00:00Z', '2026-09-01T06:00:00Z',
                               published_at='2026-08-31T00:00:00Z'))
        value = response('2026-09-01T06:00:00Z', '2026-09-01T06:00:00Z')
        value['reels'].append(dict(value['reels'][0], platform_media_id='456', metrics={'views': -1}))
        with self.assertRaises(ValueError):
            self.sync(value)
        self.assertEqual(len(self.snapshots()), 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM provider_receipts').fetchone()[0], 1)

    def test_cli_and_existing_database_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = str(Path(folder) / 'old.sqlite3')
            db = sqlite3.connect(db_path)
            db.execute('CREATE TABLE content(content_id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            db.commit()
            db.close()
            input_path = Path(folder) / 'response.json'
            input_path.write_text(json.dumps(response()))
            for command in ['sync-content', 'sync-analytics']:
                run = subprocess.run([sys.executable, str(ROOT / 'content_os.py'), '--db', db_path,
                                      command, '--provider', 'instagram', str(input_path)],
                                     capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
            db = connect(db_path)
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM provider_receipts').fetchone()[0], 2)
            db.close()


if __name__ == '__main__':
    unittest.main()
