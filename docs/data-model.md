# Phase 1 data model and workflow

The original CSV schema is a combined content/snapshot interchange header, not a typed database schema. It has 33 unique fields; imports require its exact order and row width. `content_os.py` defines the types and splits content metadata from analytics. The source CSVs remain unchanged.

SQLite stores content keyed by `content_id`, append-only snapshots referencing that ID, and source imports with SHA-256 hashes and exact raw bytes. JSON payloads retain decimal text from CSV (including `174.0` and measured `0.0`); empty CSV cells become null. No derived metrics are calculated. Raw JSON input is retained for later snapshots. Database `recorded_at` is ingestion time, separate from measured `data_captured_at`. Historical seed capture/publication dates remain null.

Each platform publication needs its own content ID; cross-posts share a `creative_id` but retain separate snapshots. Platform names are free text; use consistent lowercase names. Content records are insert-only through the CLI. Duplicate IDs fail; do not overwrite an existing record to re-import changed seeds. Byte-identical seed imports are idempotent. Imports are transactional, so any bad row rolls back the whole batch.

## Validation

Required content fields: content_id, creative_id, platform, title. Optional fields may be omitted or null. Numeric values must be finite and nonnegative; counts must be integral (decimal notation such as `174.0` is accepted). Duration, when known, must be positive; skip rate is 0–100 inclusive. Text must be nonempty or null. Unknown fields are rejected. Dates must be ISO timestamps with a timezone; snapshot dates cannot precede a known publication date. New snapshots require a capture date and data source. Only the historical seed import permits an unknown capture date.

Average watch time may exceed duration because of looping/replays. Counts are not assumed to rise over time: platform corrections can reduce them. No relationship is imposed between reach, views, interactions, or follows without verified platform definitions. In particular the seeds contain measured total interactions of zero with unknown component counts; these are preserved. Missing component counts are never inferred from totals.

## Add content and later snapshots

1. Copy `data/examples/content.json` to a new JSON file and replace the example values with actual metadata. Use a new content ID for each platform publication. Leave unknowns null. Run `python content_os.py add-content your-content.json`.
2. Copy `data/examples/snapshot.json` to a separate file. Enter the actual capture timestamp, source reference, and only observed metrics. Use JSON null for unknowns and zero only for measured zeros. Run `python content_os.py add-snapshot YOUR_CONTENT_ID your-snapshot.json`.
3. For later observations, create another snapshot file and repeat step 2. Old snapshots remain intact. SQL triggers reject updates/deletes. For a correction, append a snapshot with a note identifying the prior snapshot and reason; later analysis must decide which observation to use. Repeated snapshot submissions are retained as separate observations, so check the export before retrying.
4. Inspect records with `python content_os.py export`. Snapshot IDs, capture dates, sources, and ingestion times distinguish history. Keep source exports/screenshots referenced in `data_source`; the app does not fetch them.

Back up `data/content.sqlite3` while commands are idle, along with original inputs. SQLite is a local file, not a shared multi-user service; these safeguards prevent ordinary accidental edits, not deliberate database tampering.

Experiment hypotheses remain in `docs/experiments.md`. This phase does not implement experiment scoring, analytics reports, or publishing.
