-- Database schema (SQLite), generated from src/data_pipeline/load.py
-- Regenerate: uv run python scripts/setup_database.py --ddl docs/schema.sql

CREATE TABLE country_wind_imports (
	partner VARCHAR NOT NULL,
	country VARCHAR NOT NULL,
	year INTEGER NOT NULL,
	imports_from_china_kg FLOAT,
	import_growth_pct FLOAT,
	wind_generation_twh FLOAT,
	wind_generation_change_twh FLOAT,
	wind_capacity_gw FLOAT,
	PRIMARY KEY (partner, year)
);

CREATE TABLE electricity_generation (
	country VARCHAR NOT NULL,
	iso3 VARCHAR(3) NOT NULL,
	year INTEGER NOT NULL,
	area_type VARCHAR NOT NULL,
	source VARCHAR NOT NULL,
	is_aggregated BOOLEAN NOT NULL,
	generation_twh FLOAT NOT NULL,
	generation_yoy_twh FLOAT,
	generation_yoy_pct FLOAT,
	generation_share_pct FLOAT NOT NULL,
	generation_share_yoy_pp FLOAT,
	capacity_gw FLOAT,
	emissions_mtco2e FLOAT,
	emissions_yoy_mtco2e FLOAT,
	emissions_yoy_pct FLOAT,
	emissions_share_pct FLOAT,
	emissions_intensity_g_per_kwh FLOAT,
	PRIMARY KEY (country, year, source)
);

CREATE TABLE trade_flows (
	reporter VARCHAR NOT NULL,
	trade_flow VARCHAR NOT NULL,
	product_code VARCHAR(6) NOT NULL,
	product_description VARCHAR NOT NULL,
	year INTEGER NOT NULL,
	partner VARCHAR NOT NULL,
	trade_value_kusd FLOAT NOT NULL,
	quantity FLOAT NOT NULL,
	quantity_unit VARCHAR NOT NULL,
	PRIMARY KEY (reporter, trade_flow, product_code, year, partner)
);

CREATE TABLE partner_trade_energy (
	reporter VARCHAR NOT NULL,
	trade_flow VARCHAR NOT NULL,
	product_code VARCHAR(6) NOT NULL,
	year INTEGER NOT NULL,
	partner VARCHAR NOT NULL,
	country VARCHAR NOT NULL,
	trade_value_kusd FLOAT NOT NULL,
	quantity_kg FLOAT NOT NULL,
	unit_value_usd_per_kg FLOAT,
	total_generation_twh FLOAT,
	wind_solar_twh FLOAT,
	renewables_twh FLOAT,
	renewables_share_pct FLOAT,
	PRIMARY KEY (reporter, trade_flow, product_code, year, partner),
	FOREIGN KEY(reporter, trade_flow, product_code, year, partner) REFERENCES trade_flows (reporter, trade_flow, product_code, year, partner)
);

CREATE TABLE trade_wind_merged (
	reporter VARCHAR NOT NULL,
	trade_flow VARCHAR NOT NULL,
	product_code VARCHAR(6) NOT NULL,
	product_description VARCHAR NOT NULL,
	year INTEGER NOT NULL,
	partner VARCHAR NOT NULL,
	country VARCHAR NOT NULL,
	trade_value_kusd FLOAT NOT NULL,
	quantity FLOAT NOT NULL,
	quantity_unit VARCHAR NOT NULL,
	imports_from_china_kg FLOAT,
	import_growth_pct FLOAT,
	wind_generation_twh FLOAT,
	wind_generation_change_twh FLOAT,
	wind_capacity_gw FLOAT,
	PRIMARY KEY (reporter, trade_flow, product_code, year, partner),
	FOREIGN KEY(reporter, trade_flow, product_code, year, partner) REFERENCES trade_flows (reporter, trade_flow, product_code, year, partner),
	FOREIGN KEY(partner, year) REFERENCES country_wind_imports (partner, year)
);

CREATE TABLE trade_wind_wide (
	partner VARCHAR NOT NULL,
	country VARCHAR NOT NULL,
	year INTEGER NOT NULL,
	imports_from_china_kg FLOAT,
	imports_from_china_value_kusd FLOAT,
	exports_to_china_kg FLOAT,
	exports_to_china_value_kusd FLOAT,
	import_growth_pct FLOAT,
	wind_generation_twh FLOAT,
	wind_generation_change_twh FLOAT,
	wind_capacity_gw FLOAT,
	PRIMARY KEY (partner, year),
	FOREIGN KEY(partner, year) REFERENCES country_wind_imports (partner, year)
);
