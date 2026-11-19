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


# --- Hypothesis tests and diagnostics -----------------------------------------------------

def test_normality_test_detects_skew_and_log_normality():
    v = pd.Series(10 ** np.random.default_rng(3).normal(3, 1, 300))  # log-normal
    assert not st.normality_test(v)["normal"]
    assert st.normality_test(v, log=True)["normal"]


def test_compare_groups_finds_a_real_difference():
    rng = np.random.default_rng(4)
    df = pd.DataFrame({"g": ["a"] * 50 + ["b"] * 50,
                       "v": np.r_[rng.normal(0, 1, 50), rng.normal(3, 1, 50)]})
    out = st.compare_groups(df, "v", "g")
    assert out["p"] < 0.001 and out["medians"]["b"] > out["medians"]["a"]


def test_paired_change_on_log_ratio():
    df = pd.DataFrame({"who": list("abcdefgh") * 2, "year": [1] * 8 + [2] * 8,
                       "price": [10.0] * 8 + [5.0, 5, 5, 5, 5, 5, 5, 20]})
    out = st.paired_change(df, "who", "year", "price", 1, 2)
    assert out["n"] == 8
    assert out["median_change_pct"] == pytest.approx(-50.0)
    assert out["share_falling"] == pytest.approx(7 / 8)


def test_bootstrap_ci_brackets_the_estimate():
    values = np.random.default_rng(5).lognormal(0, 1, 60)
    ci = st.bootstrap_ci(values, st.top_share, n_boot=500)
    assert ci["ci_low"] <= ci["estimate"] <= ci["ci_high"]
    assert st.top_share([5, 3, 1, 1], k=2) == pytest.approx(0.8)


def test_regression_diagnostics_flag_collinearity():
    df = confounded()
    df["noise"] = 10 ** np.random.default_rng(7).normal(0, 1, len(df))  # independent of z
    clean = st.regression_diagnostics(st.fit_log_ols(df, "y", ["z", "noise"])).set_index("assumption")
    assert clean.loc["No multicollinearity", "ok"]
    # x is built from z, so y ~ x + z is already somewhat collinear (VIF about 6) ...
    built = st.regression_diagnostics(st.fit_log_ols(df, "y", ["x", "z"])).set_index("assumption")
    assert built.loc["No multicollinearity", "value"] > 5
    df["x_copy"] = df["x"] * np.exp(np.random.default_rng(6).normal(0, 0.001, len(df)))
    collinear = st.regression_diagnostics(st.fit_log_ols(df, "y", ["x", "x_copy"]))  # ... a copy is extreme
    assert not collinear.set_index("assumption").loc["No multicollinearity", "ok"]


def test_hypothesis_table_applies_holm_correction():
    table = st.hypothesis_table([
        {"hypothesis": "A", "test": "t", "statistic": 1, "p": 0.01},
        {"hypothesis": "B", "test": "t", "statistic": 1, "p": 0.04},
        {"hypothesis": "C", "test": "t", "statistic": 1, "p": 0.30},
    ])
    assert table["p_holm"].tolist() == pytest.approx([0.03, 0.08, 0.30])
    assert table["result"].tolist() == ["Supported", "Not supported", "Not supported"]


def test_seaborn_charts_render(tmp_path):
    df = confounded(90)
    df["size"] = pd.qcut(df["z"], 3, labels=["Small", "Medium", "Large"])
    pair = ch.pair_plot(df, ["x", "y", "z"], ["X", "Y", "Z"], "size", ["Small", "Medium", "Large"],
                        "t", "s", "src")
    tidy = st.tidy_coefficients(st.fit_log_ols(df, "y", ["x", "z"]))
    coef = ch.coefficient_plot({"model": tidy}, {"log_x": "X", "log_z": "Z"}, "t", "s", "src")
    for name, fig in {"pair": pair, "coef": coef}.items():
        assert ch.save(fig, name, tmp_path).stat().st_size > 5000
        ch.plt.close(fig)


# --- Package and documentation -------------------------------------------------------------

def test_package_exposes_its_modules():
    import src.analysis as pkg
    assert set(pkg.__all__) == {"charts", "exploratory", "statistical"}


