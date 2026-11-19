# Data Quality Report

Generated automatically by `scripts/run_pipeline.py`. Do not edit by hand.

- **Run started:** 2026-11-18T21:12:26
- **Status:** SUCCESS
- **Raw data:** `data/sample`
- **Database:** `sqlite:///data/processed/rare_earth_sample.db`

## Summary

| Table | Source | Rows in | Repaired | Duplicates dropped | Rejected | Loaded |
|---|---|---:|---:|---:|---:|---:|
| `trade_flows` | data1.xlsx | 49 | 1 | 1 | 2 | 46 |
| `electricity_generation` | data2.xlsx | 231 | 0 | 0 | 1 | 230 |
| `partner_trade_energy` | derived | 46 | 0 | 0 | 0 | 46 |

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
- `trade_flows`: 1 exact duplicate row(s) dropped
- `trade_flows` rejected 1 row(s): quantity_unit: isin(['kg'])
- `trade_flows` rejected 1 row(s): trade_value_kusd: greater_than_or_equal_to(0)
- `electricity_generation` rejected 1 row(s): generation_twh must be >= 0 (except Net imports / Demand)

## Missingness (loaded data)

Columns not listed have no missing values.

**`trade_flows`** (46 rows)

No missing values.

**`electricity_generation`** (230 rows)

| Column | Missing | % |
|---|---:|---:|
| generation_yoy_twh | 76 | 33.04% |
| generation_yoy_pct | 76 | 33.04% |
| capacity_gw | 42 | 18.26% |
| emissions_mtco2e | 42 | 18.26% |
| emissions_yoy_mtco2e | 230 | 100.00% |
| emissions_yoy_pct | 230 | 100.00% |
| emissions_share_pct | 230 | 100.00% |
| emissions_intensity_g_per_kwh | 42 | 18.26% |

**`partner_trade_energy`** (46 rows)

| Column | Missing | % |
|---|---:|---:|
| total_generation_twh | 6 | 13.04% |
| wind_solar_twh | 6 | 13.04% |
| renewables_twh | 6 | 13.04% |
| renewables_share_pct | 6 | 13.04% |

## Re-runnability check

Each run replaces table contents in one transaction. Row counts and a content
checksum are taken before and after loading; on a repeat run with the same
input, both must be identical.

| Table | Rows before | Rows after | Checksum before | Checksum after | Result |
|---|---:|---:|---|---|---|
| `trade_flows` | 46 | 46 | `0367c6c00e23` | `0367c6c00e23` | Unchanged (no duplicates) |
| `electricity_generation` | 230 | 230 | `6b0956041732` | `6b0956041732` | Unchanged (no duplicates) |
| `partner_trade_energy` | 46 | 46 | `a0f809414c80` | `a0f809414c80` | Unchanged (no duplicates) |

## Notes

- 6 partner_trade_energy row(s) have NULL electricity fields: no electricity data for 1 partner(s) in those years: Peru.
