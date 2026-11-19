"""Tests for the ETL pipeline (src/data_pipeline)."""

import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from src.data_pipeline import PipelineError
from src.data_pipeline.extract import read_excel
from src.data_pipeline.load import connect, create_schema, get_engine, load
from src.data_pipeline.pipeline import run_pipeline
from src.data_pipeline.quality import QualityReport
from src.data_pipeline.transform import normalize, transform_electricity, transform_trade
from src.data_pipeline.validate import validate_table

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "sample"
SOURCES = {"trade": "data1.xlsx", "electricity": "data2.xlsx"}
AGGREGATED = {"Total generation", "Wind and solar", "Renewables"}


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


def raw_electricity(years=(2023,)):
    """Mimics data2.xlsx for Japan and South Korea (France has no electricity data)."""
    rows = []
    for year in years:
        for country, iso in [("Japan", "JPN"), ("South Korea", "KOR")]:
            for source, twh, yoy, cap, emis in [
                ("Total generation", 100.0, 4.0, None, 50.0),
                ("Wind and solar", 20.0, 2.0, None, None),
                ("Renewables", 25.0, 2.0, None, None),
                ("Wind", 8.0, 1.0, 3.0, None),
                ("Net imports", -5.0, 0.0, None, None),
            ]:
                rows.append({
                    "Area": country, "ISO 3 code": iso, "Year": year,
                    "Area type": "Country or economy", "Electricity source": source,
                    "Is aggregated source": source in AGGREGATED, "Generation (TWh)": twh,
                    "Generation YoY change (TWh)": yoy, "Generation YoY change (%)": None,
                    "Share of generation (%)": twh, "Share of generation YoY change (% points)": 0.0,
                    "Capacity (GW)": cap, "Emissions (MtCO2e)": emis,
                    "Emissions YoY change (MtCO2e)": None, "Emissions YoY change (%)": None,
                    "Share of emissions (%)": None, "Emissions intensity (gCO2e/kWh)": None,
                })
    return pd.DataFrame(rows)


def clean_trade(rows):
    """rows: (trade_flow, year, partner, quantity) in the shape transform_trade returns."""
    return pd.DataFrame([{
        "reporter": "China", "trade_flow": flow, "product_code": "284690",
        "product_description": "x", "year": year, "partner": partner,
        "trade_value_kusd": 1.0, "quantity": qty, "quantity_unit": "kg",
    } for flow, year, partner, qty in rows])


@pytest.fixture
def trade():
    return transform_trade(raw_trade())


@pytest.fixture
def electricity():
    return transform_electricity(raw_electricity())


def build(tmp_path, trade, electricity):
    """Normalize, load into a fresh SQLite file and return the views."""
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    create_schema(engine)
    return load(engine, normalize(trade, electricity))


# --- Transform ---------------------------------------------------------------

def test_transform_repairs_swapped_reporter_header():
    report = QualityReport("raw", "db")
    df = transform_trade(raw_trade(), report)
    assert df["reporter"].tolist() == ["China"] * 3
    assert report.tables["trade_flows"].rows_repaired == 1


# --- Normalization -----------------------------------------------------------

def test_2nf_partial_dependencies_moved_to_own_tables(trade, electricity):
    t = normalize(trade, electricity)
    # product_description / quantity_unit depend on product_code only
    assert t["products"].to_dict("records") == [
        {"product_code": "284690", "product_description": "Compounds of rare-earth",
         "quantity_unit": "kg"}]
    assert {"product_description", "quantity_unit", "partner"}.isdisjoint(t["trade_flows"])
    # iso3 / area_type depend on country only; is_aggregated on source only
    assert {"iso3", "area_type", "is_aggregated", "country"}.isdisjoint(t["electricity_generation"])
    assert t["energy_sources"].set_index("source").loc["Wind", "is_aggregated"] == False  # noqa: E712
    # one countries row links both naming systems
    korea = t["countries"].set_index("trade_name").loc["Korea, Rep."]
    assert (korea["ember_name"], korea["iso3"]) == ("South Korea", "KOR")
    france = t["countries"].set_index("trade_name").loc["France"]
    assert pd.isna(france["ember_name"])  # traded, but no electricity data


def test_3nf_same_row_calculations_not_stored_but_recomputed(tmp_path, trade, electricity):
    t = normalize(trade, electricity)
    assert {"generation_yoy_pct", "emissions_yoy_pct",
            "emissions_intensity_g_per_kwh"}.isdisjoint(t["electricity_generation"])
    detail = build(tmp_path, trade, electricity)["electricity_generation_detail"]
    total = detail[(detail["country"] == "Japan") & (detail["source"] == "Total generation")].iloc[0]
    assert total["emissions_intensity_g_per_kwh"] == pytest.approx(50.0 / 100.0 * 1000)
    assert total["generation_yoy_pct"] == pytest.approx(4.0 / (100.0 - 4.0) * 100)


