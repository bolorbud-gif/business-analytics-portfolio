"""Tests for the ETL pipeline (src/data_pipeline)."""

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from src.data_pipeline import PipelineError
from src.data_pipeline.extract import read_excel
from src.data_pipeline.load import create_schema, get_engine
from src.data_pipeline.pipeline import run_pipeline
from src.data_pipeline.quality import QualityReport
from src.data_pipeline.transform import (
    build_country_wind_imports, build_partner_trade_energy, transform_electricity,
    transform_trade,
)
from src.data_pipeline.validate import validate_table

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "sample"
SOURCES = {"trade": "data1.xlsx", "electricity": "data2.xlsx"}


def raw_trade():
    """Mimics data1.xlsx, including its swapped 'China'/'Reporter' header cell."""
    return pd.DataFrame({
        "China": ["China", "Reporter", "China"],
        "TradeFlow": ["Export", "Import", "Export"],
        "ProductCode": [284690] * 3,
        "Product Description": ["Compounds of rare-earth"] * 3,
        "Year": [2023] * 3,
        "Partner": ["Japan", "Korea, Rep.", "France"],
        "Trade Value 1000USD": [100.0, 50.0, 10.0],
        "Quantity": [2000.0, 0.0, 100.0],
        "Quantity Unit": ["Kg"] * 3,
    })


def raw_electricity():
    rows = []
    for country, iso in [("Japan", "JPN"), ("South Korea", "KOR")]:
        for source, twh, agg in [("Total generation", 100.0, True), ("Wind and solar", 20.0, True),
                                 ("Renewables", 25.0, True), ("Net imports", -5.0, False)]:
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
def trade():
    return transform_trade(raw_trade())


@pytest.fixture
def electricity():
    return transform_electricity(raw_electricity())


# --- Transform ---------------------------------------------------------------

def test_transform_repairs_swapped_reporter_header():
    report = QualityReport("raw", "db")
    df = transform_trade(raw_trade(), report)
    assert df["reporter"].tolist() == ["China"] * 3
    assert report.tables["trade_flows"].rows_repaired == 1


def test_partner_names_mapped_and_unit_value(trade, electricity):
    pte = build_partner_trade_energy(trade, electricity).set_index("partner")
    assert pte.loc["Korea, Rep.", "country"] == "South Korea"
    assert pte.loc["Korea, Rep.", "renewables_share_pct"] == pytest.approx(25.0)
    assert pte.loc["Japan", "unit_value_usd_per_kg"] == pytest.approx(50.0)  # 100k USD / 2000 kg
    assert pd.isna(pte.loc["Korea, Rep.", "unit_value_usd_per_kg"])  # quantity 0
    assert pd.isna(pte.loc["France", "total_generation_twh"])  # no electricity data: kept


def clean_trade(rows):
    """rows: (trade_flow, year, partner, quantity) in the shape transform_trade returns."""
    return pd.DataFrame([{
        "reporter": "China", "trade_flow": flow, "product_code": "284690",
        "product_description": "x", "year": year, "partner": partner,
        "trade_value_kusd": 1.0, "quantity": qty, "quantity_unit": "kg",
    } for flow, year, partner, qty in rows])


def test_country_wind_imports_growth_rules(electricity):
    trade = clean_trade([
        ("Export", 2022, "Japan", 100.0), ("Export", 2023, "Japan", 200.0),
        ("Export", 2022, "France", 0.0), ("Export", 2023, "France", 50.0),   # previous is 0
        ("Export", 2023, "Korea, Rep.", 80.0),                               # no previous year
        ("Import", 2022, "Korea, Rep.", 999.0),                              # Import: ignored
        ("Export", 2023, "China", 5.0),                                      # re-imports: dropped
    ])
    out = build_country_wind_imports(trade, electricity).set_index(["partner", "year"])
    assert "China" not in out.index.get_level_values("partner")
    assert out.loc[("Japan", 2023), "import_growth_pct"] == pytest.approx(100.0)  # (200-100)/100*100
    assert pd.isna(out.loc[("France", 2023), "import_growth_pct"])
    assert pd.isna(out.loc[("Korea, Rep.", 2023), "import_growth_pct"])
    assert pd.isna(out.loc[("Korea, Rep.", 2022), "imports_from_china_kg"])  # missing, not 0
    assert len(out) == 3 * 2  # every partner x every year


def test_country_wind_imports_wind_columns():
    trade = clean_trade([("Export", 2023, "Korea, Rep.", 10.0)])
    electricity = pd.DataFrame({
        "country": ["South Korea", "South Korea"], "year": [2023, 2023],
        "source": ["Wind", "Solar"], "generation_twh": [4.0, 30.0],
        "generation_yoy_twh": [0.5, 3.0], "capacity_gw": [2.0, 20.0],
    })
    row = build_country_wind_imports(trade, electricity).iloc[0]
    assert (row["wind_generation_twh"], row["wind_generation_change_twh"],
            row["wind_capacity_gw"]) == (4.0, 0.5, 2.0)  # Wind only, matched via name map


