# Business Analytics Portfolio

## Project Overview
Brief description of your business problem and analytics solution.

## Business Problem
- What business challenge are you addressing?
- Why is this problem important?
- What impact will solving it have?

## Data Sources
- Description of data sources
- Data acquisition methods
- Data quality considerations

## Solution Architecture
- High-level system design
- Key components and their relationships
- Technology stack overview

## Setup Instructions

### Prerequisites
- Python 3.10+
- UV package manager
- Git

### Installation
1. Clone this repository:
   ```bash
   git clone <your-repo-url>
   cd business-analytics-portfolio   ```
2. Install dependencies into the project environment:
   ```bash
   uv sync
   ```

## Data Pipeline

### Run it (one command)
Put the raw files in `data/raw/` (`data1.xlsx`, `data2.xlsx`), then from the project root run:

```bash
uv run python scripts/run_pipeline.py
```

This runs **extract → transform → validate → load** and writes a SQLite database to
`data/processed/rare_earth.db`. Progress is logged to the console and to `logs/pipeline.log`.
The command exits with code `0` on success and `1` on any failure (missing file, failed
validation, database error), with the reason in the log. Re-running is safe: each run
replaces the table contents inside one transaction, so no duplicate rows are created.

### How it works
| Stage | Module | What it does |
|---|---|---|
| Extract | `src/data_pipeline/extract.py` | Reads the Excel files listed in `config/app_config.yaml` with Pandas |
| Transform | `src/data_pipeline/transform.py` | Renames columns, fixes the swapped reporter header in `data1.xlsx`, maps country names between sources, builds `partner_trade_energy` |
| Validate | `src/data_pipeline/validate.py` | Pandera schemas: types, allowed values, ranges, uniqueness, cross-table row counts |
| Load | `src/data_pipeline/load.py` | SQLAlchemy table definitions with primary keys; writes all tables in one transaction |

Configuration lives in `config/database.yaml` (database URL; SQLite by default, PostgreSQL
supported by changing the URL) and `config/app_config.yaml` (input files, logging).
Table and column definitions are in [docs/data_dictionary.md](docs/data_dictionary.md).

### Other commands
```bash
uv run python scripts/setup_database.py   # create empty tables only
uv run pytest                              # run the tests
```