def test_normalize_stops_if_a_dependency_does_not_hold(trade, electricity):
    trade.loc[1, "product_description"] = "Something else"  # same code, two descriptions
    with pytest.raises(PipelineError, match="product_description"):
        normalize(trade, electricity)


# --- Views -------------------------------------------------------------------

def test_partner_trade_energy_view(tmp_path, trade, electricity):
    pte = build(tmp_path, trade, electricity)["partner_trade_energy"].set_index("partner")
    assert pte.loc["Korea, Rep.", "country"] == "South Korea"
    assert pte.loc["Korea, Rep.", "renewables_share_pct"] == pytest.approx(25.0)
    assert pte.loc["Japan", "unit_value_usd_per_kg"] == pytest.approx(50.0)  # 100k USD / 2000 kg
    assert pd.isna(pte.loc["Korea, Rep.", "unit_value_usd_per_kg"])  # quantity 0
    assert pd.isna(pte.loc["France", "total_generation_twh"])  # no electricity data: kept


def test_country_wind_imports_growth_rules(tmp_path):
    trade = clean_trade([
        ("Export", 2022, "Japan", 100.0), ("Export", 2023, "Japan", 200.0),
        ("Export", 2022, "France", 0.0), ("Export", 2023, "France", 50.0),   # previous is 0
        ("Export", 2023, "Korea, Rep.", 80.0),                               # no previous year
        ("Import", 2022, "Korea, Rep.", 999.0),                              # Import: ignored
        ("Export", 2023, "China", 5.0),                                      # re-imports: dropped
    ])
    electricity = transform_electricity(raw_electricity(years=(2022, 2023)))
    cwi = build(tmp_path, trade, electricity)["country_wind_imports"].set_index(["partner", "year"])
    assert "China" not in cwi.index.get_level_values("partner")
    assert cwi.loc[("Japan", 2023), "import_growth_pct"] == pytest.approx(100.0)  # (200-100)/100*100
    assert pd.isna(cwi.loc[("France", 2023), "import_growth_pct"])
    assert pd.isna(cwi.loc[("Korea, Rep.", 2023), "import_growth_pct"])
    assert pd.isna(cwi.loc[("Korea, Rep.", 2022), "imports_from_china_kg"])  # missing, not 0
    assert len(cwi) == 3 * 2  # every partner x every year
    korea = cwi.loc[("Korea, Rep.", 2023)]  # wind matched through the countries table
    assert (korea["wind_generation_twh"], korea["wind_generation_change_twh"],
            korea["wind_capacity_gw"]) == (8.0, 1.0, 3.0)


def test_trade_wind_merged_keeps_every_data1_row_except_china(tmp_path, electricity):
    trade = clean_trade([
        ("Import", 2023, "Japan", 30.0), ("Export", 2023, "Japan", 200.0),
        ("Export", 2023, "Korea, Rep.", 80.0), ("Export", 2023, "China", 5.0),
    ])
    report = QualityReport("raw", "db")
    views = build(tmp_path, trade, electricity)
    merged = views["trade_wind_merged"]
    assert len(merged) == 3  # 4 data1 rows - 1 China row
    assert set(merged["trade_flow"]) == {"Export", "Import"}  # both directions kept
    assert "China" not in set(merged["partner"])
    from src.data_pipeline.pipeline import describe_views
    describe_views(views, trade, report)
    assert any("left out" in n for n in report.notes)


def test_trade_wind_wide_puts_export_and_import_on_one_row(tmp_path, electricity):
    trade = clean_trade([
        ("Export", 2023, "Japan", 200.0), ("Import", 2023, "Japan", 30.0),  # both directions
        ("Import", 2023, "France", 10.0),                                    # one direction
    ])
    trade.loc[trade["trade_flow"] == "Import", "trade_value_kusd"] = 7.0
    wide = build(tmp_path, trade, electricity)["trade_wind_wide"].set_index(["partner", "year"])
    assert len(wide) == 2  # one row per country-year
    japan = wide.loc[("Japan", 2023)]
    assert (japan["imports_from_china_kg"], japan["exports_to_china_kg"]) == (200.0, 30.0)
    assert japan["exports_to_china_value_kusd"] == 7.0
    france = wide.loc[("France", 2023)]
    assert pd.isna(france["imports_from_china_kg"]) and france["exports_to_china_kg"] == 10.0