# --- Validate: bad records are rejected, not loaded --------------------------

def test_valid_rows_pass_unchanged(trade, electricity):
    assert len(validate_table("trade_flows", trade)) == 3
    assert len(validate_table("electricity_generation", electricity)) == 8  # Net imports < 0 ok


def test_bad_row_is_rejected_and_saved(trade, tmp_path):
    trade.loc[0, "trade_value_kusd"] = -1.0
    report = QualityReport("raw", "db")
    valid = validate_table("trade_flows", trade, report, rejected_dir=tmp_path,
                           max_rejected_pct=50)
    assert len(valid) == 2
    q = report.tables["trade_flows"]
    assert q.rows_rejected == 1 and q.rows_valid == 2
    saved = pd.read_csv(tmp_path / "rejected_trade_flows.csv")
    assert saved["rejection_reason"].str.contains("trade_value_kusd").all()


def test_exact_duplicates_dropped_not_rejected(trade):
    report = QualityReport("raw", "db")
    valid = validate_table("trade_flows", pd.concat([trade, trade.iloc[[0]]]), report)
    assert len(valid) == 3
    assert report.tables["trade_flows"].duplicates_dropped == 1
    assert report.tables["trade_flows"].rows_rejected == 0


def test_conflicting_duplicate_keys_are_rejected(trade):
    conflict = trade.iloc[[0]].assign(trade_value_kusd=999.0)
    report = QualityReport("raw", "db")
    valid = validate_table("trade_flows", pd.concat([trade, conflict]), report,
                           max_rejected_pct=100)
    assert len(valid) == 2  # both copies of the ambiguous key are rejected
    assert report.tables["trade_flows"].rejected_by_reason == {
        "duplicate key with conflicting values": 2}


def test_table_wide_rule_gives_one_reason(electricity):
    electricity.loc[electricity["source"] == "Wind and solar", "generation_twh"] = -1.0
    report = QualityReport("raw", "db")
    validate_table("electricity_generation", electricity, report, max_rejected_pct=100)
    reasons = report.tables["electricity_generation"].rejected_by_reason
    assert list(reasons) == ["generation_twh must be >= 0 (except Net imports / Demand)"]
    assert reasons.total() == 2


def test_too_many_rejections_stop_the_run(trade):
    trade["quantity_unit"] = "ton"
    with pytest.raises(PipelineError, match="above the 5"):
        validate_table("trade_flows", trade)


def test_missing_column_stops_the_run(trade):
    with pytest.raises(PipelineError, match="structure"):
        validate_table("trade_flows", trade.drop(columns="partner"))


def test_missing_raw_file_raises_clear_error(tmp_path):
    with pytest.raises(PipelineError, match="not found"):
        read_excel(tmp_path / "nope.xlsx")


# --- End to end on the committed synthetic sample ----------------------------

def run_sample(tmp_path, **kwargs):
    return run_pipeline(SAMPLE_DIR, SOURCES, f"sqlite:///{tmp_path / 'sample.db'}",
                        rejected_dir=tmp_path / "rejected", **kwargs)


def test_sample_pipeline_quality_counts(tmp_path):
    report = run_sample(tmp_path, report_path=tmp_path / "report.md")
    t = report.tables
    assert report.status == "SUCCESS"
    assert (t["trade_flows"].rows_in, t["trade_flows"].duplicates_dropped,
            t["trade_flows"].rows_rejected, t["trade_flows"].rows_after_load) == (49, 1, 2, 46)
    assert t["electricity_generation"].rows_rejected == 1
    assert t["country_wind_imports"].rows_after_load == 8 * 3  # 8 partners x 3 years
    assert "## Re-runnability check" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_second_run_does_not_duplicate_or_change_rows(tmp_path):
    first = run_sample(tmp_path)
    second = run_sample(tmp_path)
    for name, t in second.tables.items():
        assert t.rows_before_load == first.tables[name].rows_after_load
        assert t.rows_after_load == t.rows_before_load
        assert t.checksum_after == t.checksum_before


def test_foreign_key_is_enforced(tmp_path):
    run_sample(tmp_path)
    engine = get_engine(f"sqlite:///{tmp_path / 'sample.db'}")
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(
            "insert into partner_trade_energy (reporter, trade_flow, product_code, year, "
            "partner, country, trade_value_kusd, quantity_kg) "
            "values ('China', 'Export', '284690', 2099, 'Nowhere', 'Nowhere', 1, 1)"))


def test_outdated_table_layout_requires_rebuild(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    with create_engine(url).begin() as conn:
        conn.execute(text("create table trade_flows (partner text)"))
    with pytest.raises(PipelineError, match="--rebuild"):
        create_schema(get_engine(url))
    create_schema(get_engine(url), rebuild=True)  # rebuild fixes it
