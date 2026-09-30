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
