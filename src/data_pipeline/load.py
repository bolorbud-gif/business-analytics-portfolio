"""Load stage: the normalized (3NF) schema in SQLAlchemy, loading, and the analysis views."""

import hashlib
import logging
import sqlite3
from pathlib import Path

import pandas as pd
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Connection, Engine, Float, ForeignKey, Index,
    Integer, MetaData, String, Table, create_engine, event, inspect, text,
)
from sqlalchemy.exc import SQLAlchemyError

from src.data_pipeline import PipelineError
from src.data_pipeline.quality import QualityReport, missing_counts
from src.data_pipeline.validate import validate_view
from src.data_pipeline.views import VIEWS, create_views, drop_views

logger = logging.getLogger(__name__)

metadata = MetaData()

# --- Dimension tables (2NF: attributes that depend on part of a fact's key) ----------
countries = Table(
    "countries", metadata,
    Column("country_id", Integer, primary_key=True, autoincrement=False),
    Column("trade_name", String, unique=True),   # World Bank naming (data1.xlsx)
    Column("ember_name", String, unique=True),   # Ember naming (data2.xlsx)
    Column("iso3", String(3), unique=True),
    Column("area_type", String),
    CheckConstraint("trade_name IS NOT NULL OR ember_name IS NOT NULL", name="ck_country_has_name"),
    CheckConstraint("iso3 IS NULL OR length(iso3) = 3", name="ck_iso3_length"),
)

products = Table(
    "products", metadata,
    Column("product_code", String(6), primary_key=True),
    Column("product_description", String, nullable=False),
    Column("quantity_unit", String, nullable=False),
    CheckConstraint("length(product_code) = 6", name="ck_product_code_length"),
    CheckConstraint("quantity_unit = 'kg'", name="ck_quantity_unit_kg"),
)

energy_sources = Table(
    "energy_sources", metadata,
    Column("source", String, primary_key=True),
    Column("is_aggregated", Boolean, nullable=False),
    CheckConstraint("is_aggregated IN (0, 1)", name="ck_is_aggregated_boolean"),
)

# --- Fact tables ---------------------------------------------------------------------
trade_flows = Table(
    "trade_flows", metadata,
    Column("reporter_id", Integer, ForeignKey("countries.country_id"), primary_key=True),
    Column("trade_flow", String, primary_key=True),
    Column("product_code", String(6), ForeignKey("products.product_code"), primary_key=True),
    Column("year", Integer, primary_key=True),
    Column("partner_id", Integer, ForeignKey("countries.country_id"), primary_key=True),
    Column("trade_value_usd", BigInteger, nullable=False),  # whole US dollars: money is never REAL
    Column("quantity", Float, nullable=False),  # kg, a physical measure
    CheckConstraint("trade_flow IN ('Export', 'Import')", name="ck_trade_flow"),
    CheckConstraint("trade_value_usd >= 0", name="ck_trade_value_non_negative"),
    CheckConstraint("quantity >= 0", name="ck_quantity_non_negative"),
    CheckConstraint("year BETWEEN 2000 AND 2030", name="ck_trade_year_range"),
    # Indexes: reporter_id is already the first column of the primary key index, so it
    # is covered; the other FK columns and the year filter are not.
    Index("ix_trade_flows_partner_year", "partner_id", "year"),
    Index("ix_trade_flows_product_code", "product_code"),
    Index("ix_trade_flows_year", "year"),
)

