# Install

Use Python 3.10+ with its built-in SQLite support. No additional dependencies are required.

-   AGENTS.md
-   docs/strategy.md
-   docs/experiments.md
-   data/content_schema.csv
-   data/seed_content.csv

## Setup

From the repository root, run `python content_os.py import-seed`, then
`python -m unittest discover -s tests -v`. On Windows, `py -3` can replace
`python`. See [README](README.md) and [workflow](docs/data-model.md).

## Provider ingestion

No new dependencies are needed. Back up an existing database before first sync.
Prepare a normalized Instagram response using the [provider contract](docs/ingestion.md),
then run `python content_os.py sync-analytics --provider instagram connector-response.json`.
This discovers new Reels and appends snapshots. Use `sync-content` for discovery alone.
The connector must supply actual fetch times and verified metric mappings; live API
authentication, pagination, and scheduling are not configured by this repository.
Run the full suite with `python -m unittest discover -s tests -v`.
