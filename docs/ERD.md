# Entity Relationship Diagram

Database: SQLite file `data/processed/rare_earth.db`, built by `uv run python scripts/run_pipeline.py`.
The stored tables are in **third normal form**; see [normalization.md](normalization.md) for the analysis.
Table definitions live in [`src/data_pipeline/load.py`](../src/data_pipeline/load.py) and views in
[`src/data_pipeline/views.py`](../src/data_pipeline/views.py). The generated SQL is in [`schema.sql`](schema.sql).
Field-level detail is in the [data dictionary](data_dictionary.md).

## Stored tables (3NF)

```mermaid
erDiagram
    countries ||--o{ trade_flows : "reports (reporter_id)"
    countries ||--o{ trade_flows : "is partner in (partner_id)"
    products ||--o{ trade_flows : "is traded in"
    countries ||--o{ electricity_generation : "generates"
    energy_sources ||--o{ electricity_generation : "is source of"

    countries {
        int country_id PK
        string trade_name UK "data1.xlsx name, e.g. Korea, Rep."
        string ember_name UK "data2.xlsx name, e.g. South Korea"
        string iso3 UK
        string area_type
    }

    products {
        string product_code PK "HS6, e.g. 284690"
        string product_description
        string quantity_unit "kg"
    }

    energy_sources {
        string source PK "Solar, Wind, Total generation..."
        bool is_aggregated
    }

    trade_flows {
        int reporter_id PK, FK "China"
        string trade_flow PK "Export or Import"
        string product_code PK, FK
        int year PK
        int partner_id PK, FK
        bigint trade_value_usd "whole USD, exact integer"
        float quantity "kg"
    }

    electricity_generation {
        int country_id PK, FK
        int year PK
        string source PK, FK
        float generation_twh
        float generation_yoy_twh
        float generation_share_pct
        float generation_share_yoy_pp
        float capacity_gw
        float emissions_mtco2e
        float emissions_yoy_mtco2e
        float emissions_share_pct
    }
```

### Relationships

| Parent | Child | Cardinality | Enforced? |
|---|---|---|---|
| `countries` | `trade_flows` (as reporter) | 1 : many | **Yes**: FK `reporter_id` |
| `countries` | `trade_flows` (as partner) | 1 : many | **Yes**: FK `partner_id` |
| `products` | `trade_flows` | 1 : many | **Yes**: FK `product_code` |
| `countries` | `electricity_generation` | 1 : many | **Yes**: FK `country_id` |
| `energy_sources` | `electricity_generation` | 1 : many | **Yes**: FK `source` |
| `trade_flows` | `electricity_generation` | many : many through `countries` + `year` | Resolved in the views |

SQLite leaves foreign keys off by default, separately for **every connection**. The pipeline turns them on
for each of its connections (`PRAGMA foreign_keys = ON`) and runs `PRAGMA foreign_key_check` before
committing. For your own scripts and notebooks, open the database with
`src.data_pipeline.load.connect()`, which does the same; a bare `sqlite3.connect()` would
let orphan rows in. CHECK constraints also block negative money or quantities and unknown trade
directions at the database level.

## Analysis views (computed, not stored)

Each view is a saved `SELECT` over the tables above, so it can never disagree with them.
They're queried like tables (`SELECT * FROM trade_wind_wide`), and the pipeline also exports
three of them to CSV/Excel.

```mermaid
flowchart LR
    C[(countries)] --> D[electricity_generation_detail]
    S[(energy_sources)] --> D
    E[(electricity_generation)] --> D
    T[(trade_flows)] --> P[partner_trade_energy]
    C --> P
    E --> P
    T --> W[country_wind_imports]
    C --> W
    E --> W
    T --> M[trade_wind_merged]
    PR[(products)] --> M
    W --> M
    M --> X[trade_wind_wide]
```

| View | Grain (one row is…) | Built from |
|---|---|---|
| `electricity_generation_detail` | one country, year and source, as in `data2.xlsx` (names, iso3, and the 3 recomputed 3NF columns) | electricity_generation + countries + energy_sources |
| `partner_trade_energy` | one trade flow plus the partner's power mix that year | trade_flows + countries + electricity_generation |
| `country_wind_imports` | one partner country (except China) in one year: imports from China, growth, wind | trade_flows + countries + electricity_generation (Wind) |
| `trade_wind_merged` | one `data1.xlsx` row matched to `country_wind_imports` on country + year | trade_flows + products + country_wind_imports |
| `trade_wind_wide` | one country-year with Export and Import side by side | trade_wind_merged |
