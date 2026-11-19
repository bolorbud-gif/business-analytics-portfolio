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
   git clone https://github.com/bolorbud-gif/business-analytics-portfolio.git
   cd business-analytics-portfolio
   ```
2. Install dependencies into the project environment:
   ```bash
   uv sync
   ```

Full setup, including how authorized users supply the restricted source data: [docs/setup.md](docs/setup.md).

## Data Pipeline

### Build or refresh the database (one command)

```bash
uv run python scripts/run_pipeline.py            # real data in data/raw/ (not committed)
uv run python scripts/run_pipeline.py --sample   # committed synthetic sample, no access needed
```

This runs **extract → transform → validate → load** and writes a SQLite database to
`data/processed/rare_earth.db` (or `rare_earth_sample.db`). Progress goes to the console and
`logs/pipeline.log`. The command exits with `0` on success and `1` on failure (missing file,
bad structure, too many rejected rows, database error); the database is left unchanged on
failure. Add `--rebuild` to drop and recreate the tables.

Every run writes a quality report: [docs/quality_report.md](docs/quality_report.md) (real data)
and [docs/quality_report_sample.md](docs/quality_report_sample.md) (sample). Each report has
row counts, missingness, duplicates, rejected-record counts, the action taken on bad records,
and a re-runnability check.

### Database tables

| Table | One row is… |
|---|---|
| `trade_flows` | China's rare-earth trade with one partner, in one direction, in one year (from `data1.xlsx`) |
| `electricity_generation` | One country's electricity from one source in one year (from `data2.xlsx`) |
| `partner_trade_energy` | One trade row plus the partner's power mix that year |
| `country_wind_imports` | One country in one year: rare-earth imports from China (kg), import growth %, wind generation, wind generation change and wind capacity. Also saved as `data/processed/country_wind_imports.csv` |
| `trade_wind_merged` | One `data1.xlsx` row (Import or Export) matched to `country_wind_imports` on country + year. Also saved as `data/processed/trade_wind_merged.csv` |

### How it works

| Stage | Module | What it does |
|---|---|---|
| Extract | `src/data_pipeline/extract.py` | Reads the Excel files listed in `config/app_config.yaml` with Pandas |
| Transform | `src/data_pipeline/transform.py` | Renames columns, repairs the swapped reporter header in `data1.xlsx`, maps country names between sources, builds `partner_trade_energy` and `country_wind_imports` |
| Validate | `src/data_pipeline/validate.py` | Pandera schemas: types, allowed values, ranges, uniqueness. Drops exact duplicates; rejects bad rows to `data/interim/` |
| Load | `src/data_pipeline/load.py` | SQLAlchemy tables with primary and foreign keys; replaces contents in one transaction and records before/after counts and checksums |
| Report | `src/data_pipeline/quality.py` | Builds the quality report |
| Orchestration | `src/data_pipeline/pipeline.py` | `run_pipeline()`: importable, used by the script, tests and notebooks |

### Re-runnability

Running the command twice with the same input doesn't duplicate rows or silently change counts.
Each run compares every table's row count and content checksum before and after loading. The
report's *Re-runnability check* table shows the result, and any change is logged as a warning.
`tests/test_data_pipeline.py::test_second_run_does_not_duplicate_or_change_rows` checks this automatically.

### Documentation

- [docs/ERD.md](docs/ERD.md): entity relationship diagram
- [docs/data_dictionary.md](docs/data_dictionary.md): every table and field, with type, key, source and business rule
- [docs/schema.sql](docs/schema.sql): generated `CREATE TABLE` statements
- [docs/setup.md](docs/setup.md): setup and supplying restricted data

### Other commands

```bash
uv run python scripts/setup_database.py                    # create empty tables only
uv run python scripts/setup_database.py --ddl docs/schema.sql   # regenerate schema SQL
uv run python scripts/make_sample_data.py                  # regenerate the synthetic sample
uv run pytest                                              # run the tests
```
