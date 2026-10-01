# Provider ingestion

The provider interface (`providers.AnalyticsProvider.fetch`) returns a `Fetch` containing source, actual external fetch timestamp, raw response, and platform observations. `ingestion.sync_provider` owns discovery and snapshot persistence; providers never access SQLite. No Windsor dependency or API-specific analytics logic is present. An external connector can normalize its response into this contract or implement the interface directly.

The included Instagram provider consumes a JSON file with this shape (illustrative placeholders, not BTB measurements):

```json
{
  "source": "connector/account/export reference",
  "fetched_at": "2026-09-30T13:00:00-04:00",
  "reels": [{
    "media_product_type": "REELS",
    "platform_media_id": "actual-instagram-media-id",
    "published_at": "2026-09-30T12:00:00-04:00",
    "title": "Actual title or caption",
    "metrics_observed_at": "2026-09-30T13:00:00-04:00",
    "cached": false,
    "metrics": {"views": null, "likes": null}
  }]
}
```

Normalize only verified metric mappings to Phase 1 metric names. Omit unsupported metrics or supply null. Never substitute reach for views or derive missing metrics. Unknown metric names fail validation. Media IDs must be nonempty strings, preserving their exact identifier. Non-REELS records are ignored. Reels require a known publication timestamp. Missing title uses an explicitly generated `Instagram Reel <media ID>` label, not invented creative copy.

`fetched_at` means when the external response was actually fetched, not when a saved file was read locally. `metrics_observed_at` means when the returned metrics were current; leave it null if freshness is unknown. Do not claim file-read time as a new API fetch. The adapter does not contact Instagram, fetch pagination, authenticate, or schedule jobs. Supply the complete normalized result from your connector, including existing Reels whose analytics need refreshing. Connector pagination and permissions remain connector responsibilities.

```powershell
python content_os.py sync-content --provider instagram connector-response.json
python content_os.py sync-analytics --provider instagram connector-response.json
python content_os.py export
```

`sync-content` discovers publications only. `sync-analytics` also discovers missing publications and appends an observation for every returned Reel. Both are atomic. Exact response replay is idempotent per command; a new fetch envelope creates new snapshots even when metrics are unchanged. Duplicate media IDs within one batch fail rather than arbitrarily choosing a row. Existing records match by platform plus platform media ID, even if their local content ID differs. A SQLite unique index enforces that identity for manual additions as well. Existing metadata is retained; conflicting known publication dates fail. Cross-post creative relationships require human linking; automatically discovered posts use their platform/media identity as the initial creative ID.

All metric fields appear in ingestion snapshots; missing fields remain null and measured zeros remain zero. Raw responses and per-Reel raw input are stored. `data_captured_at` and `data_fetched_at` carry the actual external fetch time; `recorded_at` remains local ingestion time. `metrics_observed_at` carries the distinct observation time. Older/equal observations relative to prior provider history are `stale`; known older cache observations or explicit cached responses are `cached`; unknown observation times are `unknown`. Only observations current at fetch time and newer than prior history are `fresh`. Cached/stale data is retained, never silently presented as a fresh checkpoint or overwritten.

Checkpoint labels are assigned only to fresh observations within inclusive ±25% windows around 1h, 6h, 24h, 72h, and 7d after publication. Pulls outside the windows have null checkpoints. Multiple observations can share a checkpoint. This is labeling, not a scheduler or an assertion that missed checkpoints were measured. The policy is a documented starting convention and can be adjusted after a human decision.

Opening an existing Phase 1 database adds the external-ID index without rewriting source records or snapshots. If old records contain duplicate non-null external IDs, migration fails: resolve those identities deliberately before syncing. Seed records have unknown external IDs and cannot be matched by title; supply verified IDs before enabling ingestion for those same historical Reels to avoid an unverified merge. Back up the database first; there is no automatic fuzzy matching.