electricity_generation = Table(
    "electricity_generation", metadata,
    Column("country_id", Integer, ForeignKey("countries.country_id"), primary_key=True),
    Column("year", Integer, primary_key=True),
    Column("source", String, ForeignKey("energy_sources.source"), primary_key=True),
    Column("generation_twh", Float, nullable=False),
    Column("generation_yoy_twh", Float),
    Column("generation_share_pct", Float, nullable=False),
    Column("generation_share_yoy_pp", Float),
    Column("capacity_gw", Float),
    Column("emissions_mtco2e", Float),
    Column("emissions_yoy_mtco2e", Float),
    Column("emissions_share_pct", Float),
    CheckConstraint("capacity_gw IS NULL OR capacity_gw >= 0", name="ck_capacity_non_negative"),
    CheckConstraint("year BETWEEN 2000 AND 2030", name="ck_generation_year_range"),
    CheckConstraint("emissions_mtco2e IS NULL OR emissions_mtco2e >= 0",
                    name="ck_emissions_non_negative"),
    # Net imports can be negative and Demand / Net imports are measured against
    # generation, so their shares can fall outside 0-100.
    CheckConstraint("source IN ('Net imports', 'Demand') OR generation_twh >= 0",
                    name="ck_generation_non_negative"),
    CheckConstraint("source IN ('Net imports', 'Demand') OR generation_share_pct BETWEEN 0 AND 100.5",
                    name="ck_generation_share_range"),
    # country_id is the first column of the primary key index, so it is covered.
    Index("ix_electricity_generation_source", "source"),
    Index("ix_electricity_generation_year", "year"),
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


def connect(db_path) -> sqlite3.Connection:
    """Open the SQLite file with plain sqlite3 (e.g. in a notebook) with foreign keys ON.

    SQLite turns foreign keys off for every new connection unless told otherwise, so a
    bare sqlite3.connect() would let writes break them. Use this instead.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(engine: Engine, rebuild: bool = False) -> None:
    """Create all tables if they do not exist yet (views are created by load()).

    rebuild=True drops views and tables and recreates them (data is reloaded by the
    pipeline). If an existing table's columns, indexes or CHECK constraints differ from
    the definitions here, or an analysis output still exists as a table (the pre-3NF
    layout), stop and ask for a rebuild instead of loading into the wrong shape.
    """
    try:
        if rebuild:
            with engine.begin() as conn:
                drop_views(conn)
                for name in set(VIEWS) & set(inspect(conn).get_table_names()):
                    conn.execute(text(f"DROP TABLE {name}"))
            metadata.drop_all(engine)
            logger.info("Dropped existing views and tables (--rebuild)")
        existing = inspect(engine)
        stored = set(existing.get_table_names())
        outdated = sorted(set(VIEWS) & stored)
        for table in metadata.sorted_tables:
            if table.name in stored:
                have = ({c["name"] for c in existing.get_columns(table.name)},
                        {i["name"] for i in existing.get_indexes(table.name)},
                        {c["name"] for c in existing.get_check_constraints(table.name)})
                want = (set(table.columns.keys()), {i.name for i in table.indexes},
                        {c.name for c in table.constraints if isinstance(c, CheckConstraint)})
                if have != want:
                    outdated.append(table.name)
        if outdated:
            raise PipelineError(
                f"The database has an outdated structure ({', '.join(outdated)}). "
                "Run again with --rebuild to recreate the tables."
            )
        metadata.create_all(engine)
    except SQLAlchemyError as exc:
        raise PipelineError(f"Could not create database schema: {exc}") from exc
    logger.info("Database schema ready: %s", ", ".join(metadata.tables))


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame rows as dicts with NaN turned into SQL NULL."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def snapshot(conn: Connection, name: str, key: list[str]):
    """Rows of a table or view sorted by key, their count and a short content checksum."""
    df = pd.read_sql(text(f"SELECT * FROM {name} ORDER BY {', '.join(key)}"), conn)
    if df.empty:
        return df, 0, None
    digest = hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes())
    return df, len(df), digest.hexdigest()[:12]


def _record(report, name, before, after, source=None):
    (_, rows_before, sum_before), (df, rows_after, sum_after) = before, after
    if rows_before and rows_after != rows_before:
        logger.warning("%s: row count changed from %s to %s since the last run",
                       name, rows_before, rows_after)
    elif rows_before and sum_after != sum_before:
        logger.warning("%s: same row count but values changed since the last run", name)
    logger.info("%s %s: %s rows (before: %s, content %s)", "View" if source else "Table", name,
                rows_after, rows_before, "unchanged" if sum_after == sum_before else "updated")
    if report:
        q = report.table(name, source or "")
        if source:  # views have no input stage
            q.rows_in = q.rows_valid = rows_after
            q.missing = missing_counts(df)
        q.rows_before_load, q.checksum_before = rows_before, sum_before
        q.rows_after_load, q.checksum_after = rows_after, sum_after


def load(
    engine: Engine, tables: dict[str, pd.DataFrame], report: QualityReport | None = None
) -> dict[str, pd.DataFrame]:
    """Replace the contents of every table and refresh the views, in one transaction.

    Child tables are emptied before parents and parents filled before children, so
    foreign keys hold throughout. The views are then recreated, read back and
    validated. Re-running with the same input gives identical tables and views; any
    change in row count between runs is logged, never silent. If anything fails, the
    transaction rolls back and the database is unchanged. Returns the views' rows.
    """
    ordered = [t for t in metadata.sorted_tables if t.name in tables]
    keys = {t.name: [c.name for c in t.primary_key.columns] for t in ordered}
    keys.update({name: key for name, (_, key) in VIEWS.items()})
    try:
        with engine.begin() as conn:
            existing_views = set(inspect(conn).get_view_names())
            before = {t.name: snapshot(conn, t.name, keys[t.name]) for t in ordered}
            before.update({v: snapshot(conn, v, keys[v]) if v in existing_views
                           else (None, 0, None) for v in VIEWS})
            for table in reversed(ordered):
                conn.execute(table.delete())
            for table in ordered:
                conn.execute(table.insert(), _records(tables[table.name]))
            if engine.dialect.name == "sqlite":
                orphans = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
                if orphans:  # defence in depth: FKs are enforced on insert already
                    raise PipelineError(f"Foreign key check failed: {orphans[:5]}")
            create_views(conn)

            for table in ordered:
                _record(report, table.name, before[table.name],
                        snapshot(conn, table.name, keys[table.name]))
            views = {}
            for name in VIEWS:
                after = snapshot(conn, name, keys[name])
                validate_view(name, after[0])  # raises -> rollback
                _record(report, name, before[name], after, source="view")
                views[name] = after[0]
    except SQLAlchemyError as exc:
        raise PipelineError(f"Database load failed, no changes were saved: {exc}") from exc
    return views
