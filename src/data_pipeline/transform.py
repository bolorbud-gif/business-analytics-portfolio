"""Transform stage: clean column names, fix known data problems, normalize to 3NF."""

import logging

import pandas as pd

from src.data_pipeline import PipelineError
from src.data_pipeline.quality import QualityReport, missing_counts

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


# --- Normalization (1NF -> 2NF -> 3NF) -----------------------------------------------
# Columns computed from other columns of the same row (3NF): not stored, recomputed in
# the electricity_generation_detail view.
DERIVED_ELECTRICITY_COLUMNS = {
    "generation_yoy_pct": "generation_yoy_twh / (generation_twh - generation_yoy_twh) * 100",
    "emissions_yoy_pct": "emissions_yoy_mtco2e / (emissions_mtco2e - emissions_yoy_mtco2e) * 100",
    "emissions_intensity_g_per_kwh": "emissions_mtco2e / generation_twh * 1000",
}


def _require_dependency(df: pd.DataFrame, determinant: str, dependents: list[str], what: str):
    """Check that `determinant` decides each dependent column (one value per key).

    Moving a column to its own table (2NF) is only safe if this holds; otherwise data
    would be lost, so the run stops instead.
    """
    for col in dependents:
        n = df.groupby(determinant)[col].nunique(dropna=False)
        bad = n[n > 1]
        if len(bad):
            raise PipelineError(
                f"Cannot normalize {what}: {col!r} has more than one value for "
                f"{determinant} {list(bad.index[:5])}"
            )


def normalize(
    trade: pd.DataFrame, electricity: pd.DataFrame, report: QualityReport | None = None
) -> dict[str, pd.DataFrame]:
    """Split the validated source tables into 3NF tables.

    2NF (every non-key column depends on the whole key):
      countries       iso3, area_type depend on the country only, not on country+year+source;
                      also links the trade naming ("Korea, Rep.") to the Ember naming
                      ("South Korea") in data instead of in code
      products        product_description, quantity_unit depend on product_code only
      energy_sources  is_aggregated depends on source only
    3NF (no non-key column depends on another non-key column):
      electricity_generation drops DERIVED_ELECTRICITY_COLUMNS
    """
    trade = trade.reset_index(drop=True)
    electricity = electricity.reset_index(drop=True)
    _require_dependency(trade, "product_code", ["product_description", "quantity_unit"],
                        "products")
    _require_dependency(electricity, "country", ["iso3", "area_type"], "countries")
    _require_dependency(electricity, "iso3", ["country"], "countries")
    _require_dependency(electricity, "source", ["is_aggregated"], "energy sources")

    # countries: one row per real country, with its name in each source
    ember = electricity[["country", "iso3", "area_type"]].drop_duplicates().set_index("country")
    rows = []
    for name in sorted(set(trade["reporter"]) | set(trade["partner"])):
        mapped = PARTNER_TO_COUNTRY.get(name, name)
        rows.append({"trade_name": name,
                     "ember_name": mapped if mapped in ember.index else None})
    linked = [r["ember_name"] for r in rows if r["ember_name"] is not None]
    if len(linked) != len(set(linked)):
        raise PipelineError("Cannot normalize countries: two trade names map to one Ember country")
    rows += [{"trade_name": None, "ember_name": e} for e in sorted(set(ember.index) - set(linked))]
    countries = pd.DataFrame(rows, columns=["trade_name", "ember_name"])
    countries["iso3"] = countries["ember_name"].map(ember["iso3"])
    countries["area_type"] = countries["ember_name"].map(ember["area_type"])
    order = countries["trade_name"].fillna(countries["ember_name"]).sort_values().index
    countries = countries.loc[order].reset_index(drop=True)
    countries.insert(0, "country_id", range(1, len(countries) + 1))

    by_trade = countries.dropna(subset=["trade_name"]).set_index("trade_name")["country_id"]
    by_ember = countries.dropna(subset=["ember_name"]).set_index("ember_name")["country_id"]

    products = (trade[["product_code", "product_description", "quantity_unit"]]
                .drop_duplicates().sort_values("product_code").reset_index(drop=True))
    energy_sources = (electricity[["source", "is_aggregated"]]
                      .drop_duplicates().sort_values("source").reset_index(drop=True))

    trade_facts = pd.DataFrame({
        "reporter_id": trade["reporter"].map(by_trade),
        "trade_flow": trade["trade_flow"],
        "product_code": trade["product_code"],
        "year": trade["year"],
        "partner_id": trade["partner"].map(by_trade),
        # money as exact integer dollars, never REAL (validated: at most 3 decimals in kUSD)
        "trade_value_usd": (trade["trade_value_kusd"] * 1000).round().astype("int64"),
        "quantity": trade["quantity"],
    })
    electricity_facts = electricity.assign(country_id=electricity["country"].map(by_ember))
    electricity_facts = electricity_facts[[
        "country_id", "year", "source", "generation_twh", "generation_yoy_twh",
        "generation_share_pct", "generation_share_yoy_pp", "capacity_gw", "emissions_mtco2e",
        "emissions_yoy_mtco2e", "emissions_share_pct",
    ]]

    tables = {
        "countries": countries,
        "products": products,
        "energy_sources": energy_sources,
        "trade_flows": trade_facts,
        "electricity_generation": electricity_facts,
    }
    if report:
        for name in ["countries", "products", "energy_sources"]:
            q = report.table(name, "normalized")
            q.rows_in = q.rows_valid = len(tables[name])
        for name in tables:
            report.table(name).missing = missing_counts(tables[name])
        both = int((countries["trade_name"].notna() & countries["ember_name"].notna()).sum())
        report.notes.append(
            f"Normalized to 3NF: {len(countries)} countries ({both} matched across both "
            f"sources), {len(products)} product(s), {len(energy_sources)} energy sources. "
            f"Not stored because they are computed from the same row (3NF): "
            f"{', '.join(DERIVED_ELECTRICITY_COLUMNS)}; recomputed in "
            f"electricity_generation_detail."
        )
    logger.info("Normalized: %s", {n: len(t) for n, t in tables.items()})
    return tables
