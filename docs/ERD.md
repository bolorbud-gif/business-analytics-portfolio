# Entity Relationship Diagram

Database: SQLite file `data/processed/rare_earth.db`, built by `uv run python scripts/run_pipeline.py`.
Table definitions live in [`src/data_pipeline/load.py`](../src/data_pipeline/load.py); the
generated SQL is in [`schema.sql`](schema.sql). Field-level detail is in the
[data dictionary](data_dictionary.md).

```mermaid
erDiagram
    trade_flows ||--|| partner_trade_energy : "enriched as (FK, 1:1)"
    electricity_generation }o..o{ partner_trade_energy : "looked up by country + year"

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
```

## Relationships

| From | To | Type | Enforced? | Rule |
|---|---|---|---|---|
| `partner_trade_energy` | `trade_flows` | Exactly one `partner_trade_energy` row per `trade_flows` row | **Yes**: composite foreign key on all 5 key columns (SQLite `PRAGMA foreign_keys = ON`) | The pipeline also checks that both tables have the same row count |
| `partner_trade_energy` | `electricity_generation` | Many-to-many lookup on `country` + `year` (each country-year has one row per source) | No: logical link only, because `electricity_generation`'s key also includes `source` | `country` comes from `partner` via the name map in `transform.py`. Partners with no match keep NULL electricity fields |

## Grain (what one row means)

| Table | One row is… | Kind |
|---|---|---|
| `trade_flows` | China's trade with one partner, in one direction, for one product and year | Fact (from `data1.xlsx`) |
| `electricity_generation` | One country's electricity from one source in one year | Fact (from `data2.xlsx`) |
| `partner_trade_energy` | One `trade_flows` row plus that partner's power mix in the same year | Derived analysis table |
