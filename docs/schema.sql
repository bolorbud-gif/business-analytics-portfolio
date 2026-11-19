-- Database schema (SQLite), generated from src/data_pipeline/load.py
-- and src/data_pipeline/views.py
-- Regenerate: uv run python scripts/setup_database.py --ddl docs/schema.sql

CREATE TABLE countries (
	country_id INTEGER NOT NULL,
	trade_name VARCHAR,
	ember_name VARCHAR,
	iso3 VARCHAR(3),
	area_type VARCHAR,
	PRIMARY KEY (country_id),
	CONSTRAINT ck_country_has_name CHECK (trade_name IS NOT NULL OR ember_name IS NOT NULL),
	CONSTRAINT ck_iso3_length CHECK (iso3 IS NULL OR length(iso3) = 3),
	UNIQUE (trade_name),
	UNIQUE (ember_name),
	UNIQUE (iso3)
);

CREATE TABLE energy_sources (
	source VARCHAR NOT NULL,
	is_aggregated BOOLEAN NOT NULL,
	PRIMARY KEY (source),
	CONSTRAINT ck_is_aggregated_boolean CHECK (is_aggregated IN (0, 1))
);

CREATE TABLE products (
	product_code VARCHAR(6) NOT NULL,
	product_description VARCHAR NOT NULL,
	quantity_unit VARCHAR NOT NULL,
	PRIMARY KEY (product_code),
	CONSTRAINT ck_product_code_length CHECK (length(product_code) = 6),
	CONSTRAINT ck_quantity_unit_kg CHECK (quantity_unit = 'kg')
);

CREATE TABLE electricity_generation (
	country_id INTEGER NOT NULL,
	year INTEGER NOT NULL,
	source VARCHAR NOT NULL,
	generation_twh FLOAT NOT NULL,
	generation_yoy_twh FLOAT,
	generation_share_pct FLOAT NOT NULL,
	generation_share_yoy_pp FLOAT,
	capacity_gw FLOAT,
	emissions_mtco2e FLOAT,
	emissions_yoy_mtco2e FLOAT,
	emissions_share_pct FLOAT,
	PRIMARY KEY (country_id, year, source),
	CONSTRAINT ck_capacity_non_negative CHECK (capacity_gw IS NULL OR capacity_gw >= 0),
	CONSTRAINT ck_generation_year_range CHECK (year BETWEEN 2000 AND 2030),
	CONSTRAINT ck_emissions_non_negative CHECK (emissions_mtco2e IS NULL OR emissions_mtco2e >= 0),
	CONSTRAINT ck_generation_non_negative CHECK (source IN ('Net imports', 'Demand') OR generation_twh >= 0),
	CONSTRAINT ck_generation_share_range CHECK (source IN ('Net imports', 'Demand') OR generation_share_pct BETWEEN 0 AND 100.5),
	FOREIGN KEY(country_id) REFERENCES countries (country_id),
	FOREIGN KEY(source) REFERENCES energy_sources (source)
);

CREATE INDEX ix_electricity_generation_source ON electricity_generation (source);

CREATE INDEX ix_electricity_generation_year ON electricity_generation (year);

CREATE TABLE trade_flows (
	reporter_id INTEGER NOT NULL,
	trade_flow VARCHAR NOT NULL,
	product_code VARCHAR(6) NOT NULL,
	year INTEGER NOT NULL,
	partner_id INTEGER NOT NULL,
	trade_value_usd BIGINT NOT NULL,
	quantity FLOAT NOT NULL,
	PRIMARY KEY (reporter_id, trade_flow, product_code, year, partner_id),
	CONSTRAINT ck_trade_flow CHECK (trade_flow IN ('Export', 'Import')),
	CONSTRAINT ck_trade_value_non_negative CHECK (trade_value_usd >= 0),
	CONSTRAINT ck_quantity_non_negative CHECK (quantity >= 0),
	CONSTRAINT ck_trade_year_range CHECK (year BETWEEN 2000 AND 2030),
	FOREIGN KEY(reporter_id) REFERENCES countries (country_id),
	FOREIGN KEY(product_code) REFERENCES products (product_code),
	FOREIGN KEY(partner_id) REFERENCES countries (country_id)
);

CREATE INDEX ix_trade_flows_partner_year ON trade_flows (partner_id, year);

CREATE INDEX ix_trade_flows_product_code ON trade_flows (product_code);

CREATE INDEX ix_trade_flows_year ON trade_flows (year);

-- View: computed from the tables above, stores nothing
CREATE VIEW electricity_generation_detail AS
SELECT c.ember_name AS country, c.iso3, e.year, c.area_type, e.source, s.is_aggregated,
       e.generation_twh, e.generation_yoy_twh,
       e.generation_yoy_twh / NULLIF(e.generation_twh - e.generation_yoy_twh, 0) * 100
           AS generation_yoy_pct,
       e.generation_share_pct, e.generation_share_yoy_pp, e.capacity_gw, e.emissions_mtco2e,
       e.emissions_yoy_mtco2e,
       e.emissions_yoy_mtco2e / NULLIF(e.emissions_mtco2e - e.emissions_yoy_mtco2e, 0) * 100
           AS emissions_yoy_pct,
       e.emissions_share_pct,
       e.emissions_mtco2e / NULLIF(e.generation_twh, 0) * 1000 AS emissions_intensity_g_per_kwh
