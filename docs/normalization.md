# Normalization (1NF → 2NF → 3NF)

The database stores data in **third normal form**. The analysis outputs (`partner_trade_energy`,
`country_wind_imports`, `trade_wind_merged`, `trade_wind_wide`) are **SQL views**: they're
calculated from the normalized tables when read and store nothing. Diagram: [ERD.md](ERD.md).
Fields: [data_dictionary.md](data_dictionary.md).

Every dependency below was **tested on the real data** (227 trade rows, 6,729 electricity rows), not assumed.
The pipeline re-checks the 2NF dependencies on every run (`normalize()` in
[`transform.py`](../src/data_pipeline/transform.py)) and stops if one no longer holds, because
splitting the table would then lose data.

## Relationships between the entities

| Entity | Identified by | Related to |
|---|---|---|
| Country | `country_id`; has a trade name and/or an Ember name | reports trade (China), is a trade partner, generates electricity |
| Product | `product_code` (HS6) | is traded in trade flows |
| Energy source | `source` (Solar, Wind, Total generation, …) | appears in electricity generation |
| Trade flow | reporter + direction + product + year + partner | 1 reporter country, 1 partner country, 1 product |
| Electricity generation | country + year + source | 1 country, 1 energy source |

Cardinalities: one country has many trade flows as partner (and as reporter, for China) and
many electricity rows. One product has many trade flows, and one energy source has many electricity rows.
Trade and electricity relate to each other only **through country + year**, a many-to-many link,
which the views resolve.

## Before: the two source tables

`trade_flows` (from `data1.xlsx`), key (reporter, trade_flow, product_code, year, partner):
reporter, trade_flow, product_code, **product_description**, year, partner, trade_value_kusd,
quantity, **quantity_unit**

`electricity_generation` (from `data2.xlsx`), key (country, year, source): country, **iso3**,
year, **area_type**, source, **is_aggregated**, generation_twh, generation_yoy_twh,
**generation_yoy_pct**, generation_share_pct, generation_share_yoy_pp, capacity_gw,
emissions_mtco2e, emissions_yoy_mtco2e, **emissions_yoy_pct**, emissions_share_pct,
**emissions_intensity_g_per_kwh**

## 1NF: one value per cell

| Check | Result |
|---|---|
| Every cell holds a single value (no lists, no "A; B") | ✅ Both source tables. Commas inside names such as "Korea, Rep." or "Hydro, bioenergy and other renewables" are part of one name, not lists |
| Every table has a primary key; no duplicate rows | ✅ Enforced: Pandera uniqueness check, then PRIMARY KEY in SQLite |
| No repeating groups (the same kind of value spread over several columns) | ✅ In stored tables. The `trade_wind_wide` **view** deliberately pairs `imports_from_china_*` with `exports_to_china_*` for a one-sheet layout; it's a presentation view, not storage |
| Source problem | The header/cell swap in `data1.xlsx` (header `China`, one cell `Reporter`) put a value in the wrong place. It's repaired in the transform step |

## 2NF: every non-key column depends on the whole key

Partial dependencies found, each verified with "one value per determinant" on the real data:

| Table | Column | Depends only on | Evidence | Fix |
|---|---|---|---|---|
| trade_flows | product_description | product_code | 1 description per code | → `products` |
| trade_flows | quantity_unit | product_code | 1 unit per code | → `products` |
| electricity_generation | iso3 | country | 1 code per country, and 1 country per code | → `countries` |
| electricity_generation | area_type | country | 1 type per country | → `countries` |
| electricity_generation | is_aggregated | source | 1 flag per source | → `energy_sources` |

Country names were a related problem: the same country is "Korea, Rep." in `data1.xlsx` and
"South Korea" in `data2.xlsx`. That link lived in Python code. It now lives in the `countries` table:
one row per country with both names, and the facts refer to it by `country_id`.

## 3NF: no non-key column depends on another non-key column

Columns that are calculated from other columns **in the same row**:

| Column | Formula | Matches provider value | Fix |
|---|---|---|---|
| emissions_intensity_g_per_kwh | emissions_mtco2e ÷ generation_twh × 1000 | 5,641 of 5,641 rows (within 0.01) | not stored; recomputed in view `electricity_generation_detail` |
| generation_yoy_pct | generation_yoy_twh ÷ (generation_twh − generation_yoy_twh) × 100 | 6,048 of 6,048 (within 0.1 pp) | same |
| emissions_yoy_pct | emissions_yoy_mtco2e ÷ (emissions_mtco2e − emissions_yoy_mtco2e) × 100 | 5,221 of 5,221 (within 0.1 pp) | same |

The same rule removed calculated columns from the old analysis tables. For example, `unit_value_usd_per_kg`
(= value ÷ quantity) and `renewables_share_pct` (= renewables ÷ total) are now computed in views.

### Kept on purpose

These are provider values that depend on **other rows**, not other columns of the same row, so
3NF doesn't require removing them. They're kept because some can't be recomputed from what we store:

| Kept | Why |
|---|---|
| generation_yoy_twh, emissions_yoy_mtco2e | 2020 values use the provider's 2019 data, which isn't in the file |
| generation_share_pct, generation_share_yoy_pp, emissions_share_pct | Provider's official shares; recomputing gives the same result (5,912 of 5,912 rows within 0.1 pp) |
| Aggregate source rows (Total generation, Renewables, Wind and solar, …) | They are sums of other rows (e.g. Total generation = sum of the 9 base sources, 409 of 409). Kept as the provider's official totals and used by the views. Removing them goes beyond 3NF |

## After: the 3NF schema

| Table | Primary key | Non-key columns |
|---|---|---|
| `countries` | country_id | trade_name (unique), ember_name (unique), iso3 (unique), area_type |
| `products` | product_code | product_description, quantity_unit |
| `energy_sources` | source | is_aggregated |
| `trade_flows` | reporter_id, trade_flow, product_code, year, partner_id | trade_value_kusd, quantity |
| `electricity_generation` | country_id, year, source | generation_twh, generation_yoy_twh, generation_share_pct, generation_share_yoy_pp, capacity_gw, emissions_mtco2e, emissions_yoy_mtco2e, emissions_share_pct |

Foreign keys (enforced): `trade_flows.reporter_id` and `trade_flows.partner_id` → `countries`;
`trade_flows.product_code` → `products`; `electricity_generation.country_id` → `countries`;
`electricity_generation.source` → `energy_sources`.

## Verification

- **Nothing lost:** the `electricity_generation_detail` view rebuilds all 17 columns of
  `data2.xlsx`. 13 are identical, and the 3 recomputed ones match the provider in every row.
- **Same results:** the four analysis views were compared cell by cell with the tables the
  previous (non-normalized) version stored. They matched in every row and column (227, 432,
  223 and 223 rows).
- **Tests:** `tests/test_data_pipeline.py` checks that partial and same-row dependencies aren't
  stored, that normalization stops if a dependency breaks, that foreign keys are enforced, and
  that the analysis outputs are views, not tables.
