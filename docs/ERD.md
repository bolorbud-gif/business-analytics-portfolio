# Entity Relationship Diagram

Database: SQLite file `data/processed/rare_earth.db`, built by `uv run python scripts/run_pipeline.py`.
Table definitions live in [`src/data_pipeline/load.py`](../src/data_pipeline/load.py); the
generated SQL is in [`schema.sql`](schema.sql). Field-level detail is in the
[data dictionary](data_dictionary.md).

```mermaid
erDiagram
    trade_flows ||--|| partner_trade_energy : "enriched as (FK, 1:1)"
    electricity_generation }o..o{ partner_trade_energy : "looked up by country + year"
    trade_flows }o..o| country_wind_imports : "Export rows summed by partner + year"
    electricity_generation |o..o| country_wind_imports : "Wind row by country + year"
    trade_flows ||--o| trade_wind_merged : "data1 row (FK)"
    country_wind_imports ||--o{ trade_wind_merged : "matched on country + year (FK)"
    trade_wind_merged }|..|| trade_wind_wide : "pivoted: Export + Import on one row"
    country_wind_imports ||--o| trade_wind_wide : "country + year (FK)"

    trade_flows {
        string reporter PK "always China"
        string trade_flow PK "Export or Import"
        string product_code PK "HS6, e.g. 284690"
        int year PK
        string partner PK "World Bank country name"
        string product_description
        float trade_value_kusd "thousand USD, >= 0"
        float quantity ">= 0"
        string quantity_unit "kg"
    }

    electricity_generation {
        string country PK "Ember country name"
        int year PK
        string source PK "Solar, Coal, Total generation..."
        string iso3 "ISO alpha-3"
        string area_type
        bool is_aggregated
        float generation_twh
        float generation_yoy_twh
        float generation_yoy_pct
        float generation_share_pct
        float generation_share_yoy_pp
        float capacity_gw "nullable"
        float emissions_mtco2e "nullable"
        float emissions_yoy_mtco2e
        float emissions_yoy_pct
        float emissions_share_pct
        float emissions_intensity_g_per_kwh "nullable"
    }

    partner_trade_energy {
        string reporter PK, FK
        string trade_flow PK, FK
        string product_code PK, FK
        int year PK, FK
        string partner PK, FK
        string country "partner mapped to Ember name"
        float trade_value_kusd
        float quantity_kg
        float unit_value_usd_per_kg "NULL if quantity is 0"
        float total_generation_twh "NULL if no match"
        float wind_solar_twh "NULL if no match"
        float renewables_twh "NULL if no match"
        float renewables_share_pct "NULL if no match"
    }

    country_wind_imports {
        string partner PK "importing country, excl. China"
        int year PK
        string country "Ember name"
        float imports_from_china_kg "NULL if not recorded"
        float import_growth_pct "(t - t-1) / t-1 x 100"
        float wind_generation_twh
        float wind_generation_change_twh
        float wind_capacity_gw
    }

    trade_wind_merged {
        string reporter PK, FK
        string trade_flow PK, FK "Export or Import"
        string product_code PK, FK
        int year PK, FK "join key"
        string partner PK, FK "join key, excl. China"
        string product_description
        string country
        float trade_value_kusd
        float quantity
        string quantity_unit
        float imports_from_china_kg
        float import_growth_pct
        float wind_generation_twh
        float wind_generation_change_twh
        float wind_capacity_gw
    }

    trade_wind_wide {
        string partner PK, FK
        int year PK, FK
        string country
        float imports_from_china_kg "China Export rows"
        float imports_from_china_value_kusd
        float exports_to_china_kg "China Import rows"
        float exports_to_china_value_kusd
        float import_growth_pct
        float wind_generation_twh
        float wind_generation_change_twh
        float wind_capacity_gw
    }
```

## Relationships

| From | To | Type | Enforced? | Rule |
|---|---|---|---|---|
| `partner_trade_energy` | `trade_flows` | Exactly one `partner_trade_energy` row per `trade_flows` row | **Yes**: composite foreign key on all 5 key columns (SQLite `PRAGMA foreign_keys = ON`) | The pipeline also checks that both tables have the same row count |
| `partner_trade_energy` | `electricity_generation` | Many-to-many lookup on `country` + `year` (each country-year has one row per source) | No: logical link only, because `electricity_generation`'s key also includes `source` | `country` comes from `partner` via the name map in `transform.py`. Partners with no match keep NULL electricity fields |
| `country_wind_imports` | `trade_flows` | One country-year summarizes 0 or more `Export` rows (`partner` + `year`) | No: aggregate, not a row-to-row link | Years with no Export row get NULL imports (not 0). China is excluded |
| `country_wind_imports` | `electricity_generation` | One country-year matches 0 or 1 `Wind` row (`country` + `year` + `source = 'Wind'`) | No: logical link | Countries with no wind data keep NULL wind fields |
| `trade_wind_merged` | `trade_flows` | Each `trade_flows` row appears at most once | **Yes**: composite FK on the 5 key columns | Only China's trade with itself is left out |
| `trade_wind_merged` | `country_wind_imports` | Many merged rows per country-year (one per trade flow) | **Yes**: FK on (`partner`, `year`) | This is the "match country and year" join |
| `trade_wind_wide` | `trade_wind_merged` | One wide row per country-year, made from its 1–2 merged rows | No: derived by pivot | Row count must equal distinct country-years in `trade_wind_merged` |
| `trade_wind_wide` | `country_wind_imports` | Each wide row matches one country-year | **Yes**: FK on (`partner`, `year`) | |

## Grain (what one row means)

| Table | One row is… | Kind |
|---|---|---|
| `trade_flows` | China's trade with one partner, in one direction, for one product and year | Fact (from `data1.xlsx`) |
| `electricity_generation` | One country's electricity from one source in one year | Fact (from `data2.xlsx`) |
| `partner_trade_energy` | One `trade_flows` row plus that partner's power mix in the same year | Derived analysis table |
| `country_wind_imports` | One country in one year: rare-earth imports from China, their growth, and wind power | Derived analysis table (panel) |
| `trade_wind_merged` | One `data1.xlsx` row plus that country's `country_wind_imports` values for the same year | Derived analysis table |
| `trade_wind_wide` | One country in one year with imports from China and exports to China side by side, plus wind | Derived analysis table (one sheet) |
