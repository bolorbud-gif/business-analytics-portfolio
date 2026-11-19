# Data Dictionary

Database: `data/processed/rare_earth.db` (SQLite). Diagram: [ERD.md](ERD.md).
Normal forms: [normalization.md](normalization.md). SQL: [schema.sql](schema.sql).

- **Stored tables** are in 3NF. **Views** are computed from them and store nothing.
- **Validated** rules are Pandera checks in [`validate.py`](../src/data_pipeline/validate.py), applied to the
  source rows *before* normalization. Rows that fail are rejected (not loaded) and counted in the
  [quality report](quality_report.md). Views are re-checked with the same rules after every load.
- **Key:** `PK` = primary key (part), `FK` = foreign key (enforced), `UK` = unique.

## Sources

| Source file | Location | Contents | Coverage (real data) |
|---|---|---|---|
| `data1.xlsx`, sheet `By-HS6Product` | `data/raw/` (not committed) | China's trade in rare-earth compounds (HS 284690) by partner: value and quantity, exports and imports. Layout matches a WITS (World Bank) "By-HS6Product" export | 73 partners, 2020–2025, 227 rows |
| `data2.xlsx`, sheet `elec-gen by countries` | `data/raw/` (not committed) | Electricity generation, capacity and emissions by country and source. Layout matches Ember's yearly electricity data | 70 countries, 2020–2025, 6,729 rows |
| Synthetic sample | `data/sample/` (committed) | Same layouts, random values, planted bad records | 8 partners / 7 countries, 2022–2024 |

