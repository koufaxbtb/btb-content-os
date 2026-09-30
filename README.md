# Bend The Block Content OS

Private content intelligence and experimentation system for Bend The Block.

## Mission

Build a data-driven system that learns from every piece of content we publish and helps us improve hooks, retention, sharing, follower conversion, and original-audio adoption.

## Core Systems

- Content Library
- Analytics Engine
- Experiment Log
- Hook Lab
- Trend Radar
- Culture & Audio Engine

## Implemented: Phase 1 only

Local content records, seed import, analytics snapshot history, validation, and tests. No dashboard or publishing integration.

Requires Python 3.10+; no third-party packages, server, or installation step. SQLite is included with Python and provides transactions, foreign keys, and inspectable local storage with minimal infrastructure. JSON payloads preserve supplied numeric representations; null means unknown.

From the repository root:

```powershell
python content_os.py import-seed
python content_os.py export
python -m unittest discover -s tests -v
```

If Windows uses the Python launcher, replace `python` with `py -3`. The default database is `data/content.sqlite3` (ignored by Git). To select another existing directory, put `--db PATH` before the command. Re-running an unchanged seed import adds nothing.

See [data model and daily workflow](docs/data-model.md) for adding content and later snapshots, validation rules, corrections, and backups. Editable templates live in [data/examples](data/examples). Example values are placeholders, not measured records.

Source documents: [strategy](docs/strategy.md), [experiments](docs/experiments.md), [CSV schema](data/content_schema.csv), and [original seeds](data/seed_content.csv). These source files remain unchanged.
