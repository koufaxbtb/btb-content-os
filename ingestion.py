"""Provider-independent discovery and append-only ingestion."""
import hashlib
import json

from content_os import METRICS, add_content, add_snapshot, timestamp, validate
from providers import AnalyticsProvider

CHECKPOINTS = [('1h', 1), ('6h', 6), ('24h', 24), ('72h', 72), ('7d', 168)]


def checkpoint(published, observed):
    hours = (observed - published).total_seconds() / 3600
    for label, target in CHECKPOINTS:
        if target * .75 <= hours <= target * 1.25:
            return label
    return None


def sync_provider(db, provider: AnalyticsProvider, analytics=True):
    batch = provider.fetch()
    validate({'data_source': batch.source, 'data_fetched_at': batch.fetched_at},
             ['data_source', 'data_fetched_at'], ['data_source', 'data_fetched_at'])
    fetched = timestamp(batch.fetched_at, 'data_fetched_at')
    result = {'content_created': 0, 'snapshots_added': 0, 'responses_skipped': 0}
    # A savepoint works both standalone and inside the CLI transaction.
    db.execute('SAVEPOINT provider_sync')
    try:
        db.execute('''CREATE TABLE IF NOT EXISTS provider_receipts (
            digest TEXT PRIMARY KEY, source TEXT NOT NULL, fetched_at TEXT NOT NULL,
            raw_response TEXT NOT NULL)''')
        digest = hashlib.sha256(batch.raw.encode('utf-8')).hexdigest()
        # Content-only discovery must not suppress a later analytics pull.
        receipt = ('analytics:' if analytics else 'content:') + digest
        if db.execute('SELECT 1 FROM provider_receipts WHERE digest=?', (receipt,)).fetchone():
            result['responses_skipped'] = 1
        else:
            seen = set()
            for item in batch.observations:
                validate({'platform': item.platform, 'platform_media_id': item.media_id,
                          'published_at': item.published_at, 'title': item.title},
                         ['platform', 'platform_media_id', 'published_at', 'title'],
                         ['platform', 'platform_media_id', 'published_at', 'title'])
                identity = (item.platform, item.media_id)
                if identity in seen:
                    raise ValueError('Duplicate media ID within provider response')
                seen.add(identity)
                published = timestamp(item.published_at, 'published_at')
                if published > fetched:
                    raise ValueError('Publication is after fetch time')
                validate(item.metrics, METRICS, [])
                observed = timestamp(item.observed_at, 'metrics_observed_at')
                if observed and (observed > fetched or observed < published):
                    raise ValueError('Metric observation must fall between publication and fetch')
                row = db.execute('''SELECT content_id,payload FROM content
                    WHERE json_extract(payload,'$.platform')=?
                    AND json_extract(payload,'$.platform_media_id')=?''', identity).fetchone()
                if row:
                    content_id = row[0]
                    known_publication = timestamp(json.loads(row[1]).get('published_at'), 'published_at')
                    if known_publication and known_publication != published:
                        raise ValueError('Conflicting publication date for existing media ID')
                else:
                    content_id = f'{item.platform}:{item.media_id}'
                    add_content(db, {'content_id': content_id, 'creative_id': content_id,
                                     'platform': item.platform, 'platform_media_id': item.media_id,
                                     'published_at': item.published_at, 'title': item.title,
                                     'format': 'reel'})
                    result['content_created'] += 1
                if analytics:
                    previous = [timestamp(json.loads(r[0]).get('metrics_observed_at'), 'metrics_observed_at')
                                for r in db.execute('SELECT payload FROM snapshots WHERE content_id=?', (content_id,))]
                    previous = [date for date in previous if date is not None]
                    freshness = ('unknown' if observed is None else
                                 'stale' if previous and observed <= max(previous) else
                                 'cached' if item.cached or observed < fetched else 'fresh')
                    snapshot = {metric: item.metrics.get(metric) for metric in METRICS}
                    snapshot.update(data_source=batch.source, data_captured_at=batch.fetched_at,
                                    data_fetched_at=batch.fetched_at, metrics_observed_at=item.observed_at,
                                    freshness=freshness,
                                    checkpoint=checkpoint(published, observed) if freshness == 'fresh' else None)
                    add_snapshot(db, content_id, snapshot, json.dumps(item.raw))
                    result['snapshots_added'] += 1
            db.execute('INSERT INTO provider_receipts VALUES (?,?,?,?)',
                       (receipt, batch.source, batch.fetched_at, batch.raw))
        db.execute('RELEASE provider_sync')
    except Exception:
        db.execute('ROLLBACK TO provider_sync')
        db.execute('RELEASE provider_sync')
        raise
    return result
