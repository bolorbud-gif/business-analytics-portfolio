"""Validate stage: Pandera schemas that every table must pass before loading."""

import logging
from collections import Counter
from pathlib import Path

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from src.data_pipeline import PipelineError
from src.data_pipeline.quality import QualityReport, missing_counts

logger = logging.getLogger(__name__)

YEAR_RANGE = pa.Check.in_range(2000, 2030)
NON_NEGATIVE = pa.Check.ge(0)
# Money is stored as INTEGER whole US dollars, so a value in thousand USD may have at most
# 3 decimals; anything finer would be rounded away when stored.
WHOLE_DOLLARS = pa.Check(
    lambda s: ((s * 1000).round() - s * 1000).abs() < 1e-6,
    error="trade_value_kusd must have at most 3 decimals (whole US dollars)",
)

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
        "trade_value_kusd": pa.Column(float, [NON_NEGATIVE, WHOLE_DOLLARS]),
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
        "reporter": pa.Column(str, pa.Check.isin(["China"])),
        "trade_flow": pa.Column(str, pa.Check.isin(["Export", "Import"])),
        "product_code": pa.Column(str, pa.Check.str_matches(r"^\d{6}$")),
        "year": pa.Column(int, YEAR_RANGE),
        "partner": pa.Column(str),
        "country": pa.Column(str),
        "trade_value_kusd": pa.Column(float, NON_NEGATIVE),
        "quantity_kg": pa.Column(float, NON_NEGATIVE),
        "unit_value_usd_per_kg": pa.Column(float, NON_NEGATIVE, nullable=True),
        "total_generation_twh": pa.Column(float, NON_NEGATIVE, nullable=True),
        "wind_solar_twh": pa.Column(float, NON_NEGATIVE, nullable=True),
        "renewables_twh": pa.Column(float, NON_NEGATIVE, nullable=True),
        "renewables_share_pct": pa.Column(float, pa.Check.in_range(0, 100.5), nullable=True),
    },
    unique=["reporter", "trade_flow", "product_code", "year", "partner"],
    strict=True,
    coerce=True,
    name="partner_trade_energy",
)

country_wind_imports_schema = pa.DataFrameSchema(
    {
        "partner": pa.Column(str),
        "country": pa.Column(str),
        "year": pa.Column(int, YEAR_RANGE),
        "imports_from_china_kg": pa.Column(float, NON_NEGATIVE, nullable=True),
        "import_growth_pct": pa.Column(float, pa.Check.ge(-100), nullable=True),
        "wind_generation_twh": pa.Column(float, NON_NEGATIVE, nullable=True),
        "wind_generation_change_twh": pa.Column(float, nullable=True),
        "wind_capacity_gw": pa.Column(float, NON_NEGATIVE, nullable=True),
    },
    unique=["partner", "year"],
    strict=True,
    coerce=True,
    name="country_wind_imports",
)

trade_wind_merged_schema = pa.DataFrameSchema(
    {
        "reporter": pa.Column(str, pa.Check.isin(["China"])),
        "trade_flow": pa.Column(str, pa.Check.isin(["Export", "Import"])),
        "product_code": pa.Column(str, pa.Check.str_matches(r"^\d{6}$")),
        "product_description": pa.Column(str),
        "year": pa.Column(int, YEAR_RANGE),
        "partner": pa.Column(str, pa.Check.ne("China")),
        "country": pa.Column(str),
        "trade_value_kusd": pa.Column(float, NON_NEGATIVE),
        "quantity": pa.Column(float, NON_NEGATIVE),
        "quantity_unit": pa.Column(str, pa.Check.isin(["kg"])),
        "imports_from_china_kg": pa.Column(float, NON_NEGATIVE, nullable=True),
        "import_growth_pct": pa.Column(float, pa.Check.ge(-100), nullable=True),
        "wind_generation_twh": pa.Column(float, NON_NEGATIVE, nullable=True),
        "wind_generation_change_twh": pa.Column(float, nullable=True),
        "wind_capacity_gw": pa.Column(float, NON_NEGATIVE, nullable=True),
    },
    unique=["reporter", "trade_flow", "product_code", "year", "partner"],
    strict=True,
    coerce=True,
    name="trade_wind_merged",
)

trade_wind_wide_schema = pa.DataFrameSchema(
    {
        "partner": pa.Column(str, pa.Check.ne("China")),
        "country": pa.Column(str),
        "year": pa.Column(int, YEAR_RANGE),
        "imports_from_china_kg": pa.Column(float, NON_NEGATIVE, nullable=True),
        "imports_from_china_value_kusd": pa.Column(float, NON_NEGATIVE, nullable=True),
        "exports_to_china_kg": pa.Column(float, NON_NEGATIVE, nullable=True),
        "exports_to_china_value_kusd": pa.Column(float, NON_NEGATIVE, nullable=True),
        "import_growth_pct": pa.Column(float, pa.Check.ge(-100), nullable=True),
        "wind_generation_twh": pa.Column(float, NON_NEGATIVE, nullable=True),
        "wind_generation_change_twh": pa.Column(float, nullable=True),
        "wind_capacity_gw": pa.Column(float, NON_NEGATIVE, nullable=True),
    },
    checks=[
        pa.Check(
            lambda df: df["imports_from_china_kg"].notna() | df["exports_to_china_kg"].notna(),
            element_wise=False,
            error="each row needs at least one trade direction",
        ),
    ],
    unique=["partner", "year"],
    strict=True,
    coerce=True,
    name="trade_wind_wide",
)

