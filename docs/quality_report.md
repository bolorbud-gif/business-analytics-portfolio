# Data Quality Report

Generated automatically by `scripts/run_pipeline.py`. Do not edit by hand.

- **Run started:** 2026-11-18T21:54:07
- **Status:** SUCCESS
- **Raw data:** `data/raw`
- **Database:** `sqlite:///data/processed/rare_earth.db`

## Summary

| Table | Source | Rows in | Repaired | Duplicates dropped | Rejected | Loaded |
|---|---|---:|---:|---:|---:|---:|
| `trade_flows` | data1.xlsx | 227 | 1 | 0 | 0 | 227 |
| `electricity_generation` | data2.xlsx | 6729 | 0 | 0 | 0 | 6729 |
| `partner_trade_energy` | derived | 227 | 0 | 0 | 0 | 227 |
| `country_wind_imports` | derived | 432 | 0 | 0 | 0 | 432 |

## Action taken on bad records

| Problem | Detected in | Action |
|---|---|---|
| Header/cell swap in reporter column (data1.xlsx) | Transform | Repaired: column renamed to `reporter`, header value restored in the row; logged |
| Exact duplicate rows | Validate | First copy kept, other copies dropped; counted |
| Row breaks a validation rule (bad value, wrong unit, range, key conflict) | Validate (Pandera) | Rejected: not loaded; saved with the reason to `data/interim/rejected_<table>.csv` |
| Rejected share above `max_rejected_pct` | Validate | Run stops before loading; database left unchanged |
| Missing file, missing column, database error | Any stage | Run stops; database left unchanged (load is one transaction) |
| Trade partner with no electricity data that year | Transform | Kept; electricity columns left NULL; partners listed under Notes |

## Repairs and rejected records

- `trade_flows` repaired: 1 row(s) had reporter 'Reporter' (header/cell swap); set to 'China'

## Missingness (loaded data)

Columns not listed have no missing values.

**`trade_flows`** (227 rows)

No missing values.

**`electricity_generation`** (6729 rows)

| Column | Missing | % |
|---|---:|---:|
| generation_yoy_twh | 2 | 0.03% |
| generation_yoy_pct | 681 | 10.12% |
| generation_share_yoy_pp | 2 | 0.03% |
| capacity_gw | 1162 | 17.27% |
| emissions_mtco2e | 409 | 6.08% |
| emissions_yoy_mtco2e | 411 | 6.11% |
| emissions_yoy_pct | 1508 | 22.41% |
| emissions_share_pct | 409 | 6.08% |
| emissions_intensity_g_per_kwh | 1088 | 16.17% |

**`partner_trade_energy`** (227 rows)

| Column | Missing | % |
|---|---:|---:|
| total_generation_twh | 15 | 6.61% |
| wind_solar_twh | 15 | 6.61% |
| renewables_twh | 15 | 6.61% |
| renewables_share_pct | 15 | 6.61% |

**`country_wind_imports`** (432 rows)

| Column | Missing | % |
|---|---:|---:|
| imports_from_china_kg | 312 | 72.22% |
| import_growth_pct | 380 | 87.96% |
| wind_generation_twh | 35 | 8.10% |
| wind_generation_change_twh | 36 | 8.33% |
| wind_capacity_gw | 42 | 9.72% |

## Re-runnability check

Each run replaces table contents in one transaction. Row counts and a content
checksum are taken before and after loading; on a repeat run with the same
input, both must be identical.

| Table | Rows before | Rows after | Checksum before | Checksum after | Result |
|---|---:|---:|---|---|---|
| `trade_flows` | 227 | 227 | `7bad92af32de` | `7bad92af32de` | Unchanged (no duplicates) |
| `electricity_generation` | 6729 | 6729 | `0424f3b57e67` | `0424f3b57e67` | Unchanged (no duplicates) |
| `partner_trade_energy` | 227 | 227 | `9be0998409ca` | `9be0998409ca` | Unchanged (no duplicates) |
| `country_wind_imports` | 432 | 432 | `e11e49327bc3` | `e11e49327bc3` | Unchanged (no duplicates) |

## Notes

- 15 partner_trade_energy row(s) have NULL electricity fields: no electricity data for 8 partner(s) in those years: Korea, Dem. Rep., Lao PDR, Mozambique, Myanmar, Other Asia, nes, Peru, Ukraine, Venezuela.
- country_wind_imports: imports from China recorded for 120 of 432 country-years (years [2023, 2024]); import growth computed for 52. Other years have no Export rows in data1.xlsx, so they are NULL, not zero.
