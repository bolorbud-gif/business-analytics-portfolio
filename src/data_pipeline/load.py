"""Load stage: define the database schema with SQLAlchemy and write validated tables."""

import hashlib
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import (
    Boolean, Column, Connection, Engine, Float, ForeignKeyConstraint, Integer, MetaData, String,
    Table, create_engine, event, inspect, select,
)
from sqlalchemy.exc import SQLAlchemyError

from src.data_pipeline import PipelineError
from src.data_pipeline.quality import QualityReport

logger = logging.getLogger(__name__)

metadata = MetaData()

trade_flows = Table(
    "trade_flows", metadata,
    Column("reporter", String, primary_key=True),
    Column("trade_flow", String, primary_key=True),
    Column("product_code", String(6), primary_key=True),
    Column("product_description", String, nullable=False),
    Column("year", Integer, primary_key=True),
    Column("partner", String, primary_key=True),
    Column("trade_value_kusd", Float, nullable=False),
    Column("quantity", Float, nullable=False),
    Column("quantity_unit", String, nullable=False),
)

electricity_generation = Table(
    "electricity_generation", metadata,
    Column("country", String, primary_key=True),
    Column("iso3", String(3), nullable=False),
    Column("year", Integer, primary_key=True),
    Column("area_type", String, nullable=False),
    Column("source", String, primary_key=True),
    Column("is_aggregated", Boolean, nullable=False),
    Column("generation_twh", Float, nullable=False),
    Column("generation_yoy_twh", Float),
    Column("generation_yoy_pct", Float),
    Column("generation_share_pct", Float, nullable=False),
    Column("generation_share_yoy_pp", Float),
    Column("capacity_gw", Float),
    Column("emissions_mtco2e", Float),
    Column("emissions_yoy_mtco2e", Float),
    Column("emissions_yoy_pct", Float),
    Column("emissions_share_pct", Float),
    Column("emissions_intensity_g_per_kwh", Float),
)

partner_trade_energy = Table(
    "partner_trade_energy", metadata,
    Column("reporter", String, primary_key=True),
    Column("trade_flow", String, primary_key=True),
    Column("product_code", String(6), primary_key=True),
    Column("year", Integer, primary_key=True),
    Column("partner", String, primary_key=True),
    Column("country", String, nullable=False),
    Column("trade_value_kusd", Float, nullable=False),
    Column("quantity_kg", Float, nullable=False),
    Column("unit_value_usd_per_kg", Float),
    Column("total_generation_twh", Float),
    Column("wind_solar_twh", Float),
    Column("renewables_twh", Float),
    Column("renewables_share_pct", Float),
    ForeignKeyConstraint(
        ["reporter", "trade_flow", "product_code", "year", "partner"],
        ["trade_flows.reporter", "trade_flows.trade_flow", "trade_flows.product_code",
         "trade_flows.year", "trade_flows.partner"],
    ),
)

country_wind_imports = Table(
    "country_wind_imports", metadata,
    Column("partner", String, primary_key=True),
    Column("country", String, nullable=False),
    Column("year", Integer, primary_key=True),
    Column("imports_from_china_kg", Float),
    Column("import_growth_pct", Float),
    Column("wind_generation_twh", Float),
    Column("wind_generation_change_twh", Float),
    Column("wind_capacity_gw", Float),
)

trade_wind_merged = Table(
    "trade_wind_merged", metadata,
    Column("reporter", String, primary_key=True),
    Column("trade_flow", String, primary_key=True),
    Column("product_code", String(6), primary_key=True),
    Column("product_description", String, nullable=False),
    Column("year", Integer, primary_key=True),
    Column("partner", String, primary_key=True),
    Column("country", String, nullable=False),
    Column("trade_value_kusd", Float, nullable=False),
    Column("quantity", Float, nullable=False),
    Column("quantity_unit", String, nullable=False),
    Column("imports_from_china_kg", Float),
    Column("import_growth_pct", Float),
    Column("wind_generation_twh", Float),
    Column("wind_generation_change_twh", Float),
    Column("wind_capacity_gw", Float),
    ForeignKeyConstraint(
        ["reporter", "trade_flow", "product_code", "year", "partner"],
        ["trade_flows.reporter", "trade_flows.trade_flow", "trade_flows.product_code",
         "trade_flows.year", "trade_flows.partner"],
    ),
    ForeignKeyConstraint(
        ["partner", "year"],
        ["country_wind_imports.partner", "country_wind_imports.year"],
    ),
)


