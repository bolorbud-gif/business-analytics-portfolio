# Data Quality Report

Generated automatically by `scripts/run_pipeline.py`. Do not edit by hand.

- **Run started:** 2026-11-18T23:19:41
- **Status:** SUCCESS
- **Raw data:** `data/raw`
- **Database:** `sqlite:///data/processed/rare_earth.db`

## Summary

| Table | Source | Rows in | Repaired | Duplicates dropped | Rejected | Loaded |
|---|---|---:|---:|---:|---:|---:|
| `trade_flows` | data1.xlsx | 227 | 1 | 0 | 0 | 227 |
| `electricity_generation` | data2.xlsx | 6729 | 0 | 0 | 0 | 6729 |
| `countries` | normalized | 73 | 0 | 0 | 0 | 73 |
| `products` | normalized | 1 | 0 | 0 | 0 | 1 |
| `energy_sources` | normalized | 17 | 0 | 0 | 0 | 17 |
| `electricity_generation_detail` | view | 6729 | 0 | 0 | 0 | 6729 |
| `partner_trade_energy` | view | 227 | 0 | 0 | 0 | 227 |
| `country_wind_imports` | view | 432 | 0 | 0 | 0 | 432 |
| `trade_wind_merged` | view | 223 | 0 | 0 | 0 | 223 |
| `trade_wind_wide` | view | 223 | 0 | 0 | 0 | 223 |

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
| generation_share_yoy_pp | 2 | 0.03% |
| capacity_gw | 1162 | 17.27% |
| emissions_mtco2e | 409 | 6.08% |
| emissions_yoy_mtco2e | 411 | 6.11% |
| emissions_share_pct | 409 | 6.08% |

**`countries`** (73 rows)

| Column | Missing | % |
|---|---:|---:|
| ember_name | 3 | 4.11% |
| iso3 | 3 | 4.11% |
| area_type | 3 | 4.11% |

**`products`** (1 rows)

No missing values.

**`energy_sources`** (17 rows)

No missing values.

**`electricity_generation_detail`** (6729 rows)

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

**`trade_wind_merged`** (223 rows)

| Column | Missing | % |
|---|---:|---:|
| imports_from_china_kg | 103 | 46.19% |
| import_growth_pct | 171 | 76.68% |
| wind_generation_twh | 20 | 8.97% |
| wind_generation_change_twh | 20 | 8.97% |
| wind_capacity_gw | 22 | 9.87% |

**`trade_wind_wide`** (223 rows)

| Column | Missing | % |
|---|---:|---:|
| imports_from_china_kg | 103 | 46.19% |
| imports_from_china_value_kusd | 103 | 46.19% |
| exports_to_china_kg | 120 | 53.81% |
| exports_to_china_value_kusd | 120 | 53.81% |
| import_growth_pct | 171 | 76.68% |
| wind_generation_twh | 20 | 8.97% |
| wind_generation_change_twh | 20 | 8.97% |
| wind_capacity_gw | 22 | 9.87% |

## Re-runnability check

Each run replaces table contents in one transaction. Row counts and a content
checksum are taken before and after loading; on a repeat run with the same
input, both must be identical.

| Table | Rows before | Rows after | Checksum before | Checksum after | Result |
|---|---:|---:|---|---|---|
| `trade_flows` | 227 | 227 | `ef78033727bc` | `ef78033727bc` | Unchanged (no duplicates) |
| `electricity_generation` | 6729 | 6729 | `e8a03d3980ed` | `e8a03d3980ed` | Unchanged (no duplicates) |
| `countries` | 73 | 73 | `4a176ebaa365` | `4a176ebaa365` | Unchanged (no duplicates) |
| `products` | 1 | 1 | `c325b6472e82` | `c325b6472e82` | Unchanged (no duplicates) |
| `energy_sources` | 17 | 17 | `6e8601522c31` | `6e8601522c31` | Unchanged (no duplicates) |
| `electricity_generation_detail` | 6729 | 6729 | `e1c8ab9ed759` | `e1c8ab9ed759` | Unchanged (no duplicates) |
| `partner_trade_energy` | 227 | 227 | `c825714e89d6` | `c825714e89d6` | Unchanged (no duplicates) |
| `country_wind_imports` | 432 | 432 | `e11e49327bc3` | `e11e49327bc3` | Unchanged (no duplicates) |
| `trade_wind_merged` | 223 | 223 | `3d6e7d13383d` | `3d6e7d13383d` | Unchanged (no duplicates) |
| `trade_wind_wide` | 223 | 223 | `30c506681d47` | `30c506681d47` | Unchanged (no duplicates) |

## Notes

- Normalized to 3NF: 73 countries (70 matched across both sources), 1 product(s), 17 energy sources. Not stored because they are computed from the same row (3NF): generation_yoy_pct, emissions_yoy_pct, emissions_intensity_g_per_kwh; recomputed in electricity_generation_detail.
- partner_trade_energy: 15 row(s) have NULL electricity fields: no electricity data for 8 partner(s) in those years: Korea, Dem. Rep., Lao PDR, Mozambique, Myanmar, Other Asia, nes, Peru, Ukraine, Venezuela.
- country_wind_imports: imports from China recorded for 120 of 432 country-years (years [2023, 2024]); import growth computed for 52. Other years have no Export rows in data1.xlsx, so they are NULL, not zero.
- trade_wind_merged: 4 data1.xlsx row(s) not matched to country_wind_imports and left out (partner China: the reporter trading with itself is re-imports).
- trade_wind_wide: 0 country-year(s) have both directions, 120 only imports from China, 103 only exports to China.
