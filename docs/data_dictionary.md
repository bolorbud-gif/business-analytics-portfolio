# Data Dictionary

## Sources (`data/raw/`, not committed to git)

| File | Contents | Coverage |
|---|---|---|
| `data1.xlsx` | China's trade in rare-earth compounds (HS 284690) by partner country: trade value and quantity, exports and imports | 73 partners, 2020–2025, 227 rows |
| `data2.xlsx` | Electricity generation, capacity and emissions by country and source | 70 countries, 2020–2025, 6,729 rows |

**Known data issue:** in `data1.xlsx` the first column's header reads `China` and one row
(Poland, 2024, Export) reads `Reporter`: the header and a cell are swapped. The transform
step renames the column to `reporter` and restores `China` in that row (logged as a warning).

## Database tables (`data/processed/rare_earth.db`)

### `trade_flows`
One row per reporter, trade flow, product, year and partner. Primary key: all five.

| Column | Type | Description | Validation |
|---|---|---|---|
| reporter | text | Reporting country | must be `China` |
| trade_flow | text | Direction of trade | `Export` or `Import` |
| product_code | text | HS6 product code | 6 digits |
| product_description | text | HS6 product description | |
| year | integer | Calendar year | 2000–2030 |
| partner | text | Partner country (World Bank naming) | non-empty |
| trade_value_kusd | real | Trade value, thousand USD | ≥ 0 |
| quantity | real | Quantity traded | ≥ 0 |
| quantity_unit | text | Unit of `quantity` | must be `kg` |

### `electricity_generation`
One row per country, year and electricity source. Primary key: country, year, source.

| Column | Type | Description | Validation |
|---|---|---|---|
| country | text | Country (Ember naming) | |
| iso3 | text | ISO 3166 alpha-3 code | 3 capital letters |
| year | integer | Calendar year | 2000–2030 |
| area_type | text | Area type | |
| source | text | Electricity source (Solar, Coal, Total generation, …) | |
| is_aggregated | boolean | Source is a sum of other sources (e.g. Renewables) | |
| generation_twh | real | Generation, TWh | ≥ 0, except Net imports / Demand |
| generation_yoy_twh | real | Year-on-year change, TWh | nullable |
| generation_yoy_pct | real | Year-on-year change, % | nullable |
| generation_share_pct | real | Share of total generation, % | 0–100, except Net imports / Demand |
| generation_share_yoy_pp | real | Change in share, percentage points | nullable |
| capacity_gw | real | Installed capacity, GW | ≥ 0, nullable |
| emissions_mtco2e | real | Emissions, MtCO2e | ≥ 0, nullable |
| emissions_yoy_mtco2e | real | Year-on-year change in emissions, MtCO2e | nullable |
| emissions_yoy_pct | real | Year-on-year change in emissions, % | nullable |
| emissions_share_pct | real | Share of total emissions, % | nullable |
| emissions_intensity_g_per_kwh | real | Emissions intensity, gCO2e/kWh | ≥ 0, nullable |

### `partner_trade_energy` (analysis table)
`trade_flows` joined with each partner's power mix in the same year. One row per partner,
year and trade flow; row count must equal `trade_flows`.

| Column | Type | Description |
|---|---|---|
| partner | text | Partner country (trade naming) |
| country | text | Matching country name in the electricity data |
| year | integer | Calendar year |
| trade_flow | text | `Export` or `Import` |
| trade_value_kusd | real | Trade value, thousand USD |
| quantity_kg | real | Quantity, kg |
| unit_value_usd_per_kg | real | Trade value ÷ quantity, USD per kg (NULL if quantity is 0) |
| total_generation_twh | real | Partner's total electricity generation, TWh |
| wind_solar_twh | real | Partner's wind + solar generation, TWh |
| renewables_twh | real | Partner's renewable generation, TWh |
| renewables_share_pct | real | Renewables ÷ total generation, % |

The electricity columns are NULL for partners with no electricity data for that year
(e.g. Peru, Venezuela, "Other Asia, nes"); the pipeline logs which partners these are.
Ten country names that differ between the sources are mapped in
`PARTNER_TO_COUNTRY` in `src/data_pipeline/transform.py`.