FROM electricity_generation e
JOIN countries c ON c.country_id = e.country_id
JOIN energy_sources s ON s.source = e.source;

-- View: computed from the tables above, stores nothing
CREATE VIEW partner_trade_energy AS
SELECT r.trade_name AS reporter, t.trade_flow, t.product_code, t.year,
       p.trade_name AS partner, COALESCE(p.ember_name, p.trade_name) AS country,
       t.trade_value_usd / 1000.0 AS trade_value_kusd, t.quantity AS quantity_kg,
       t.trade_value_usd * 1.0 / NULLIF(t.quantity, 0) AS unit_value_usd_per_kg,
       tot.generation_twh AS total_generation_twh,
       ws.generation_twh AS wind_solar_twh,
       ren.generation_twh AS renewables_twh,
       ren.generation_twh / NULLIF(tot.generation_twh, 0) * 100 AS renewables_share_pct
FROM trade_flows t
JOIN countries r ON r.country_id = t.reporter_id
JOIN countries p ON p.country_id = t.partner_id
LEFT JOIN electricity_generation tot
       ON tot.country_id = t.partner_id AND tot.year = t.year AND tot.source = 'Total generation'
LEFT JOIN electricity_generation ws
       ON ws.country_id = t.partner_id AND ws.year = t.year AND ws.source = 'Wind and solar'
LEFT JOIN electricity_generation ren
       ON ren.country_id = t.partner_id AND ren.year = t.year AND ren.source = 'Renewables';

-- View: computed from the tables above, stores nothing
CREATE VIEW country_wind_imports AS
WITH years AS (SELECT year FROM trade_flows UNION SELECT year FROM electricity_generation),
     partners AS (SELECT DISTINCT partner_id FROM trade_flows
                  WHERE partner_id NOT IN (SELECT reporter_id FROM trade_flows)),
     imports AS (SELECT partner_id, year, SUM(quantity) AS kg FROM trade_flows
                 WHERE trade_flow = 'Export' GROUP BY partner_id, year)
SELECT c.trade_name AS partner, COALESCE(c.ember_name, c.trade_name) AS country, y.year,
       i.kg AS imports_from_china_kg,
       CASE WHEN prev.kg > 0 THEN (i.kg - prev.kg) / prev.kg * 100 END AS import_growth_pct,
       w.generation_twh AS wind_generation_twh,
       w.generation_yoy_twh AS wind_generation_change_twh,
       w.capacity_gw AS wind_capacity_gw
FROM partners pt
CROSS JOIN years y
JOIN countries c ON c.country_id = pt.partner_id
LEFT JOIN imports i ON i.partner_id = pt.partner_id AND i.year = y.year
LEFT JOIN imports prev ON prev.partner_id = pt.partner_id AND prev.year = y.year - 1
LEFT JOIN electricity_generation w
       ON w.country_id = pt.partner_id AND w.year = y.year AND w.source = 'Wind';

-- View: computed from the tables above, stores nothing
CREATE VIEW trade_wind_merged AS
SELECT r.trade_name AS reporter, t.trade_flow, t.product_code, pr.product_description, t.year,
       cw.partner, cw.country, t.trade_value_usd / 1000.0 AS trade_value_kusd, t.quantity,
       pr.quantity_unit,
       cw.imports_from_china_kg, cw.import_growth_pct, cw.wind_generation_twh,
       cw.wind_generation_change_twh, cw.wind_capacity_gw
FROM trade_flows t
JOIN countries r ON r.country_id = t.reporter_id
JOIN countries p ON p.country_id = t.partner_id
JOIN products pr ON pr.product_code = t.product_code
JOIN country_wind_imports cw ON cw.partner = p.trade_name AND cw.year = t.year;

-- View: computed from the tables above, stores nothing
CREATE VIEW trade_wind_wide AS
SELECT partner, country, year,
       SUM(CASE WHEN trade_flow = 'Export' THEN quantity END) AS imports_from_china_kg,
       SUM(CASE WHEN trade_flow = 'Export' THEN trade_value_kusd END)
           AS imports_from_china_value_kusd,
       SUM(CASE WHEN trade_flow = 'Import' THEN quantity END) AS exports_to_china_kg,
       SUM(CASE WHEN trade_flow = 'Import' THEN trade_value_kusd END)
           AS exports_to_china_value_kusd,
       MAX(import_growth_pct) AS import_growth_pct,
       MAX(wind_generation_twh) AS wind_generation_twh,
       MAX(wind_generation_change_twh) AS wind_generation_change_twh,
       MAX(wind_capacity_gw) AS wind_capacity_gw
FROM trade_wind_merged
GROUP BY partner, country, year;
