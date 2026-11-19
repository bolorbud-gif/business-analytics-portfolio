"""Tests for the analysis functions (src/analysis)."""

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")  # no window needed

from src.analysis import charts as ch  # noqa: E402
from src.analysis import exploratory as ex  # noqa: E402
from src.analysis import statistical as st  # noqa: E402
from src.data_pipeline.pipeline import run_pipeline  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sample_db(tmp_path_factory):
    """The synthetic sample, built into a fresh database."""
    tmp = tmp_path_factory.mktemp("db")
    run_pipeline(ROOT / "data" / "sample", {"trade": "data1.xlsx", "electricity": "data2.xlsx"},
                 f"sqlite:///{tmp / 'sample.db'}", rejected_dir=tmp / "rejected")
    con, _ = ex.open_database(tmp / "sample.db")
    yield con
    con.close()


# --- Connecting and data quality -------------------------------------------------------

def test_open_database_explains_how_to_build_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="run_pipeline.py"):
        ex.open_database(tmp_path / "missing.db")


def test_check_database_passes_on_a_fresh_build(sample_db):
    checks = ex.check_database(sample_db)
    assert checks["passed"].all(), checks[~checks["passed"]]
    assert len(checks) >= 15


def test_check_database_catches_an_orphan_row(sample_db):
    sample_db.execute("PRAGMA foreign_keys = OFF")  # simulate a careless write
    sample_db.execute("INSERT INTO trade_flows VALUES (1, 'Export', '284690', 2024, 99999, 1, 1)")
    try:
        checks = ex.check_database(sample_db).set_index("check")
        assert not checks.loc["Foreign keys enforced on this connection", "passed"]
        assert not checks.loc["No orphan rows", "passed"]
    finally:
        sample_db.rollback()
        sample_db.execute("PRAGMA foreign_keys = ON")


def test_coverage_by_year_counts_rows_per_direction(sample_db):
    cov = ex.coverage_by_year(sample_db)
    assert set(cov.columns) == {"Export", "Import"}
    assert cov.values.sum() == sample_db.execute("SELECT COUNT(*) FROM trade_flows").fetchone()[0]


def test_country_panel_adds_size_and_shares(sample_db):
    panel = ex.load_country_panel(sample_db)
    row = panel.dropna(subset=["wind_share_pct"]).iloc[0]
    assert row["wind_share_pct"] == pytest.approx(
        row["wind_generation_twh"] / row["total_generation_twh"] * 100)
    sample = ex.analysis_sample(panel)
    assert (sample[["imports_from_china_kg", "wind_capacity_gw"]] > 0).all().all()
    assert set(sample["size_group"].unique()) <= {"Small", "Medium", "Large"}


# --- Describing ---------------------------------------------------------------------------

def test_describe_numeric_counts_missing_and_skew():
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 100.0, None]})
    d = ex.describe_numeric(df, ["x"]).loc["x"]
    assert (d["n"], d["missing"], d["missing_pct"], d["median"]) == (4, 1, 20.0, 2.5)
    assert d["skew"] > 1  # one large value: right-skewed


def test_concentration_hhi_and_level():
    two_equal = ex.concentration(pd.Series([50.0, 50.0]))
    assert two_equal["hhi"] == 5000 and two_equal["level"] == "highly concentrated"
    many = ex.concentration(pd.Series([1.0] * 20))
    assert many["hhi"] == 500 and many["level"] == "unconcentrated"
    assert many["top5_share"] == pytest.approx(0.25)


def test_market_shares_folds_the_rest_into_other():
    df = pd.DataFrame({"partner": list("ABCDE"), "kg": [40.0, 30.0, 15.0, 10.0, 5.0]})
    s = ex.market_shares(df, "partner", "kg", top=2)
    assert list(s.index) == ["A", "B", "All other (3)"]
    assert s["share"].sum() == pytest.approx(1.0)
    assert s.loc["All other (3)", "kg"] == 30.0


