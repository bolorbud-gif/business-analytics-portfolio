"""Load stage: define the database schema with SQLAlchemy and write validated tables."""

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import (
    Boolean, Column, Engine, Float, Integer, MetaData, String, Table, create_engine, func,
    select,
)
from sqlalchemy.exc import SQLAlchemyError

from src.data_pipeline import PipelineError

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
    Column("partner", String, primary_key=True),
    Column("country", String, nullable=False),
    Column("year", Integer, primary_key=True),
    Column("trade_flow", String, primary_key=True),
    Column("trade_value_kusd", Float, nullable=False),
    Column("quantity_kg", Float, nullable=False),
    Column("unit_value_usd_per_kg", Float),
    Column("total_generation_twh", Float),
    Column("wind_solar_twh", Float),
    Column("renewables_twh", Float),
    Column("renewables_share_pct", Float),
)


def get_engine(url: str, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine. For SQLite, make sure the folder exists."""
    if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, echo=echo)


def create_schema(engine: Engine) -> None:
    """Create all tables if they do not exist yet."""
    try:
        metadata.create_all(engine)
    except SQLAlchemyError as exc:
        raise PipelineError(f"Could not create database schema: {exc}") from exc
    logger.info("Database schema ready: %s", ", ".join(metadata.tables))


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame rows as dicts with NaN turned into SQL NULL."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def load(engine: Engine, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Replace the contents of each table in a single transaction.

    Re-running the pipeline gives the same result (no duplicate rows), and if any
    insert fails nothing is changed.
    """
    counts = {}
    try:
        with engine.begin() as conn:
            for name, df in tables.items():
                table = metadata.tables[name]
                conn.execute(table.delete())
                conn.execute(table.insert(), _records(df))
                counts[name] = conn.execute(select(func.count()).select_from(table)).scalar_one()
                logger.info("Loaded %s rows into %s", counts[name], name)
    except SQLAlchemyError as exc:
        raise PipelineError(f"Database load failed, no changes were saved: {exc}") from exc
    return counts
