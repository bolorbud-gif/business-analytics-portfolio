# Data Dictionary

Database: `data/processed/rare_earth.db` (SQLite). Diagram: [ERD.md](ERD.md). SQL: [schema.sql](schema.sql).
Every rule marked **Validated** is a Pandera check in
[`src/data_pipeline/validate.py`](../src/data_pipeline/validate.py). Rows that fail one are rejected
(not loaded) and counted in the [quality report](quality_report.md).

**Key** column: `PK` = part of the primary key, `FK` = part of the foreign key to `trade_flows`.

## Sources

| Source file | Location | Contents | Coverage (real data) |
|---|---|---|---|
| `data1.xlsx`, sheet `By-HS6Product` | `data/raw/` (not committed) | China's trade in rare-earth compounds (HS 284690) by partner: value and quantity, exports and imports. Layout matches a WITS (World Bank) "By-HS6Product" export | 73 partners, 2020–2025, 227 rows |
| `data2.xlsx`, sheet `elec-gen by countries` | `data/raw/` (not committed) | Electricity generation, capacity and emissions by country and source. Layout matches Ember's yearly electricity data | 70 countries, 2020–2025, 6,729 rows |
| Synthetic sample | `data/sample/` (committed) | Same layouts, random values, planted bad records | 8 partners / 7 countries, 2022–2024 |