def test_yearly_trade_and_period_change():
    trade = pd.DataFrame({
        "year": [2023, 2023, 2024], "trade_flow": ["Export"] * 3, "partner": ["A", "B", "A"],
        "quantity_kg": [100.0, 100.0, 220.0], "trade_value_kusd": [2.0, 2.0, 2.2],
    })
    yearly = ex.yearly_trade(trade)
    assert yearly.set_index("year").loc[2023, "unit_value_usd_per_kg"] == pytest.approx(20.0)
    change = ex.period_change(yearly, "Export", 2023, 2024)
    assert change["quantity_kg"] == pytest.approx(10.0)          # 200 -> 220 kg
    assert change["value_kusd"] == pytest.approx(-45.0)          # 4.0 -> 2.2
    assert change["unit_value_usd_per_kg"] == pytest.approx(-50.0)
    with pytest.raises(ValueError):
        ex.period_change(yearly, "Import", 2023, 2024)


# --- Statistics ---------------------------------------------------------------------------

def confounded(n=400, seed=1):
    """x and y both driven by size z; x has no effect of its own on y."""
    rng = np.random.default_rng(seed)
    z = 10 ** rng.uniform(0, 3, n)
    x = z ** 0.8 * 10 ** rng.normal(0, 0.3, n)
    y = z ** 1.5 * 10 ** rng.normal(0, 0.3, n)
    return pd.DataFrame({"x": x, "y": y, "z": z, "year": rng.choice([2023, 2024], n),
                         "partner": np.arange(n) % 100})


def test_strength_labels():
    assert st.strength(0.1) == "very weak"
    assert st.strength(0.5) == "moderate positive"
    assert st.strength(-0.85) == "very strong negative"


def test_partial_correlation_removes_a_confounder():
    df = confounded()
    assert st.correlation(df, "x", "y")["r"] > 0.7  # looks related...
    partial = st.partial_correlation(df, "x", "y", ["z"])
    assert abs(partial["r"]) < 0.15  # ...until size is removed
    assert partial["n"] == len(df)


def test_fit_log_ols_recovers_elasticities():
    df = confounded()
    res = st.fit_log_ols(df, "y", ["x", "z"])
    coef = st.tidy_coefficients(res)["coef"]
    assert coef["log_z"] == pytest.approx(1.5, abs=0.1)
    assert coef["log_x"] == pytest.approx(0.0, abs=0.1)
    assert "C(year)[T.2024]" in coef.index


def test_log10_positive_drops_non_positive():
    out = st.log10_positive(pd.Series([100.0, 0.0, -5.0]))
    assert out.iloc[0] == 2 and out.iloc[1:].isna().all()


def test_growth_summary_uses_robust_statistics():
    g = st.growth_summary(pd.Series([10.0, 20.0, 30.0, -50.0, 100000.0, None]))
    assert g["n"] == 5 and g["median_pct"] == 20.0
    assert g["extreme_count"] == 1 and g["share_growing"] == pytest.approx(0.8)
    assert g["mean_pct"] > 10000  # why the mean is not reported


# --- Charts (smoke tests: they render and save) -------------------------------------------

def test_charts_render_and_save(tmp_path):
    shares = ex.market_shares(pd.DataFrame({"p": list("ABC"), "kg": [3.0, 2.0, 1.0]}), "p", "kg")
    figs = {
        "bars": ch.market_share_bars(shares, "t", "s", "src"),
        "change": ch.change_bars(pd.Series({"a": 5.0, "b": -20.0}), "t", "s", "src"),
        "line": ch.line_trend(pd.DataFrame({"year": [2020, 2021], "a": [1, 2], "b": [2, 2.1]}),
                              "year", ["a", "b"], ["A", "B"], "GW", "t", "s", "src"),
        "heat": ch.correlation_heatmap(pd.DataFrame(np.eye(3)), ["a", "b", "c"], "t", "s", "src"),
        "hist": ch.log_histogram(pd.Series([1.0, 10.0, 100.0, 1000.0]), "kg", "t", "s", "src"),
    }
    for name, fig in figs.items():
        path = ch.save(fig, name, tmp_path)
        assert path.exists() and path.stat().st_size > 5000
        ch.plt.close(fig)