SCHEMAS = {
    "trade_flows": trade_schema,
    "electricity_generation": electricity_schema,
    "partner_trade_energy": partner_trade_energy_schema,
    "country_wind_imports": country_wind_imports_schema,
    "trade_wind_merged": trade_wind_merged_schema,
    "trade_wind_wide": trade_wind_wide_schema,
}


# Views are checked with the same rules as the tables they replace.
VIEW_SCHEMAS = {
    "electricity_generation_detail": electricity_schema,
    "partner_trade_energy": partner_trade_energy_schema,
    "country_wind_imports": country_wind_imports_schema,
    "trade_wind_merged": trade_wind_merged_schema,
    "trade_wind_wide": trade_wind_wide_schema,
}


def validate_view(name: str, df: pd.DataFrame) -> None:
    """Check a view's rows. Views are computed from validated data, so any failure
    means the view logic is wrong: stop the run (the load rolls back)."""
    try:
        VIEW_SCHEMAS[name].validate(df, lazy=True)
    except SchemaErrors as exc:
        problems = sorted({_reason(r) for _, r in exc.failure_cases.iterrows()})
        raise PipelineError(f"View {name!r} failed validation: {'; '.join(problems[:5])}") from exc


def _reason(row) -> str:
    """Readable rejection reason. Table-wide checks are reported once per column by
    Pandera, so they are labelled by the check only."""
    check = str(row["check"])
    if check.startswith("multiple_fields_uniqueness"):
        return "duplicate key with conflicting values"
    if row["schema_context"] == "DataFrameSchema" or not isinstance(row["column"], str):
        return check
    return f"{row['column']}: {check}"


def validate_table(
    name: str,
    df: pd.DataFrame,
    report: QualityReport | None = None,
    rejected_dir: Path | None = None,
    max_rejected_pct: float = 5.0,
) -> pd.DataFrame:
    """Validate one table and return only the rows that pass.

    - Exact duplicate rows: first copy kept, the rest dropped.
    - Rows failing any rule: rejected, saved with the reason to
      <rejected_dir>/rejected_<name>.csv, and not loaded.
    - Structural problems (missing columns) or a rejected share above
      max_rejected_pct stop the run with PipelineError.
    """
    quality = report.table(name) if report else None
    rows_in = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    duplicates = rows_in - len(df)
    if duplicates:
        logger.warning("%s: dropped %s exact duplicate row(s)", name, duplicates)

    schema = SCHEMAS[name]
    reasons: Counter = Counter()
    try:
        valid = schema.validate(df, lazy=True)
        rejected = df.iloc[0:0]
    except SchemaErrors as exc:
        cases = exc.failure_cases
        structural = cases[cases["index"].isna()]
        if not structural.empty:
            problems = "; ".join(_reason(r) for _, r in structural.iterrows())
            raise PipelineError(f"{name}: table structure is invalid: {problems}") from exc

        cases = cases.assign(index=cases["index"].astype(int), reason=cases.apply(_reason, axis=1))
        row_reasons = cases.groupby("index")["reason"].apply(lambda r: "; ".join(sorted(set(r))))
        reasons = Counter(cases.drop_duplicates(["index", "reason"])["reason"])
        rejected = df.loc[row_reasons.index].assign(rejection_reason=row_reasons.values)
        valid = schema.validate(df.drop(index=row_reasons.index))
        for reason, n in sorted(reasons.items()):
            logger.warning("%s: rejected %s row(s): %s", name, n, reason)

    rejected_pct = len(rejected) / len(df) * 100 if len(df) else 0.0
    if rejected_dir is not None:
        path = Path(rejected_dir) / f"rejected_{name}.csv"
        if len(rejected):
            path.parent.mkdir(parents=True, exist_ok=True)
            rejected.to_csv(path, index=False)
            logger.warning("%s: %s rejected row(s) saved to %s", name, len(rejected), path)
        elif path.exists():
            path.unlink()  # no stale rejects from an earlier run

    if quality:
        quality.duplicates_dropped = duplicates
        quality.rejected_by_reason = reasons
        quality.rows_rejected = len(rejected)
        quality.rows_valid = len(valid)
        quality.missing = missing_counts(valid)

    if rejected_pct > max_rejected_pct:
        raise PipelineError(
            f"{name}: {len(rejected)} of {len(df)} rows rejected ({rejected_pct:.1f}%), above the "
            f"{max_rejected_pct}% limit. Nothing was loaded; check the rejected rows file."
        )
    logger.info("Validated %s: %s rows passed, %s rejected, %s duplicates dropped",
                name, len(valid), len(rejected), duplicates)
    return valid
