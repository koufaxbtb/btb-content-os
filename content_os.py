"""Phase 1 local content store. Python standard library only."""
import argparse
import csv
import hashlib
import io
import json
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COUNTS = 'views reach likes comments shares saves total_interactions follows_generated profile_visits original_audio_uses'.split()
METRICS = COUNTS + ['skip_rate_pct', 'avg_watch_time_seconds']
SNAPSHOT_FIELDS = METRICS + ['data_captured_at', 'data_source', 'notes']
FIELDS = 'content_id creative_id platform platform_media_id published_at title series content_lane format hook_text script_text reusable_audio_line target_emotion duration_seconds cta_type editing_notes source_or_topic experiment_id views reach skip_rate_pct avg_watch_time_seconds likes comments shares saves total_interactions follows_generated profile_visits original_audio_uses data_captured_at data_source notes'.split()
CONTENT_FIELDS = [f for f in FIELDS if f not in SNAPSHOT_FIELDS]


def timestamp(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'{field}: expected ISO timestamp')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError('timezone required')
        return result
    except ValueError as exc:
        raise ValueError(f'{field}: use an ISO timestamp with timezone') from exc


def validate(record, allowed, required):
    if not isinstance(record, dict) or set(record) - set(allowed):
        raise ValueError('Unknown fields or invalid object')
    for field in required:
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f'{field}: required nonempty text')
    for field, value in record.items():
        if value is None:
            continue
        if field in METRICS + ['duration_seconds']:
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError(f'{field}: expected a number')
            try:
                number = Decimal(str(value))
            except InvalidOperation as exc:
                raise ValueError(f'{field}: malformed number') from exc
            if not number.is_finite() or number < 0:
                raise ValueError(f'{field}: must be finite and nonnegative')
            if field in COUNTS and number != number.to_integral_value():
                raise ValueError(f'{field}: count must be integral')
            if field == 'skip_rate_pct' and number > 100:
                raise ValueError('skip_rate_pct: must be between 0 and 100')
            if field == 'duration_seconds' and number == 0:
                raise ValueError('duration_seconds: must be positive')
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f'{field}: use nonempty text or null')
    for field in ['published_at', 'data_captured_at']:
        timestamp(record.get(field), field)


def connect(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA foreign_keys = ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS imports (
        digest TEXT PRIMARY KEY, source_name TEXT NOT NULL, raw_bytes BLOB NOT NULL);
    CREATE TABLE IF NOT EXISTS content (
        content_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS snapshots (
        snapshot_id INTEGER PRIMARY KEY, content_id TEXT NOT NULL REFERENCES content,
        payload TEXT NOT NULL, raw_input TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
    CREATE TRIGGER IF NOT EXISTS snapshots_no_update BEFORE UPDATE ON snapshots
        BEGIN SELECT RAISE(ABORT, 'Snapshots are append-only'); END;
    CREATE TRIGGER IF NOT EXISTS snapshots_no_delete BEFORE DELETE ON snapshots
        BEGIN SELECT RAISE(ABORT, 'Snapshots are append-only'); END;
    ''')
    return db


def add_content(db, record):
    validate(record, CONTENT_FIELDS, ['content_id', 'creative_id', 'platform', 'title'])
    db.execute('INSERT INTO content VALUES (?, ?)', (record['content_id'], json.dumps(record)))


def add_snapshot(db, content_id, record, raw=None, historical=False):
    validate(record, SNAPSHOT_FIELDS, ['data_source'] + ([] if historical else ['data_captured_at']))
    row = db.execute('SELECT payload FROM content WHERE content_id=?', (content_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown content_id')
    published = timestamp(json.loads(row[0]).get('published_at'), 'published_at')
    captured = timestamp(record.get('data_captured_at'), 'data_captured_at')
    if published and captured and captured < published:
        raise ValueError('Snapshot predates publication')
    db.execute('INSERT INTO snapshots(content_id,payload,raw_input) VALUES (?,?,?)',
               (content_id, json.dumps(record), raw if raw is not None else json.dumps(record)))


def import_seed(db, seed, schema):
    raw = Path(seed).read_bytes()
    header = list(csv.reader(io.StringIO(Path(schema).read_text(encoding='utf-8-sig'))))
    if header != [FIELDS]:
        raise ValueError('Schema must contain exactly the documented unique field header')
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    if not rows or rows[0] != FIELDS:
        raise ValueError('Seed header does not match schema')
    digest = hashlib.sha256(raw).hexdigest()
    if db.execute('SELECT 1 FROM imports WHERE digest=?', (digest,)).fetchone():
        return 0
    with db:
        db.execute('INSERT INTO imports VALUES (?,?,?)', (digest, str(seed), raw))
        for cells in rows[1:]:
            if len(cells) != len(FIELDS):
                raise ValueError('Malformed CSV row width')
            record = dict(zip(FIELDS, [None if cell == '' else cell for cell in cells]))
            add_content(db, {f: record[f] for f in CONTENT_FIELDS})
            add_snapshot(db, record['content_id'], {f: record[f] for f in SNAPSHOT_FIELDS},
                         json.dumps(dict(zip(FIELDS, cells))), historical=True)
    return len(rows) - 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=str(ROOT / 'data/content.sqlite3'))
    sub = parser.add_subparsers(dest='command', required=True)
    seed = sub.add_parser('import-seed')
    seed.add_argument('--seed', default=str(ROOT / 'data/seed_content.csv'))
    seed.add_argument('--schema', default=str(ROOT / 'data/content_schema.csv'))
    content = sub.add_parser('add-content')
    content.add_argument('file')
    snap = sub.add_parser('add-snapshot')
    snap.add_argument('content_id')
    snap.add_argument('file')
    sub.add_parser('export')
    args = parser.parse_args()
    try:
        with connect(args.db) as db:
            if args.command == 'import-seed':
                print(f'Imported {import_seed(db, args.seed, args.schema)} content records and snapshots')
            elif args.command in ('add-content', 'add-snapshot'):
                raw = Path(args.file).read_text(encoding='utf-8-sig')
                record = json.loads(raw)
                if args.command == 'add-content':
                    add_content(db, record)
                else:
                    add_snapshot(db, args.content_id, record, raw)
                print('Added successfully')
            else:
                print(json.dumps({
                    'content': [json.loads(r[0]) for r in db.execute('SELECT payload FROM content ORDER BY content_id')],
                    'snapshots': [dict(snapshot_id=r[0], content_id=r[1], values=json.loads(r[2]), recorded_at=r[3])
                                  for r in db.execute('SELECT snapshot_id,content_id,payload,recorded_at FROM snapshots ORDER BY snapshot_id')]
                }, indent=2))
    except (ValueError, sqlite3.Error, OSError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