How to supply the real files: [setup.md](setup.md#supplying-the-real-data).

---

# Stored tables

## `countries`

**Grain:** one real country. **PK:** `country_id`. **Source:** trade names from `data1.xlsx`
(reporter and partners), Ember names and codes from `data2.xlsx`, linked by `PARTNER_TO_COUNTRY` in
[`transform.py`](../src/data_pipeline/transform.py).

| Field | Type | Key | Source | Description | Business rule |
|---|---|---|---|---|---|
| country_id | INTEGER | PK | generated | Surrogate id, numbered in name order | Same input gives the same ids (re-run safe) |
| trade_name | VARCHAR | UK | `data1.xlsx` `Partner` / reporter | World Bank name, e.g. `Korea, Rep.` | NULL for countries with electricity data only |
| ember_name | VARCHAR | UK | `data2.xlsx` `Area` | Ember name, e.g. `South Korea` | NULL for partners with no electricity data (e.g. Peru) |
| iso3 | VARCHAR(3) | UK | `data2.xlsx` `ISO 3 code` | ISO 3166 alpha-3 | Was repeated on every electricity row (2NF). **Validated:** 3 capital letters |
| area_type | VARCHAR | | `data2.xlsx` `Area type` | Area type | Was repeated on every electricity row (2NF) |

Rule: two trade names may not map to the same Ember country; the run stops if they do.

## `products`

**Grain:** one HS6 product. **PK:** `product_code`. **Source:** `data1.xlsx`.

| Field | Type | Key | Source | Description | Business rule |
|---|---|---|---|---|---|
| product_code | VARCHAR(6) | PK | `ProductCode` | HS 6-digit code | **Validated:** 6 digits; text, so leading zeros survive |
| product_description | VARCHAR | | `Product Description` | HS product name | Was repeated on every trade row (2NF). Must be one description per code, or the run stops |
| quantity_unit | VARCHAR | | `Quantity Unit` | Unit of `trade_flows.quantity` | **Validated:** `kg`. One unit per code, or the run stops |

## `energy_sources`

**Grain:** one electricity source. **PK:** `source`. **Source:** `data2.xlsx`.

| Field | Type | Key | Source | Description | Business rule |
|---|---|---|---|---|---|
| source | VARCHAR | PK | `Electricity source` | Solar, Wind, Hydro, …, totals (Total generation, Renewables, Wind and solar, Fossil, Clean) and balances (Net imports, Demand) | |
| is_aggregated | BOOLEAN | | `Is aggregated source` | True when the source is a sum of others | Was repeated on every electricity row (2NF). Don't add aggregated and base sources together |

## `trade_flows`

**Grain:** China's trade with one partner, in one direction, for one product and year.
**PK:** (`reporter_id`, `trade_flow`, `product_code`, `year`, `partner_id`). **Source:** `data1.xlsx`.

| Field | Type | Key | Source | Description | Business rule |
|---|---|---|---|---|---|
| reporter_id | INTEGER | PK, FK → countries | first column (header is the swapped value `China`) | Reporting country | **Validated:** must be China. The `Reporter` cell (header/cell swap) is **repaired** |
| trade_flow | VARCHAR | PK | `TradeFlow` | Direction from China's view: `Export` = China sells, `Import` = China buys | **Validated:** `Export` or `Import` |
| product_code | VARCHAR(6) | PK, FK → products | `ProductCode` | HS6 code | |
| year | INTEGER | PK | `Year` | Calendar year | **Validated:** 2000–2030 |
| partner_id | INTEGER | PK, FK → countries | `Partner` | Partner country | **Validated:** name non-empty |
| trade_value_kusd | FLOAT | | `Trade Value 1000USD` | Trade value, thousand USD | **Validated:** ≥ 0 |
| quantity | FLOAT | | `Quantity` | Quantity, in `products.quantity_unit` (kg) | **Validated:** ≥ 0 |

Rules: **Validated** unique on the key. Exact duplicate rows are dropped, keeping the first copy.
Rows sharing a key but with different values are both rejected.

## `electricity_generation`

**Grain:** one country's electricity from one source in one year.
**PK:** (`country_id`, `year`, `source`). **Source:** `data2.xlsx`.

| Field | Type | Key | Source | Description | Business rule |
|---|---|---|---|---|---|
| country_id | INTEGER | PK, FK → countries | `Area` | Country | |
| year | INTEGER | PK | `Year` | Calendar year | **Validated:** 2000–2030 |
| source | VARCHAR | PK, FK → energy_sources | `Electricity source` | Source | |
| generation_twh | FLOAT | | `Generation (TWh)` | Generation, TWh | **Validated:** ≥ 0, except Net imports / Demand |
| generation_yoy_twh | FLOAT | | `Generation YoY change (TWh)` | Change from previous year | Nullable. Kept: 2020 uses the provider's 2019 value |
| generation_share_pct | FLOAT | | `Share of generation (%)` | Share of the country's total generation | **Validated:** 0–100, except Net imports / Demand |
| generation_share_yoy_pp | FLOAT | | `Share of generation YoY change (% points)` | Change in share, percentage points | Nullable |
| capacity_gw | FLOAT | | `Capacity (GW)` | Installed capacity | **Validated:** ≥ 0; nullable |
| emissions_mtco2e | FLOAT | | `Emissions (MtCO2e)` | Emissions, Mt CO2e | **Validated:** ≥ 0; nullable |
| emissions_yoy_mtco2e | FLOAT | | `Emissions YoY change (MtCO2e)` | Change in emissions | Nullable |
| emissions_share_pct | FLOAT | | `Share of emissions (%)` | Share of the country's power-sector emissions | Nullable |

**Not stored (3NF):** `Generation YoY change (%)`, `Emissions YoY change (%)` and
`Emissions intensity (gCO2e/kWh)` are calculated from other columns of the same row. They are
recomputed in `electricity_generation_detail`, and match the provider's values in every row.

---

# Views (computed on read)

Definitions: [`views.py`](../src/data_pipeline/views.py). Each is validated after every load with the
rules of the table it replaced. "NULL, not zero" means a value that isn't recorded is left empty, so it never reads as zero.

## `electricity_generation_detail`

`data2.xlsx` as it was: one row per country, year and source, with **all 17 original columns**.
`country`, `iso3` and `area_type` come from `countries`, and `is_aggregated` from `energy_sources`.
13 columns come straight from storage; these 3 are recomputed:

| Field | Formula |
|---|---|
| generation_yoy_pct | generation_yoy_twh ÷ (generation_twh − generation_yoy_twh) × 100 |
| emissions_yoy_pct | emissions_yoy_mtco2e ÷ (emissions_mtco2e − emissions_yoy_mtco2e) × 100 |
| emissions_intensity_g_per_kwh | emissions_mtco2e ÷ generation_twh × 1000 |

All three are NULL when the divisor is 0.

## `partner_trade_energy`

**Grain:** one `trade_flows` row plus the partner's power mix that year (227 rows).
**Key:** reporter, trade_flow, product_code, year, partner.

| Field | Source / formula | Rule |
|---|---|---|
| reporter, trade_flow, product_code, year | `trade_flows` | |
| partner | `countries.trade_name` | |
| country | `countries.ember_name`, else trade name | |
| trade_value_kusd, quantity_kg | `trade_flows` | |
| unit_value_usd_per_kg | trade_value_kusd × 1000 ÷ quantity | NULL when quantity is 0 |
| total_generation_twh, wind_solar_twh, renewables_twh | `electricity_generation` for Total generation / Wind and solar / Renewables | NULL if no electricity data for that partner-year |
| renewables_share_pct | renewables ÷ total × 100 | **Validated:** 0–100 |

## `country_wind_imports`

**Grain:** one partner country (every partner except reporters, i.e. China) × every year (432 rows).
**Key:** partner, year.

| Field | Source / formula | Rule |
|---|---|---|
| partner, country | `countries` | China excluded: buying from itself is re-imports |
| year | every year in `trade_flows` or `electricity_generation` | complete panel |
| imports_from_china_kg | sum of `trade_flows.quantity` where trade_flow = `Export` | China's exports are the partner's imports. NULL, not zero, when not recorded |
| import_growth_pct | (this year − previous year) ÷ previous year × 100 | NULL if either year is missing or the previous year is 0. **Validated:** ≥ −100 |
| wind_generation_twh, wind_generation_change_twh, wind_capacity_gw | `electricity_generation` where source = `Wind` (generation, generation_yoy_twh, capacity_gw) | NULL if no data |

**Data limitation (real data):** `data1.xlsx` has Export rows only for 2023–2024, so imports are
filled for those years and growth for 2024 only.

## `trade_wind_merged`

**Grain:** one `data1.xlsx` row matched to `country_wind_imports` on **country + year** (223 rows).
**Key:** reporter, trade_flow, product_code, year, partner.

Columns: reporter, trade_flow, product_code, product_description, year, partner, country,
trade_value_kusd, quantity, quantity_unit (all from `data1.xlsx` via `trade_flows` + `products`),
then imports_from_china_kg, import_growth_pct, wind_generation_twh, wind_generation_change_twh and
wind_capacity_gw (from `country_wind_imports`). Both trade directions are kept. The only `data1.xlsx` rows
left out are China trading with itself (4 rows), and the quality report lists them.

## `trade_wind_wide`

**Grain:** one country-year with both directions **side by side** (223 rows). **Key:** partner, year.
Also exported as `data/processed/trade_wind_wide.xlsx` (one sheet, `trade_wind`) and `.csv`.

| Field | Source / formula |
|---|---|
| partner, country, year | `trade_wind_merged` |
| imports_from_china_kg, imports_from_china_value_kusd | quantity / value of the `Export` row (country buys from China) |
| exports_to_china_kg, exports_to_china_value_kusd | quantity / value of the `Import` row (China buys from the country) |
| import_growth_pct, wind_generation_twh, wind_generation_change_twh, wind_capacity_gw | `trade_wind_merged` |

**Validated:** every row has at least one direction. In the real data no country-year has both
directions (Import rows are 2020–2022 and 2025, Export rows 2023–2024); the sample shows both side by side.
