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