def test_api_reference_lists_every_public_function():
    import importlib
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    builder = importlib.import_module("build_api_reference")
    doc = (ROOT / "docs" / "api_reference.md").read_text(encoding="utf-8")
    for package, modules in builder.PACKAGES.items():
        for mod in modules:
            module = importlib.import_module(f"{package}.{mod}")
            for name, _ in builder.public_members(module):
                assert f"**`{name}`**" in doc, f"{package}.{mod}.{name} missing: run build_api_reference.py"


# --- Functions moved out of the notebooks -----------------------------------------------------

def test_table_row_counts_and_missing_by_year(sample_db):
    counts = ex.table_row_counts(sample_db)
    assert list(counts.index) == ex.TABLES and (counts > 0).all()
    df = pd.DataFrame({"year": [1, 1, 2, 2], "a": [1.0, None, None, None]})
    assert ex.missing_by_year(df, ["a"])["a"].tolist() == [50.0, 100.0]


def test_wind_trend_focus_and_fallback():
    wind = pd.DataFrame({
        "country": ["China", "China", "A", "A", "B", "B", "C"],
        "year": [2020, 2021, 2020, 2021, 2020, 2021, 2021],  # C lacks 2020: excluded
        "wind_capacity_gw": [5.0, 30.0, 10.0, 12.0, 1.0, 2.0, 99.0],
    })
    trend, info = ex.wind_trend(wind)
    assert trend.set_index("year").loc[2021].to_dict() == {"China": 30.0, "Other": 14.0}
    assert info["focus_ahead"] is True and info["labels"] == ["China", "Other 2 countries"]
    trend, info = ex.wind_trend(wind[wind["country"] != "China"])
    assert info["series"] == ["All"] and info["focus_ahead"] is None


def test_size_adjusted_residuals_match_partial_correlation():
    df = confounded()
    resid = st.size_adjusted_residuals(df, "x", "y", ["z"])
    r = np.corrcoef(resid["x_resid"], resid["y_resid"])[0, 1]
    assert r == pytest.approx(st.partial_correlation(df, "x", "y", ["z"])["r"])


def test_show_saves_only_when_asked(tmp_path):
    fig = ch.change_bars(pd.Series({"a": 1.0}), "t", "s", "src")
    assert ch.show(fig, "kept", folder=tmp_path).exists()
    fig = ch.change_bars(pd.Series({"a": 1.0}), "t", "s", "src")
    assert ch.show(fig, "skipped", save_figure=False, folder=tmp_path) is None
    assert not (tmp_path / "skipped.png").exists()


# --- Architecture rules --------------------------------------------------------------------