How to supply the real files: [setup.md](setup.md#supplying-the-real-data).

---

## `trade_flows`

**Grain:** China's trade with one partner, in one direction, for one product and year.
**Primary key:** (`reporter`, `trade_flow`, `product_code`, `year`, `partner`).
**Source:** `data1.xlsx`.

| Field | Type | Key | Source column | Description | Business rule |
|---|---|---|---|---|---|
| reporter | VARCHAR | PK | first column (header is the swapped value `China`) | Reporting country | **Validated:** must be `China`. A cell reading `Reporter` (header/cell swap in the source) is **repaired** to `China` |
| trade_flow | VARCHAR | PK | `TradeFlow` | Direction of trade, seen from China | **Validated:** `Export` or `Import` |
| product_code | VARCHAR(6) | PK | `ProductCode` | HS 6-digit product code | **Validated:** exactly 6 digits; stored as text so leading zeros survive |
| product_description | VARCHAR | | `Product Description` | HS product name | Required |
| year | INTEGER | PK | `Year` | Calendar year | **Validated:** 2000–2030 |
| partner | VARCHAR | PK | `Partner` | Partner country, World Bank naming | **Validated:** non-empty |
| trade_value_kusd | FLOAT | | `Trade Value 1000USD` | Trade value, thousand US dollars | **Validated:** ≥ 0 |
| quantity | FLOAT | | `Quantity` | Quantity traded | **Validated:** ≥ 0 |
| quantity_unit | VARCHAR | | `Quantity Unit` | Unit of `quantity`, lower-cased | **Validated:** must be `kg`, so quantities are comparable |

Table rules: **Validated** unique on the primary key. Exact duplicate rows are dropped, keeping the first copy.
Rows sharing a key but with different values are both rejected, because the correct one can't be chosen.

## `electricity_generation`

**Grain:** one country's electricity from one source in one year.
**Primary key:** (`country`, `year`, `source`).
**Source:** `data2.xlsx`.

| Field | Type | Key | Source column | Description | Business rule |
|---|---|---|---|---|---|
| country | VARCHAR | PK | `Area` | Country, Ember naming | Required |
| year | INTEGER | PK | `Year` | Calendar year | **Validated:** 2000–2030 |
| source | VARCHAR | PK | `Electricity source` | Solar, Wind, Hydro, Coal, Gas, …, plus totals (Total generation, Renewables, Wind and solar, Fossil, Clean) and balances (Net imports, Demand) | Required |
| iso3 | VARCHAR(3) | | `ISO 3 code` | ISO 3166 alpha-3 code | **Validated:** 3 capital letters |
| area_type | VARCHAR | | `Area type` | Area type (all rows: country or economy) | Required |
| is_aggregated | BOOLEAN | | `Is aggregated source` | True when the source is a sum of others (e.g. Renewables) | Don't add aggregated and non-aggregated sources together, or generation is double-counted |
| generation_twh | FLOAT | | `Generation (TWh)` | Electricity generated, TWh | **Validated:** ≥ 0, except `Net imports` (can be negative) and `Demand` |
| generation_yoy_twh | FLOAT | | `Generation YoY change (TWh)` | Change from previous year, TWh | Nullable (first year has no prior) |
| generation_yoy_pct | FLOAT | | `Generation YoY change (%)` | Change from previous year, % | Nullable |
| generation_share_pct | FLOAT | | `Share of generation (%)` | Share of the country's total generation, % | **Validated:** 0–100, except `Net imports` / `Demand`, which are measured against generation and can be below 0 or above 100 |
| generation_share_yoy_pp | FLOAT | | `Share of generation YoY change (% points)` | Change in share, percentage points | Nullable |
| capacity_gw | FLOAT | | `Capacity (GW)` | Installed capacity, GW | **Validated:** ≥ 0; nullable (not reported for balances) |
| emissions_mtco2e | FLOAT | | `Emissions (MtCO2e)` | Emissions, million tonnes CO2-equivalent | **Validated:** ≥ 0; nullable |
| emissions_yoy_mtco2e | FLOAT | | `Emissions YoY change (MtCO2e)` | Change in emissions from previous year | Nullable |
| emissions_yoy_pct | FLOAT | | `Emissions YoY change (%)` | Change in emissions, % | Nullable |
| emissions_share_pct | FLOAT | | `Share of emissions (%)` | Share of the country's power-sector emissions, % | Nullable |
| emissions_intensity_g_per_kwh | FLOAT | | `Emissions intensity (gCO2e/kWh)` | Emissions per unit generated | **Validated:** ≥ 0; nullable |

Table rules: **Validated** unique on the primary key. Exact duplicates are dropped and conflicting keys rejected, as for `trade_flows`.

## `partner_trade_energy` (derived analysis table)

**Grain:** one `trade_flows` row plus that partner's power mix in the same year.
**Primary key:** (`reporter`, `trade_flow`, `product_code`, `year`, `partner`).
**Foreign key:** the same five columns → `trade_flows`.
**Source:** built by `build_partner_trade_energy()` in
[`transform.py`](../src/data_pipeline/transform.py) from the *validated* rows of the two tables above.

| Field | Type | Key | Source | Description | Business rule |
|---|---|---|---|---|---|
| reporter | VARCHAR | PK, FK | `trade_flows.reporter` | Reporting country | Must exist in `trade_flows` (FK enforced) |
| trade_flow | VARCHAR | PK, FK | `trade_flows.trade_flow` | Export or Import | as above |
| product_code | VARCHAR(6) | PK, FK | `trade_flows.product_code` | HS6 code | as above |
| year | INTEGER | PK, FK | `trade_flows.year` | Calendar year | as above |
| partner | VARCHAR | PK, FK | `trade_flows.partner` | Partner, World Bank naming | as above |
| country | VARCHAR | | derived from `partner` | Partner name in Ember naming | Mapped with `PARTNER_TO_COUNTRY` in `transform.py` (10 names differ, e.g. `Korea, Rep.` → `South Korea`); otherwise unchanged |
| trade_value_kusd | FLOAT | | `trade_flows.trade_value_kusd` | Trade value, thousand USD | ≥ 0 |
| quantity_kg | FLOAT | | `trade_flows.quantity` | Quantity, kg | ≥ 0; unit already validated as kg |
| unit_value_usd_per_kg | FLOAT | | derived | `trade_value_kusd × 1000 ÷ quantity_kg` | NULL when quantity is 0 (no division by zero) |
| total_generation_twh | FLOAT | | `electricity_generation` where source = `Total generation` | Partner's total generation that year | NULL if the partner has no electricity data that year |
| wind_solar_twh | FLOAT | | `electricity_generation` where source = `Wind and solar` | Partner's wind + solar generation | NULL if no match |
| renewables_twh | FLOAT | | `electricity_generation` where source = `Renewables` | Partner's renewable generation | NULL if no match |
| renewables_share_pct | FLOAT | | derived | `renewables_twh ÷ total_generation_twh × 100` | **Validated:** 0–100; NULL if no match |

Table rules: the row count must equal `trade_flows`; if not, the run stops.
Unmatched partners are kept rather than dropped, so trade totals stay complete. They're listed in the quality report.

## `country_wind_imports` (derived analysis table)

**Grain:** one partner country in one year: rare-earth imports from China next to that country's wind power.
**Primary key:** (`partner`, `year`).
**Source:** built by `build_country_wind_imports()` in
[`transform.py`](../src/data_pipeline/transform.py) from the *validated* rows of `trade_flows`
and `electricity_generation`. Also exported to `data/processed/country_wind_imports.csv` (not committed).

Every partner (except China) gets a row for every year in the data, so the table is a complete panel.
A year with no trade record is NULL, not 0.

| Field | Type | Key | Source | Description | Business rule |
|---|---|---|---|---|---|
| partner | VARCHAR | PK | `trade_flows.partner` | Importing country, World Bank naming | `China` excluded (re-imports are not demand) |
| country | VARCHAR | | derived from `partner` | Same country, Ember naming | Mapped with `PARTNER_TO_COUNTRY` |
| year | INTEGER | PK | `trade_flows.year` ∪ `electricity_generation.year` | Calendar year | **Validated:** 2000–2030 |
| imports_from_china_kg | FLOAT | | `trade_flows.quantity` where `trade_flow = 'Export'` | Rare-earth compounds (HS 284690) the country bought from China, kg (sum over products) | China's **exports** are the partner's **imports**. NULL when no export is recorded that year. **Validated:** ≥ 0 |
| import_growth_pct | FLOAT | | derived | Year-on-year import growth: (this year − previous year) ÷ previous year × 100 | NULL when this year or the previous year is missing, or the previous year is 0. **Validated:** ≥ −100 |
| wind_generation_twh | FLOAT | | `electricity_generation.generation_twh` where `source = 'Wind'` | Wind electricity generated, TWh | NULL if no electricity data. **Validated:** ≥ 0 |
| wind_generation_change_twh | FLOAT | | `electricity_generation.generation_yoy_twh` where `source = 'Wind'` | Change in wind generation from the previous year, TWh | Taken from the source file. It equals this year minus last year (checked: 334 of 334 rows), and 2020 is filled from the provider's 2019 figure |
| wind_capacity_gw | FLOAT | | `electricity_generation.capacity_gw` where `source = 'Wind'` | Installed wind capacity, GW | NULL if not reported. **Validated:** ≥ 0 |

**Data limitation (real data):** `data1.xlsx` contains China's *exports* only for 2023 and 2024.
The other years hold China's imports instead. So `imports_from_china_kg` is filled for 2023–2024
only, and `import_growth_pct` for 2024 only (52 countries). Re-downloading `data1.xlsx` with
exports for every year fills the table automatically on the next run.

## `trade_wind_merged` (derived analysis table)

**Grain:** one `data1.xlsx` row (one `trade_flows` row) with the matching country-year from `country_wind_imports`.
**Primary key:** (`reporter`, `trade_flow`, `product_code`, `year`, `partner`).
**Foreign keys:** those five columns → `trade_flows`; (`partner`, `year`) → `country_wind_imports`.
**Source:** built by `build_trade_wind_merged()` in [`transform.py`](../src/data_pipeline/transform.py).
It joins validated `trade_flows` (the cleaned `data1.xlsx`) to `country_wind_imports` on
**country (`partner`) + year**, an inner join. Also exported to `data/processed/trade_wind_merged.csv` (not committed).

Unlike `country_wind_imports`, this table keeps **both** trade directions (Import and Export rows)
and the trade value in USD from `data1.xlsx`.

| Field | Type | Key | Source | Description | Business rule |
|---|---|---|---|---|---|
| reporter | VARCHAR | PK, FK | `data1.xlsx` first column | Reporting country | **Validated:** `China` |
| trade_flow | VARCHAR | PK, FK | `data1.xlsx` `TradeFlow` | `Export` = country buys from China; `Import` = China buys from the country | **Validated:** `Export` or `Import` |
| product_code | VARCHAR(6) | PK, FK | `data1.xlsx` `ProductCode` | HS6 code | **Validated:** 6 digits |
| product_description | VARCHAR | | `data1.xlsx` `Product Description` | HS product name | Required |
| year | INTEGER | PK, FK | `data1.xlsx` `Year` | Calendar year (join key) | **Validated:** 2000–2030 |
| partner | VARCHAR | PK, FK | `data1.xlsx` `Partner` | Country (join key), World Bank naming | **Validated:** not `China` |
| country | VARCHAR | | `country_wind_imports.country` | Same country, Ember naming | |
| trade_value_kusd | FLOAT | | `data1.xlsx` `Trade Value 1000USD` | Trade value, thousand USD | **Validated:** ≥ 0 |
| quantity | FLOAT | | `data1.xlsx` `Quantity` | Quantity traded | **Validated:** ≥ 0 |
| quantity_unit | VARCHAR | | `data1.xlsx` `Quantity Unit` | Unit | **Validated:** `kg` |
| imports_from_china_kg | FLOAT | | `country_wind_imports` | Country's imports from China that year, kg | Equals `quantity` on Export rows; NULL on Import rows' years unless an Export exists the same year |
| import_growth_pct | FLOAT | | `country_wind_imports` | (this year − previous year) ÷ previous year × 100 | Export-to-Export years only; never compares an Import year with an Export year |
| wind_generation_twh | FLOAT | | `country_wind_imports` | Wind generation, TWh | NULL if no electricity data |
| wind_generation_change_twh | FLOAT | | `country_wind_imports` | Change from previous year, TWh | NULL if no electricity data |
| wind_capacity_gw | FLOAT | | `country_wind_imports` | Installed wind capacity, GW | NULL if not reported |

Table rules: each `data1.xlsx` row appears **at most once**. The merge checks for many-to-one
and fails the run if rows are lost or duplicated. The only rows left out are China's trade with
itself (4 rows in the real data), which `country_wind_imports` excludes; the quality report lists them.

## `trade_wind_wide` (derived analysis table, "one sheet" view)

**Grain:** one country in one year, with both trade directions **side by side** instead of on separate rows.
**Primary key:** (`partner`, `year`).
**Foreign key:** (`partner`, `year`) → `country_wind_imports`.
**Source:** built by `build_trade_wind_wide()` in [`transform.py`](../src/data_pipeline/transform.py),
which pivots `trade_wind_merged` on `trade_flow`. Also exported as `data/processed/trade_wind_wide.csv`
and as a one-sheet Excel file, `data/processed/trade_wind_wide.xlsx` (sheet `trade_wind`). Neither is committed.

Direction names are from the **partner country's** point of view:

| Field | Type | Key | Source | Description | Business rule |
|---|---|---|---|---|---|
| partner | VARCHAR | PK, FK | `trade_wind_merged.partner` | Country, World Bank naming | **Validated:** not `China` |
| country | VARCHAR | | `trade_wind_merged.country` | Same country, Ember naming | |
| year | INTEGER | PK, FK | `trade_wind_merged.year` | Calendar year | **Validated:** 2000–2030 |
| imports_from_china_kg | FLOAT | | `quantity` where `trade_flow = 'Export'` | Rare-earth compounds the country bought from China, kg | NULL if no Export row that year. **Validated:** ≥ 0 |
| imports_from_china_value_kusd | FLOAT | | `trade_value_kusd` where `trade_flow = 'Export'` | Value of those imports, thousand USD | NULL if no Export row. **Validated:** ≥ 0 |
| exports_to_china_kg | FLOAT | | `quantity` where `trade_flow = 'Import'` | Rare-earth compounds China bought from the country, kg | NULL if no Import row. **Validated:** ≥ 0 |
| exports_to_china_value_kusd | FLOAT | | `trade_value_kusd` where `trade_flow = 'Import'` | Value of those exports, thousand USD | NULL if no Import row. **Validated:** ≥ 0 |
| import_growth_pct | FLOAT | | `trade_wind_merged` | Growth of imports from China: (this year − previous year) ÷ previous year × 100 | As in `country_wind_imports` |
| wind_generation_twh | FLOAT | | `trade_wind_merged` | Wind generation, TWh | |
| wind_generation_change_twh | FLOAT | | `trade_wind_merged` | Change from previous year, TWh | |
| wind_capacity_gw | FLOAT | | `trade_wind_merged` | Installed wind capacity, GW | |

Table rules: **Validated** every row has at least one direction filled. The row count must equal
the number of distinct country-years in `trade_wind_merged`; if not, the run stops.

**Data limitation (real data):** no country-year in `data1.xlsx` has both directions (Import rows
are 2020–2022 and 2025, Export rows 2023–2024), so each row currently has only one side filled.
The synthetic sample has both directions per year and shows the side-by-side layout working.