# --- Validate: bad records are rejected, not loaded --------------------------

def test_valid_rows_pass_unchanged(trade, electricity):
    assert len(validate_table("trade_flows", trade)) == 3
    assert len(validate_table("electricity_generation", electricity)) == 10  # Net imports < 0 ok


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
    assert t["countries"].rows_after_load == 8 + 1  # 8 partners + China
    assert t["country_wind_imports"].rows_after_load == 8 * 3  # 8 partners x 3 years
    assert t["trade_wind_merged"].rows_after_load == t["trade_flows"].rows_after_load
    # all 24 country-years stay; the 2 rejected rows only blank one direction each
    assert t["trade_wind_wide"].rows_after_load == 8 * 3
    assert "## Re-runnability check" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_second_run_does_not_duplicate_or_change_rows(tmp_path):
    first = run_sample(tmp_path)
    second = run_sample(tmp_path)
    for name, t in second.tables.items():
        if t.rows_after_load is None:
            continue
        assert t.rows_before_load == first.tables[name].rows_after_load, name
        assert t.rows_after_load == t.rows_before_load, name
        assert t.checksum_after == t.checksum_before, name


def test_foreign_keys_are_enforced(tmp_path):
    run_sample(tmp_path)
    engine = get_engine(f"sqlite:///{tmp_path / 'sample.db'}")
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(
            "insert into trade_flows (reporter_id, trade_flow, product_code, year, partner_id, "
            "trade_value_usd, quantity) values (1, 'Export', '284690', 2099, 99999, 1, 1)"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(
            "insert into electricity_generation (country_id, year, source, generation_twh, "
            "generation_share_pct) values (1, 2099, 'Unknown source', 1, 1)"))


def test_money_is_stored_as_exact_integer_dollars(tmp_path, trade, electricity):
    tables = normalize(trade, electricity)
    assert "trade_value_kusd" not in tables["trade_flows"]
    assert tables["trade_flows"]["trade_value_usd"].dtype == "int64"
    build(tmp_path, trade, electricity)
    db = connect(tmp_path / "test.db")
    assert {r[0] for r in db.execute("select typeof(trade_value_usd) from trade_flows")} == {"integer"}
    assert db.execute("select sum(trade_value_usd) from trade_flows").fetchone()[0] == 160_000


def test_value_finer_than_a_dollar_is_rejected(trade):
    trade.loc[0, "trade_value_kusd"] = 1.2345  # 1,234.50 USD: cents would be lost
    report = QualityReport("raw", "db")
    validate_table("trade_flows", trade, report, max_rejected_pct=100)
    assert list(report.tables["trade_flows"].rejected_by_reason) == [
        "trade_value_kusd: trade_value_kusd must have at most 3 decimals (whole US dollars)"]


def test_check_constraints_refuse_bad_values(tmp_path):
    run_sample(tmp_path)
    db = connect(tmp_path / "sample.db")
    for values, constraint in [("(1, 'Export', '284690', 2099, 2, -5, 1)", "ck_trade_value"),
                               ("(1, 'Gift', '284690', 2099, 2, 5, 1)", "ck_trade_flow"),
                               ("(1, 'Export', '284690', 2099, 2, 5, -1)", "ck_quantity")]:
        with pytest.raises(sqlite3.IntegrityError, match=constraint):
            db.execute(f"insert into trade_flows values {values}")


def test_connect_helper_turns_foreign_keys_on(tmp_path):
    run_sample(tmp_path)
    assert connect(tmp_path / "sample.db").execute("pragma foreign_keys").fetchone()[0] == 1
    assert sqlite3.connect(tmp_path / "sample.db").execute("pragma foreign_keys").fetchone()[0] == 0


def test_analysis_outputs_are_views_not_tables(tmp_path):
    run_sample(tmp_path)
    insp = inspect(get_engine(f"sqlite:///{tmp_path / 'sample.db'}"))
    assert set(insp.get_table_names()) == {
        "countries", "products", "energy_sources", "trade_flows", "electricity_generation"}
    assert set(insp.get_view_names()) == {
        "electricity_generation_detail", "partner_trade_energy", "country_wind_imports",
        "trade_wind_merged", "trade_wind_wide"}


def test_outdated_layout_requires_rebuild(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    with create_engine(url).begin() as conn:
        conn.execute(text("create table trade_wind_wide (partner text)"))  # pre-3NF table
    with pytest.raises(PipelineError, match="--rebuild"):
        create_schema(get_engine(url))
    create_schema(get_engine(url), rebuild=True)  # rebuild fixes it
    assert "trade_wind_wide" not in inspect(get_engine(url)).get_table_names()
