"""Validate stage: Pandera schemas that every table must pass before loading."""

import logging

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from src.data_pipeline import PipelineError

logger = logging.getLogger(__name__)

YEAR_RANGE = pa.Check.in_range(2000, 2030)
NON_NEGATIVE = pa.Check.ge(0)

# Sources that are not a share of generation, so their share can be < 0 or > 100.
BALANCE_SOURCES = {"Net imports", "Demand"}

trade_schema = pa.DataFrameSchema(
    {
        "reporter": pa.Column(str, pa.Check.isin(["China"])),
        "trade_flow": pa.Column(str, pa.Check.isin(["Export", "Import"])),
        "product_code": pa.Column(str, pa.Check.str_matches(r"^\d{6}$")),
        "product_description": pa.Column(str),
        "year": pa.Column(int, YEAR_RANGE),
        "partner": pa.Column(str, pa.Check.str_length(min_value=1)),
        "trade_value_kusd": pa.Column(float, NON_NEGATIVE),
        "quantity": pa.Column(float, NON_NEGATIVE),
        "quantity_unit": pa.Column(str, pa.Check.isin(["kg"])),
    },
    unique=["reporter", "trade_flow", "product_code", "year", "partner"],
    strict=True,
    coerce=True,
    name="trade_flows",
)

electricity_schema = pa.DataFrameSchema(
    {
        "country": pa.Column(str),
        "iso3": pa.Column(str, pa.Check.str_matches(r"^[A-Z]{3}$")),
        "year": pa.Column(int, YEAR_RANGE),
        "area_type": pa.Column(str),
        "source": pa.Column(str),
        "is_aggregated": pa.Column(bool),
        "generation_twh": pa.Column(float),
        "generation_yoy_twh": pa.Column(float, nullable=True),
        "generation_yoy_pct": pa.Column(float, nullable=True),
        "generation_share_pct": pa.Column(float),
        "generation_share_yoy_pp": pa.Column(float, nullable=True),
        "capacity_gw": pa.Column(float, NON_NEGATIVE, nullable=True),
        "emissions_mtco2e": pa.Column(float, NON_NEGATIVE, nullable=True),
        "emissions_yoy_mtco2e": pa.Column(float, nullable=True),
        "emissions_yoy_pct": pa.Column(float, nullable=True),
        "emissions_share_pct": pa.Column(float, nullable=True),
        "emissions_intensity_g_per_kwh": pa.Column(float, NON_NEGATIVE, nullable=True),
    },
    checks=[
        pa.Check(
            lambda df: df["source"].isin(BALANCE_SOURCES) | (df["generation_twh"] >= 0),
            element_wise=False,
            error="generation_twh must be >= 0 (except Net imports / Demand)",
        ),
        pa.Check(
            lambda df: df["source"].isin(BALANCE_SOURCES)
            | df["generation_share_pct"].between(0, 100.5),
            element_wise=False,
            error="generation_share_pct must be 0-100 (except Net imports / Demand)",
        ),
    ],
    unique=["country", "year", "source"],
    strict=True,
    coerce=True,
    name="electricity_generation",
)

partner_trade_energy_schema = pa.DataFrameSchema(
    {
        "partner": pa.Column(str),
        "country": pa.Column(str),
        "year": pa.Column(int, YEAR_RANGE),
        "trade_flow": pa.Column(str, pa.Check.isin(["Export", "Import"])),
        "trade_value_kusd": pa.Column(float, NON_NEGATIVE),
        "quantity_kg": pa.Column(float, NON_NEGATIVE),
        "unit_value_usd_per_kg": pa.Column(float, NON_NEGATIVE, nullable=True),
        "total_generation_twh": pa.Column(float, NON_NEGATIVE, nullable=True),
        "wind_solar_twh": pa.Column(float, NON_NEGATIVE, nullable=True),
        "renewables_twh": pa.Column(float, NON_NEGATIVE, nullable=True),
        "renewables_share_pct": pa.Column(float, pa.Check.in_range(0, 100.5), nullable=True),
    },
    unique=["partner", "year", "trade_flow"],
    strict=True,
    coerce=True,
    name="partner_trade_energy",
)

SCHEMAS = {
    "trade_flows": trade_schema,
    "electricity_generation": electricity_schema,
    "partner_trade_energy": partner_trade_energy_schema,
}


def validate_table(name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Validate one table. Collects every failure, logs them, then raises PipelineError."""
    try:
        validated = SCHEMAS[name].validate(df, lazy=True)
    except SchemaErrors as exc:
        cases = exc.failure_cases
        logger.error("Validation failed for %s: %s problem(s)", name, len(cases))
        for _, row in cases.head(20).iterrows():
            logger.error(
                "  column=%s check=%s value=%s row=%s",
                row["column"], row["check"], row["failure_case"], row["index"],
            )
        raise PipelineError(f"Validation failed for table {name!r}; see log for details") from exc
    logger.info("Validated %s: %s rows passed all checks", name, len(validated))
    return validated


def validate(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Validate every table, plus cross-table checks."""
    validated = {name: validate_table(name, df) for name, df in tables.items()}
    if len(validated["partner_trade_energy"]) != len(validated["trade_flows"]):
        raise PipelineError("partner_trade_energy row count differs from trade_flows (bad join)")
    return validated
