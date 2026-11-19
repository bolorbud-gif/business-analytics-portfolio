"""Analysis views over the normalized (3NF) tables.

Views store nothing: they are computed from countries, products, energy_sources,
trade_flows and electricity_generation every time they are read, so they can never
disagree with the stored data. Listed in dependency order.
"""

from sqlalchemy import Connection, inspect, text

COUNTRY = "COALESCE({t}.ember_name, {t}.trade_name)"

VIEWS: dict[str, tuple[str, list[str]]] = {
    # Electricity as in data2.xlsx: names instead of ids, and the 3NF-dropped columns
    # recomputed from the stored ones.
    "electricity_generation_detail": ("""
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
JOIN energy_sources s ON s.source = e.source
""", ["country", "year", "source"]),

    # Every trade row with the partner's power mix that year.
    "partner_trade_energy": (f"""
SELECT r.trade_name AS reporter, t.trade_flow, t.product_code, t.year,
       p.trade_name AS partner, {COUNTRY.format(t="p")} AS country,
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
       ON ren.country_id = t.partner_id AND ren.year = t.year AND ren.source = 'Renewables'
""", ["reporter", "trade_flow", "product_code", "year", "partner"]),

    # Panel: every partner (except reporters, i.e. China) x every year. Imports from
    # China = China's Export rows; NULL when not recorded (missing is not zero).
    "country_wind_imports": (f"""
WITH years AS (SELECT year FROM trade_flows UNION SELECT year FROM electricity_generation),
     partners AS (SELECT DISTINCT partner_id FROM trade_flows
                  WHERE partner_id NOT IN (SELECT reporter_id FROM trade_flows)),
     imports AS (SELECT partner_id, year, SUM(quantity) AS kg FROM trade_flows
                 WHERE trade_flow = 'Export' GROUP BY partner_id, year)
SELECT c.trade_name AS partner, {COUNTRY.format(t="c")} AS country, y.year,
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
       ON w.country_id = pt.partner_id AND w.year = y.year AND w.source = 'Wind'
""", ["partner", "year"]),

    # Every data1.xlsx row matched to country_wind_imports on country + year.
    "trade_wind_merged": ("""
SELECT r.trade_name AS reporter, t.trade_flow, t.product_code, pr.product_description, t.year,
       cw.partner, cw.country, t.trade_value_usd / 1000.0 AS trade_value_kusd, t.quantity,
       pr.quantity_unit,
       cw.imports_from_china_kg, cw.import_growth_pct, cw.wind_generation_twh,
       cw.wind_generation_change_twh, cw.wind_capacity_gw
FROM trade_flows t
JOIN countries r ON r.country_id = t.reporter_id
JOIN countries p ON p.country_id = t.partner_id
JOIN products pr ON pr.product_code = t.product_code
JOIN country_wind_imports cw ON cw.partner = p.trade_name AND cw.year = t.year
""", ["reporter", "trade_flow", "product_code", "year", "partner"]),

    # trade_wind_merged with Export and Import side by side: one row per country-year.
    "trade_wind_wide": ("""
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
GROUP BY partner, country, year
""", ["partner", "year"]),
}


def view_ddl() -> list[str]:
    return [f"CREATE VIEW {name} AS{sql.rstrip()};" for name, (sql, _) in VIEWS.items()]


def drop_views(conn: Connection) -> None:
    existing = set(inspect(conn).get_view_names())
    for name in reversed(list(VIEWS)):
        if name in existing:
            conn.execute(text(f"DROP VIEW {name}"))


def create_views(conn: Connection) -> None:
    """(Re)create every view so its definition always matches this code."""
    drop_views(conn)
    for statement in view_ddl():
        conn.execute(text(statement))
