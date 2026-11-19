"""Transform stage: clean column names, fix known data problems, build analysis table."""

import logging

import pandas as pd

from src.data_pipeline import PipelineError
from src.data_pipeline.quality import QualityReport

logger = logging.getLogger(__name__)

TRADE_COLUMNS = {
    "TradeFlow": "trade_flow",
    "ProductCode": "product_code",
    "Product Description": "product_description",
    "Year": "year",
    "Partner": "partner",
    "Trade Value 1000USD": "trade_value_kusd",
    "Quantity": "quantity",
    "Quantity Unit": "quantity_unit",
}

ELECTRICITY_COLUMNS = {
    "Area": "country",
    "ISO 3 code": "iso3",
    "Year": "year",
    "Area type": "area_type",
    "Electricity source": "source",
    "Is aggregated source": "is_aggregated",
    "Generation (TWh)": "generation_twh",
    "Generation YoY change (TWh)": "generation_yoy_twh",
    "Generation YoY change (%)": "generation_yoy_pct",
    "Share of generation (%)": "generation_share_pct",
    "Share of generation YoY change (% points)": "generation_share_yoy_pp",
    "Capacity (GW)": "capacity_gw",
    "Emissions (MtCO2e)": "emissions_mtco2e",
    "Emissions YoY change (MtCO2e)": "emissions_yoy_mtco2e",
    "Emissions YoY change (%)": "emissions_yoy_pct",
    "Share of emissions (%)": "emissions_share_pct",
    "Emissions intensity (gCO2e/kWh)": "emissions_intensity_g_per_kwh",
}

# Trade data uses World Bank country names; electricity data uses Ember names.
PARTNER_TO_COUNTRY = {
    "Czech Republic": "Czechia",
    "Egypt, Arab Rep.": "Egypt",
    "Hong Kong, China": "Hong Kong (SAR of China)",
    "Iran, Islamic Rep.": "Iran",
    "Korea, Dem. Rep.": "North Korea",
    "Korea, Rep.": "South Korea",
    "Philippines": "The Philippines",
    "Russian Federation": "Russia",
    "Turkey": "Turkish",
    "Vietnam": "Viet Nam",
}


def _require_columns(df: pd.DataFrame, columns, name: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise PipelineError(f"{name} data is missing expected columns: {missing}")


def transform_trade(raw: pd.DataFrame, report: QualityReport | None = None) -> pd.DataFrame:
    """Clean the rare-earth trade table.

    In the source file the reporter column's header and one of its cells are
    swapped: the header reads "China" and one row reads "Reporter". We rename the
    column to `reporter` and put the header value back into that row.
    """
    quality = report.table("trade_flows", "data1.xlsx") if report else None
    if quality:
        quality.rows_in = len(raw)
    df = raw.copy()
    first_col = df.columns[0]
    df = df.rename(columns={first_col: "reporter"})
    if first_col != "Reporter":
        swapped = df["reporter"] == "Reporter"
        if swapped.any():
            logger.warning(
                "Trade data: header/cell swap found in %s row(s); set reporter to %r",
                int(swapped.sum()), first_col,
            )
            df.loc[swapped, "reporter"] = first_col
            if quality:
                quality.rows_repaired += int(swapped.sum())
                quality.repairs.append(
                    f"{int(swapped.sum())} row(s) had reporter 'Reporter' (header/cell swap); "
                    f"set to {first_col!r}"
                )

    _require_columns(df, TRADE_COLUMNS, "Trade")
    df = df.rename(columns=TRADE_COLUMNS)
    df["product_code"] = df["product_code"].astype(str)
    df["quantity_unit"] = df["quantity_unit"].str.strip().str.lower()
    logger.info("Transformed trade data: %s rows", len(df))
    return df


def transform_electricity(raw: pd.DataFrame, report: QualityReport | None = None) -> pd.DataFrame:
    """Rename electricity columns to snake_case."""
    if report:
        report.table("electricity_generation", "data2.xlsx").rows_in = len(raw)
    _require_columns(raw, ELECTRICITY_COLUMNS, "Electricity")
    df = raw.rename(columns=ELECTRICITY_COLUMNS)[list(ELECTRICITY_COLUMNS.values())]
    df["is_aggregated"] = df["is_aggregated"].astype(bool)
    logger.info("Transformed electricity data: %s rows", len(df))
    return df


def build_partner_trade_energy(
    trade: pd.DataFrame, electricity: pd.DataFrame, report: QualityReport | None = None
) -> pd.DataFrame:
    """One row per trade_flows row, joined with the partner's power mix that year.

    Adds unit value (USD per kg) and the partner's total, wind+solar and renewable
    generation for the same year. Partners with no electricity data keep NaN.
    """
    df = trade.rename(columns={"quantity": "quantity_kg"})  # validated as kg
    df["country"] = df["partner"].replace(PARTNER_TO_COUNTRY)
    df["unit_value_usd_per_kg"] = (df["trade_value_kusd"] * 1000 / df["quantity_kg"]).where(
        df["quantity_kg"] > 0
    )

    mix = electricity.pivot_table(
        index=["country", "year"], columns="source", values="generation_twh", aggfunc="sum"
    )
    mix = mix.reindex(columns=["Total generation", "Wind and solar", "Renewables"])
    mix.columns = ["total_generation_twh", "wind_solar_twh", "renewables_twh"]
    mix["renewables_share_pct"] = mix["renewables_twh"] / mix["total_generation_twh"] * 100
    mix = mix.reset_index()

    out = df.merge(mix, on=["country", "year"], how="left")
    unmatched = sorted(out.loc[out["total_generation_twh"].isna(), "partner"].unique())
    if unmatched:
        logger.warning("No electricity data for %s partner(s): %s", len(unmatched), unmatched)
    if report:
        report.table("partner_trade_energy", "derived").rows_in = len(out)
        rows = int(out["total_generation_twh"].isna().sum())
        if unmatched:
            report.notes.append(
                f"{rows} partner_trade_energy row(s) have NULL electricity fields: no electricity "
                f"data for {len(unmatched)} partner(s) in those years: {', '.join(unmatched)}."
            )

    columns = [
        "reporter", "trade_flow", "product_code", "year", "partner", "country",
        "trade_value_kusd", "quantity_kg", "unit_value_usd_per_kg",
        "total_generation_twh", "wind_solar_twh", "renewables_twh", "renewables_share_pct",
    ]
    logger.info("Built partner_trade_energy: %s rows", len(out))
    return out[columns]