def get_engine(url: str, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine. For SQLite, make sure the folder exists."""
    if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, echo=echo)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys = ON")  # SQLite leaves FKs off by default
    return engine


def create_schema(engine: Engine, rebuild: bool = False) -> None:
    """Create all tables if they do not exist yet.

    rebuild=True drops and recreates them (data is reloaded by the pipeline). If an
    existing table's columns differ from the definitions here, stop and ask for a
    rebuild instead of loading into the wrong shape.
    """
    try:
        if rebuild:
            metadata.drop_all(engine)
            logger.info("Dropped existing tables (--rebuild)")
        existing = inspect(engine)
        for table in metadata.sorted_tables:
            if existing.has_table(table.name):
                have = {c["name"] for c in existing.get_columns(table.name)}
                if have != set(table.columns.keys()):
                    raise PipelineError(
                        f"Table {table.name!r} in the database has an outdated structure. "
                        "Run again with --rebuild to recreate the tables."
                    )
        metadata.create_all(engine)
    except SQLAlchemyError as exc:
        raise PipelineError(f"Could not create database schema: {exc}") from exc
    logger.info("Database schema ready: %s", ", ".join(metadata.tables))


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame rows as dicts with NaN turned into SQL NULL."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def table_snapshot(conn: Connection, table: Table) -> tuple[int, str | None]:
    """Row count and a short content checksum (rows sorted by primary key)."""
    df = pd.read_sql(select(table).order_by(*table.primary_key.columns), conn)
    if df.empty:
        return 0, None
    digest = hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes())
    return len(df), digest.hexdigest()[:12]


def load(
    engine: Engine, tables: dict[str, pd.DataFrame], report: QualityReport | None = None
) -> dict[str, int]:
    """Replace the contents of each table in a single transaction.

    Child tables are emptied before parents and parents filled before children, so
    foreign keys hold throughout. Re-running with the same input gives identical
    tables; any change in row count between runs is logged, never silent. If
    anything fails, the transaction rolls back and the database is unchanged.
    """
    ordered = [t for t in metadata.sorted_tables if t.name in tables]
    counts = {}
    try:
        with engine.begin() as conn:
            before = {t.name: table_snapshot(conn, t) for t in ordered}
            for table in reversed(ordered):
                conn.execute(table.delete())
            for table in ordered:
                conn.execute(table.insert(), _records(tables[table.name]))
            for table in ordered:
                rows_before, sum_before = before[table.name]
                rows_after, sum_after = table_snapshot(conn, table)
                counts[table.name] = rows_after
                if rows_before and rows_after != rows_before:
                    logger.warning("%s: row count changed from %s to %s since the last run",
                                   table.name, rows_before, rows_after)
                elif rows_before and sum_after != sum_before:
                    logger.warning("%s: same row count but values changed since the last run",
                                   table.name)
                logger.info("Loaded %s rows into %s (before: %s, content %s)", rows_after,
                            table.name, rows_before,
                            "unchanged" if sum_after == sum_before else "updated")
                if report:
                    q = report.table(table.name)
                    q.rows_before_load, q.checksum_before = rows_before, sum_before
                    q.rows_after_load, q.checksum_after = rows_after, sum_after
    except SQLAlchemyError as exc:
        raise PipelineError(f"Database load failed, no changes were saved: {exc}") from exc
    return counts
