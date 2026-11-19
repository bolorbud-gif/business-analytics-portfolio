"""Tests for the ETL pipeline (src/data_pipeline)."""

import pandas as pd
import pytest
from sqlalchemy import text

from src.data_pipeline import PipelineError
from src.data_pipeline.extract import read_excel
from src.data_pipeline.load import create_schema, get_engine, load
from src.data_pipeline.transform import transform, transform_trade
from src.data_pipeline.validate import validate, validate_table


def raw_trade():
    """Mimics data1.xlsx, including its swapped 'China'/'Reporter' header cell."""
    return pd.DataFrame({
        "China": ["China", "Reporter"],
        "TradeFlow": ["Export", "Import"],
        "ProductCode": [284690, 284690],
        "Product Description": ["Compounds of rare-earth"] * 2,
        "Year": [2023, 2023],
        "Partner": ["Japan", "Korea, Rep."],
        "Trade Value 1000USD": [100.0, 50.0],
        "Quantity": [2000.0, 0.0],
        "Quantity Unit": ["Kg", "Kg"],
    })


def raw_electricity():
    rows = []
    for country, iso in [("Japan", "JPN"), ("South Korea", "KOR")]:
        for source, twh, agg in [("Total generation", 100.0, True),
                                 ("Wind and solar", 20.0, True),
                                 ("Renewables", 25.0, True),
                                 ("Net imports", -5.0, False)]:
            rows.append({
                "Area": country, "ISO 3 code": iso, "Year": 2023,
                "Area type": "Country or economy", "Electricity source": source,
                "Is aggregated source": agg, "Generation (TWh)": twh,
                "Generation YoY change (TWh)": 1.0, "Generation YoY change (%)": None,
                "Share of generation (%)": twh, "Share of generation YoY change (% points)": 0.0,
                "Capacity (GW)": None, "Emissions (MtCO2e)": None,
                "Emissions YoY change (MtCO2e)": None, "Emissions YoY change (%)": None,
                "Share of emissions (%)": None, "Emissions intensity (gCO2e/kWh)": None,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def tables():
    return transform({"trade": raw_trade(), "electricity": raw_electricity()})


def test_transform_fixes_swapped_reporter_header():
    df = transform_trade(raw_trade())
    assert "reporter" in df.columns
    assert df["reporter"].tolist() == ["China", "China"]
    assert df["quantity_unit"].tolist() == ["kg", "kg"]


def test_partner_names_mapped_to_electricity_names(tables):
    pte = tables["partner_trade_energy"].set_index("partner")
    assert pte.loc["Korea, Rep.", "country"] == "South Korea"
    assert pte.loc["Korea, Rep.", "renewables_share_pct"] == pytest.approx(25.0)


def test_unit_value_is_null_when_quantity_is_zero(tables):
    pte = tables["partner_trade_energy"].set_index("partner")
    assert pte.loc["Japan", "unit_value_usd_per_kg"] == pytest.approx(50.0)  # 100k USD / 2000 kg
    assert pd.isna(pte.loc["Korea, Rep.", "unit_value_usd_per_kg"])


def test_valid_tables_pass_validation(tables):
    validate(tables)  # negative Net imports is allowed


def test_validation_rejects_negative_trade_value(tables):
    bad = tables["trade_flows"].copy()
    bad.loc[0, "trade_value_kusd"] = -1.0
    with pytest.raises(PipelineError, match="trade_flows"):
        validate_table("trade_flows", bad)


def test_validation_rejects_duplicate_rows(tables):
    bad = pd.concat([tables["trade_flows"]] * 2, ignore_index=True)
    with pytest.raises(PipelineError):
        validate_table("trade_flows", bad)


def test_validation_rejects_negative_solar_generation(tables):
    bad = tables["electricity_generation"].copy()
    bad.loc[bad["source"] == "Wind and solar", "generation_twh"] = -1.0
    with pytest.raises(PipelineError):
        validate_table("electricity_generation", bad)


def test_missing_raw_file_raises_clear_error(tmp_path):
    with pytest.raises(PipelineError, match="not found"):
        read_excel(tmp_path / "nope.xlsx")


def test_load_is_repeatable(tables, tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    create_schema(engine)
    validated = validate(tables)
    load(engine, validated)
    counts = load(engine, validated)  # second run must not duplicate rows
    assert counts == {"trade_flows": 2, "electricity_generation": 8, "partner_trade_energy": 2}
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from trade_flows")).scalar_one() == 2