def test_every_analysis_function_has_a_docstring():
    import ast
    for path in sorted((ROOT / "src" / "analysis").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert ast.get_docstring(tree), f"{path.name}: module docstring missing"
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                assert ast.get_docstring(node), f"{path.name}: {node.name}() has no docstring"


@pytest.mark.parametrize("notebook", ["01_data_exploration.ipynb", "02_eda_analysis.ipynb"])
def test_notebooks_import_the_package_and_define_no_functions(notebook):
    import json
    import re
    nb = json.loads((ROOT / "notebooks" / notebook).read_text(encoding="utf-8"))
    code = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    assert "from src.analysis import" in code
    assert not re.search(r"^\s*(def|class) ", code, re.M), "logic belongs in src/analysis"


def test_group_assumptions_runs_shapiro_per_group_and_levene():
    rng = np.random.default_rng(8)
    same = pd.DataFrame({"g": ["a"] * 80 + ["b"] * 80,
                         "v": np.r_[rng.normal(0, 1, 80), rng.normal(2, 1, 80)]})
    out = st.group_assumptions(same, "v", "g").set_index("check")
    assert list(out.index) == ["Normal within a", "Normal within b", "Equal variances across groups"]
    assert out["ok"].all()
    spread = same.assign(v=np.r_[rng.normal(0, 1, 80), rng.normal(0, 6, 80)])
    assert not st.group_assumptions(spread, "v", "g").set_index("check").loc[
        "Equal variances across groups", "ok"]


def test_compare_groups_reports_epsilon_squared():
    rng = np.random.default_rng(4)
    df = pd.DataFrame({"g": ["a"] * 50 + ["b"] * 50,
                       "v": np.r_[rng.normal(0, 1, 50), rng.normal(3, 1, 50)]})
    out = st.compare_groups(df, "v", "g")
    assert out["epsilon_sq"] == pytest.approx(out["statistic"] / 99)
    assert out["effect"] == "large"


def test_paired_change_effect_sizes_and_tests():
    df = pd.DataFrame({"who": list("abcdefgh") * 2, "year": [1] * 8 + [2] * 8,
                       "price": [10.0] * 8 + [5.0, 5, 5, 5, 5, 5, 5, 20]})
    out = st.paired_change(df, "who", "year", "price", 1, 2, test="sign")
    assert out["test"] == "Sign test" and out["p"] == out["sign_p"] == pytest.approx(0.0703, abs=1e-3)
    assert out["statistic"] == 7  # seven of eight fell
    assert out["ci_low_pct"] <= out["median_change_pct"] <= out["ci_high_pct"]
    assert -1 < out["rank_biserial"] < 0
    all_fall = df.assign(price=[10.0] * 8 + [5.0, 4, 6, 3, 7, 2, 8, 9])
    assert st.paired_change(all_fall, "who", "year", "price", 1, 2)["rank_biserial"] == -1
    with pytest.raises(ValueError):
        st.paired_change(df, "who", "year", "price", 1, 2, test="t")


def test_partial_correlation_rank_version_agrees():
    df = confounded()
    pearson = st.partial_correlation(df, "x", "y", ["z"])
    ranks = st.partial_correlation(df, "x", "y", ["z"], method="spearman")
    assert ranks["method"] == "spearman" and abs(ranks["r"] - pearson["r"]) < 0.15


def test_fold_change_and_split_medians():
    assert st.fold_change(1.0) == pytest.approx(10) and st.fold_change(0.0) == pytest.approx(1)
    df = pd.DataFrame({"by": [1, 2, 3, 4], "v": [10.0, 20.0, 30.0, 40.0]})
    assert st.split_medians(df, "v", "by") == {"above": 35.0, "below": 15.0, "n_above": 2,
                                                "n_below": 2}


def test_regression_diagnostics_include_shapiro():
    out = st.regression_diagnostics(st.fit_log_ols(confounded(), "y", ["x", "z"]))
    assert {"Breusch-Pagan", "Shapiro-Wilk", "Jarque-Bera"} <= set(out["test"])


def test_hypothesis_table_leads_with_magnitude_and_effect_size():
    table = st.hypothesis_table([
        {"hypothesis": "A", "test": "t", "statistic": 1, "p": 0.01, "magnitude": "big",
         "effect_size": 0.5},
        {"hypothesis": "B", "test": "t", "statistic": 1, "p": 0.40, "magnitude": "small",
         "effect_size": 0.1},
    ])
    assert list(table.columns[:3]) == ["hypothesis", "magnitude", "effect_size"]
    assert table["statistically_significant"].tolist() == [True, False]


def trade_two_buyers(prices_end, kg_end):
    """Two buyers, A (USD 10/kg) and B (USD 2/kg) in 2023, 50 kg each."""
    kg = [50.0, 50.0, *kg_end]
    price = [10.0, 2.0, *prices_end]
    return pd.DataFrame({"trade_flow": "Export", "year": [2023, 2023, 2024, 2024],
                         "partner": ["A", "B", "A", "B"], "quantity_kg": kg,
                         "trade_value_kusd": [k * p / 1000 for k, p in zip(kg, price)]})


def test_price_mix_decomposition_separates_price_from_mix():
    mix_only = ex.price_mix_decomposition(trade_two_buyers([10.0, 2.0], [10.0, 90.0]), 2023, 2024)
    assert mix_only["price_effect_pct"] == pytest.approx(0)  # nobody's price changed ...
    assert mix_only["mix_effect_pct"] == pytest.approx(mix_only["average_change_pct"])  # ... volume moved
    assert mix_only["average_change_pct"] == pytest.approx((2.8 / 6 - 1) * 100)
    price_only = ex.price_mix_decomposition(trade_two_buyers([5.0, 1.0], [50.0, 50.0]), 2023, 2024)
    assert price_only["price_effect_pct"] == pytest.approx(-50)
    assert price_only["mix_effect_pct"] == pytest.approx(0)
    assert price_only["volume_share_price_fell"] == pytest.approx(1)
    without_a = ex.price_mix_decomposition(trade_two_buyers([5.0, 1.0], [50.0, 50.0]), 2023, 2024,
                                           exclude=["A"])
    assert without_a["buyers"] == 1


def test_buyer_price_changes_in_dollars_per_kg():
    out = ex.buyer_price_changes(trade_two_buyers([5.0, 1.0], [50.0, 50.0]), 2023, 2024)
    assert out.loc["A", "price_start"] == pytest.approx(10) and out.loc["A", "price_end"] == pytest.approx(5)
    assert out["volume_share_start"].sum() == pytest.approx(1)


def test_growth_vs_wind_ratio():
    panel = pd.DataFrame({"country": ["A", "B", "C"], "year": [2024, 2024, 2023],
                          "import_growth_pct": [100.0, -50.0, 10.0],
                          "wind_generation_change_twh": [1.0, -0.5, 2.0]})
    out = ex.growth_vs_wind(panel, 2024)
    assert out["import_ratio"].tolist() == [2.0, 0.5]


def test_relationship_scatter_renders(tmp_path):
    df = pd.DataFrame({"x": [-2.0, -0.05, 0.0, 0.5, 20.0], "y": [0.1, 1.0, 3.0, 0.5, 50.0]})
    fig = ch.relationship_scatter(df, "x", "y", "X", "Y", "t", "s", "src", note="rho",
                                  xscale="symlog", yscale="log", ref_x=0, ref_y=1)
    assert ch.save(fig, "scatter", tmp_path).stat().st_size > 5000
    ch.plt.close(fig)


def test_buyer_volumes_sums_one_year_and_direction():
    trade = pd.DataFrame({"trade_flow": ["Export", "Export", "Import", "Export"],
                          "year": [2024, 2024, 2024, 2023], "partner": ["A", "A", "A", "B"],
                          "quantity_kg": [1.0, 2.0, 50.0, 7.0]})
    assert ex.buyer_volumes(trade, 2024).to_dict() == {"A": 3.0}


# --- Regression checks: descriptive table, PPML, change regressions, missing years ----------

def test_descriptive_table_adds_a_log10_row_with_normality():
    rng = np.random.default_rng(5)
    df = pd.DataFrame({"y": 10 ** rng.normal(3, 1, 200), "z": rng.normal(0, 1, 200)})  # log-normal y
    out = st.descriptive_table(df, ["y", "z"], log_columns=["y"], labels={"y": "Imports"})
    assert list(out.index) == ["Imports", "log10 Imports", "z"]
    assert not out.loc["Imports", "normal"] and out.loc["Imports", "skew"] > 2  # skewed raw ...
    assert out.loc["log10 Imports", "normal"]                                   # ... normal in logs
    assert out.loc["Imports", "median"] == pytest.approx(df["y"].median())


def test_correlation_matrix_can_use_log_values():
    df = pd.DataFrame({"a": [1.0, 10.0, 100.0, 1000.0], "b": [2.0, 20.0, 200.0, 2000.0]})
    assert st.correlation_matrix(df, ["a", "b"], "pearson", log=True).loc["a", "b"] == pytest.approx(1)


def test_fit_ppml_recovers_elasticities_and_keeps_zeros():
    df = confounded()
    df.loc[:9, "y"] = 0.0  # zero imports: dropped by a log model, kept by PPML
    coef = st.tidy_coefficients(st.fit_ppml(df, "y", ["x", "z"]))["coef"]
    assert coef["log_z"] == pytest.approx(1.5, abs=0.2)
    assert coef["log_x"] == pytest.approx(0.0, abs=0.2)
    assert int(st.fit_ppml(df, "y", ["x", "z"]).nobs) == len(df)


def test_log_change_ols_recovers_a_growth_elasticity_and_a_mean_change():
    rng = np.random.default_rng(3)
    n = 300
    x0, g = 10 ** rng.uniform(0, 3, n), np.exp(rng.normal(0, 0.5, n))
    y0 = 10 ** rng.uniform(0, 3, n)
    df = pd.DataFrame({"c": np.r_[np.arange(n), np.arange(n)], "t": [1] * n + [2] * n,
                       "x": np.r_[x0, x0 * g],
                       "y": np.r_[y0, y0 * g ** 0.7 * np.exp(rng.normal(0, 0.1, n))]})
    slope = st.coefficient_evidence(st.fit_log_change_ols(df, "y", ["x"], "c", "t", 1, 2), "dlog_x")
    assert slope["coef"] == pytest.approx(0.7, abs=0.05) and slope["n"] == n
    halved = pd.DataFrame({"c": ["a", "b", "a", "b"], "t": [1, 1, 2, 2], "p": [10.0, 4.0, 5.0, 2.0]})
    mean = st.coefficient_evidence(st.fit_log_change_ols(halved, "p", [], "c", "t", 1, 2), "Intercept")
    assert st.log_ratio_to_pct(mean["coef"]) == pytest.approx(-50)
    changes = st.log_changes(halved, ["p"], "c", "t", 1, 2)
    assert changes["ratio_p"].tolist() == pytest.approx([0.5, 0.5])


def test_coefficient_evidence_and_compare_models_give_fold_changes():
    res = st.fit_log_ols(confounded(), "y", ["x", "z"])
    ev = st.coefficient_evidence(res, "log_z")
    assert ev["fold"] == pytest.approx(10 ** ev["coef"])
    assert ev["fold_low"] < ev["fold"] < ev["fold_high"]
    assert 0 <= ev["residual_shapiro_p"] <= 1
    table = st.compare_models({"A": res, "B": res}, ["log_x", "log_z"])
    assert list(table["model"]) == ["A", "A", "B", "B"]
    assert table.loc[1, "fold_10x"] == pytest.approx(ev["fold"])


def panel_with_gaps():
    """Partners A (both years), B (2023 only), C (2024 only), D (neither); E has no wind."""
    return pd.DataFrame({
        "partner": list("AABBCCDDEE"), "country": list("AABBCCDDEE"),
        "year": [2023, 2024] * 5,
        "imports_from_china_kg": [100.0, 200.0, 5.0, np.nan, np.nan, 8.0, np.nan, np.nan, 50.0, 60.0],
        "wind_capacity_gw": [1.0] * 8 + [np.nan, np.nan],
        "total_generation_twh": [10.0, 11.0, 2.0, 2.0, 3.0, 3.0, 1.0, 1.0, 5.0, 5.0]})


def test_import_year_pattern_finds_partners_that_skip_years():
    out = ex.import_year_pattern(panel_with_gaps(), 2023, 2024)
    assert out.loc[list("ABCD"), "pattern"].tolist() == ["Both years", "2023 only", "2024 only", "Neither"]
    assert out.loc[list("ABD"), "buyer_type"].tolist() == ["Every year", "Skipped a year", "Never"]
    assert out.loc["A", "typical_kg"] == 150 and np.isnan(out.loc["D", "typical_kg"])


def test_analysis_sample_can_keep_non_buyers_as_zero():
    panel = panel_with_gaps()
    buyers = ex.analysis_sample(panel)
    assert len(buyers) == 4  # A twice, B 2023, C 2024; E has no wind data
    everyone = ex.analysis_sample(panel, include_non_buyers=True)
    assert len(everyone) == 8 and (everyone["imports_from_china_kg"] == 0).sum() == 4


def test_balanced_panel_keeps_entities_seen_in_every_period():
    buyers = ex.analysis_sample(panel_with_gaps())
    assert ex.balanced_panel(buyers)["country"].tolist() == ["A", "A"]


def test_within_share_separates_change_over_time_from_differences_between_entities():
    fixed = pd.DataFrame({"country": list("AABB"), "v": [10.0, 10.0, 1000.0, 1000.0]})
    assert st.within_share(fixed, "v") == pytest.approx(0)  # no country ever changes
    moving = pd.DataFrame({"country": list("AABB"), "v": [10.0, 1000.0, 10.0, 1000.0]})
    assert st.within_share(moving, "v") == pytest.approx(1)  # all variation is over time


def test_relationship_scatter_labels_a_narrow_log_axis_and_moves_the_note(tmp_path):
    df = pd.DataFrame({"x": [0.72, 0.9, 1.0, 1.4, 2.0], "y": [0.1, 1.0, 3.0, 0.5, 50.0]})
    fig = ch.relationship_scatter(df, "x", "y", "X", "Y", "t", "s", "src", note="b = 0.1",
                                  xscale="log", yscale="log", ref_x=1, ref_y=1, note_loc="upper right")
    ax = fig.axes[0]
    fig.canvas.draw()
    shown = [t.get_text() for t in ax.get_xticklabels() if t.get_text()]
    assert {"1", "1.5", "2"} <= set(shown)  # not just "1" plus a "2 x 10^0" minor label
    note = [t for t in ax.texts if t.get_text() == "b = 0.1"][0]
    assert note.get_ha() == "right"
    ch.plt.close(fig)
