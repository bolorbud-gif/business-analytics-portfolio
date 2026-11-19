"""Tests for the analytics engine (src/modeling). They use synthetic data, so they run without
the restricted source files."""

import copy

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

from sklearn.linear_model import LinearRegression  # noqa: E402

from src.analysis import charts as ch  # noqa: E402
from src.modeling import evaluate as ev  # noqa: E402
from src.modeling import predict as pr  # noqa: E402
from src.modeling import train as tr  # noqa: E402

CONFIG = tr.load_config()


@pytest.fixture(scope="module")
def data():
    return tr.synthetic_dataset(CONFIG)


@pytest.fixture(scope="module")
def quick_config():
    """The real settings with one-value grids and 3 folds, so the whole engine trains fast."""
    cfg = copy.deepcopy(CONFIG)
    cfg["split"]["cv_folds"] = 3
    cfg["tuning"] = {"regression": {"ridge": {"model__alpha": [1.0]},
                                    "random_forest": {"model__max_depth": [3], "model__min_samples_leaf": [3]}},
                     "classification": {"logistic": {"model__C": [1.0]},
                                        "random_forest": {"model__max_depth": [3], "model__min_samples_leaf": [3]}}}
    return cfg


@pytest.fixture(scope="module")
def engine(data, quick_config):
    return tr.train_engine(data, quick_config)


# --- Data and split ---------------------------------------------------------------------------

def test_features_never_include_the_target_or_trade_columns():
    features = set(tr.feature_columns(CONFIG))
    assert not features & set(CONFIG["features"]["forbidden"])
    assert not features & {CONFIG["target"]["column"], "log10_imports", "major_buyer"}


def test_synthetic_dataset_has_the_engine_columns_and_both_classes(data):
    assert set(tr.feature_columns(CONFIG)) <= set(data.columns)
    assert data["major_buyer"].nunique() == 2
    assert data.groupby("country")["year"].nunique().eq(2).all()


def test_split_by_country_keeps_each_country_on_one_side(data):
    train, test = tr.split_by_country(data, CONFIG)
    assert not set(train["country"]) & set(test["country"])
    assert len(train) + len(test) == len(data)
    assert 0.15 < len(test) / len(data) < 0.35
    assert test["major_buyer"].nunique() == 2


# --- Pipeline: preprocessing learns from training rows only -----------------------------------

def test_pipeline_learns_medians_and_scales_from_training_rows_only(data):
    train, test = tr.split_by_country(data, CONFIG)
    train = train.copy()
    train.loc[0, "demand_twh"] = np.nan          # forces the imputer to use a median
    test = test.assign(demand_twh=test["demand_twh"] * 1000)  # test rows look very different
    pipe = tr.build_pipeline(LinearRegression(), CONFIG)
    pipe.fit(train[tr.feature_columns(CONFIG)], train["log10_imports"])
    size = pipe.named_steps["prep"].named_transformers_["size"]
    col = CONFIG["features"]["size"].index("demand_twh")
    assert size.named_steps["impute"].statistics_[col] == pytest.approx(train["demand_twh"].median())
    expected_mean = np.log10(train["demand_twh"].fillna(train["demand_twh"].median())).mean()
    assert size.named_steps["scale"].mean_[col] == pytest.approx(expected_mean)


def test_safe_log10_keeps_zero_finite_and_is_importable_for_saving():
    assert tr.safe_log10(np.array([[0.0, 100.0]])).tolist() == [[-3.0, 2.0]]
    log_step = tr.build_preprocessor(CONFIG).transformers[0][1].named_steps["log10"]
    assert log_step.func.__module__ == "src.modeling.train"  # never __main__: loadable later


# --- Metrics ----------------------------------------------------------------------------------

def test_regression_metrics_match_their_definitions():
    m = ev.regression_metrics([1.0, 2.0, 3.0], [1.0, 2.0, 5.0])
    assert m["MAE"] == pytest.approx(2 / 3)
    assert m["RMSE"] == pytest.approx(np.sqrt(4 / 3))
    assert m["R2"] == pytest.approx(1 - 4 / 2)
    assert m["error_factor"] == pytest.approx(10 ** (2 / 3))


def test_classification_metrics_match_their_definitions():
    y = [1, 1, 1, 0, 0, 0]
    score = [0.9, 0.8, 0.3, 0.6, 0.2, 0.1]          # flags 3 at 0.5: two right, one wrong
    m = ev.classification_metrics(y, score, threshold=0.5)
    assert (m["precision"], m["recall"]) == (pytest.approx(2 / 3), pytest.approx(2 / 3))
    assert m["F1"] == pytest.approx(2 / 3)
    assert m["AUC"] == pytest.approx(8 / 9)          # 8 of 9 positive-negative pairs ranked right
    stricter = ev.classification_metrics(y, score, threshold=0.85)
    assert stricter["precision"] == 1 and stricter["recall"] == pytest.approx(1 / 3)
    point = ev.operating_point(y, score, 0.5)
    assert point == {"fpr": pytest.approx(1 / 3), "tpr": pytest.approx(2 / 3)}


def test_threshold_table_trades_recall_for_precision():
    y = [1, 1, 1, 0, 0, 0]
    table = ev.threshold_table(y, [0.9, 0.8, 0.3, 0.6, 0.2, 0.1], thresholds=(0.25, 0.85))
    assert table["recall"].tolist() == pytest.approx([1.0, 1 / 3])
    assert table["precision"].tolist() == pytest.approx([0.75, 1.0])


# --- Cross-validation, tuning and leakage -----------------------------------------------------

def test_random_folds_overstate_performance_when_countries_repeat(data):
    from sklearn.ensemble import RandomForestRegressor
    pipe = tr.build_pipeline(RandomForestRegressor(n_estimators=100, random_state=0), CONFIG)
    X, y, g = data[tr.feature_columns(CONFIG)], data["log10_imports"], data["country"]
    table = ev.random_vs_group_cv(pipe, X, y, g)
    assert table.loc["Random rows (leaky)", "MAE"] < table.loc["By country (GroupKFold)", "MAE"]


def test_scoring_on_training_rows_is_the_most_optimistic(data):
    X, y, g = data[tr.feature_columns(CONFIG)], data["log10_imports"], data["country"]
    table = ev.classic_leak_vs_pipeline(tr.build_pipeline(LinearRegression(), CONFIG), X, y, g, "regression")
    assert len(table) == 3
    assert table["MAE"].idxmin() == "No split: score on the training rows"


def test_leakage_screen_flags_trade_columns_and_near_copies(data):
    d = data.assign(copy_of_target=data["log10_imports"] * 2 + 1)
    cols = tr.feature_columns(CONFIG) + CONFIG["features"]["forbidden"] + ["copy_of_target"]
    table = ev.leakage_screen(d, cols, "log10_imports", CONFIG["features"]["forbidden"]).set_index("column")
    assert table.loc["copy_of_target", "flagged"]
    assert table.loc["imports_from_china_value_kusd", "flagged"]
    assert not table.loc["year", "flagged"]


def test_nested_cv_tunes_inside_each_outer_fold(data, quick_config):
    pipe, grid = tr.candidates("regression", quick_config)["Ridge regression"]
    X, y, g = data[tr.feature_columns(CONFIG)], data["log10_imports"], data["country"]
    folds = ev.nested_cv(pipe, {"model__alpha": [0.1, 10.0]}, X, y, g, "regression", n_splits=3)
    assert len(folds) == 3 and folds["params"].map(lambda p: "model__alpha" in p).all()


def test_choose_threshold_picks_from_the_grid_and_prefers_half_on_ties():
    from sklearn.dummy import DummyClassifier
    from sklearn.model_selection import GroupKFold
    X = pd.DataFrame({"x": range(20)})
    y = pd.Series([1, 0] * 10)
    g = pd.Series(np.repeat(range(10), 2))
    t = ev.choose_threshold(DummyClassifier(strategy="prior"), X, y, g, GroupKFold(5))
    assert t == 0.5  # constant 0.5 probability: every threshold up to 0.5 ties; 0.5 is kept


# --- The whole engine -------------------------------------------------------------------------

def test_engine_beats_the_dummy_baseline_on_unseen_countries(engine):
    reg, clf = engine["regression"], engine["classification"]
    assert reg["model"]["test"]["MAE"] < reg["baseline"]["test"]["MAE"]
    assert clf["model"]["test"]["AUC"] > clf["baseline"]["test"]["AUC"]
    assert reg["summary"].loc[0, "model"].startswith("Baseline")
    assert reg["best"] != reg["summary"].loc[0, "model"]


def test_saved_engine_reloads_and_predicts_the_same(engine, quick_config, tmp_path):
    bundle = tr.model_bundle(engine, quick_config, "synthetic")
    path = tr.save_bundle(bundle, tmp_path / "engine.joblib")
    loaded = pr.load_engine(path)
    sample = engine["test"]
    out = pr.predict(loaded, sample)
    direct = engine["regression"]["final"].predict(sample[tr.feature_columns(CONFIG)])
    assert out["predicted_log10_kg"].to_numpy() == pytest.approx(direct)
    assert out["predicted_kg"].to_numpy() == pytest.approx(10 ** direct)
    assert out["major_buyer_call"].tolist() == (out["p_major_buyer"] >= loaded["threshold"]).tolist()
    assert loaded["trained_on"]["rows"] == len(engine["data"])


def test_expected_vs_actual_compares_imports_with_the_estimate(engine, quick_config):
    bundle = tr.model_bundle(engine, quick_config, "synthetic")
    rows = engine["data"][engine["data"]["year"] == 2024]
    table = pr.expected_vs_actual(bundle, rows)
    assert table["predicted_kg"].is_monotonic_decreasing
    assert table["ratio_actual_to_expected"].to_numpy() == pytest.approx(
        (table["imports_from_china_kg"] / table["predicted_kg"]).to_numpy())


def test_load_engine_explains_a_missing_or_wrong_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Train it first"):
        pr.load_engine(tmp_path / "nothing.joblib")
    import joblib
    joblib.dump({"not": "an engine"}, tmp_path / "wrong.joblib")
    with pytest.raises(ValueError, match="not an engine bundle"):
        pr.load_engine(tmp_path / "wrong.joblib")


def test_predict_names_missing_feature_columns(engine, quick_config):
    bundle = tr.model_bundle(engine, quick_config, "synthetic")
    with pytest.raises(ValueError, match="demand_twh"):
        pr.predict(bundle, engine["test"].drop(columns="demand_twh"))


# --- Charts -----------------------------------------------------------------------------------

def test_engine_charts_render(engine, tmp_path):
    reg, clf = engine["regression"], engine["classification"]
    fig = ch.cv_comparison({"Regression": (reg["summary"], "MAE", "MAE"),
                            "Classification": (clf["summary"], "AUC", "AUC")},
                           "t", "s", "src", chosen={"Regression": reg["best"]})
    assert ch.save(fig, "cv", tmp_path).stat().st_size > 5000
    test = engine["test"]
    pred = reg["model"]["fitted"].predict(test[tr.feature_columns(CONFIG)])
    fig = ch.predicted_vs_actual(10 ** test["log10_imports"], 10 ** pred, test["country"], "t", "s", "src", note="MAE")
    assert ch.save(fig, "pva", tmp_path).stat().st_size > 5000
    p = clf["model"]["fitted"].predict_proba(test[tr.feature_columns(CONFIG)])[:, 1]
    fig = ch.roc_chart({"Test": ev.roc_points(test["major_buyer"], p)}, "t", "s", "src",
                       marker=(0.2, 0.8, "threshold 0.5"))
    assert ch.save(fig, "roc", tmp_path).stat().st_size > 5000
    for f in ("cv", "pva", "roc"):
        ch.plt.close("all")


# --- Analytics checklist ----------------------------------------------------------------------

def test_problem_types_are_stated_in_the_saved_bundle(engine, quick_config):
    bundle = tr.model_bundle(engine, quick_config, "synthetic")
    assert set(bundle["problem_types"]) == {"regression", "classification"}
    assert all(text.startswith("Supervised") for text in bundle["problem_types"].values())


def test_every_estimator_and_splitter_uses_the_configured_random_state():
    seed = CONFIG["split"]["random_state"]
    for task in tr.TASKS:
        for name, (pipe, _) in tr.candidates(task, CONFIG).items():
            params = pipe.named_steps["model"].get_params()
            if "random_state" in params:
                assert params["random_state"] == seed, f"{task}: {name}"
    assert ev.group_folds("classification", 5, seed).random_state == seed


def test_every_feature_has_documented_availability_and_none_comes_from_trade(data):
    table = ev.feature_availability(data, CONFIG)
    assert list(table["feature"]) == tr.feature_columns(CONFIG)
    assert not table["known_when"].eq("NOT DOCUMENTED").any()
    assert not table["from_trade_records"].any()
    assert table["share_present"].between(0, 1).all()


@pytest.fixture(scope="module")
def sample_con(tmp_path_factory):
    """The committed synthetic sample (2022-2024) built into a fresh database."""
    from src.analysis import exploratory as ex
    from src.data_pipeline.pipeline import run_pipeline
    tmp = tmp_path_factory.mktemp("db")
    run_pipeline(tr.ROOT / "data" / "sample", {"trade": "data1.xlsx", "electricity": "data2.xlsx"},
                 f"sqlite:///{tmp / 'sample.db'}", rejected_dir=tmp / "rejected")
    con, _ = ex.open_database(tmp / "sample.db")
    yield con
    con.close()


def test_lagged_features_use_the_previous_years_power_data(sample_con):
    same = tr.load_features(sample_con, [2023]).set_index("partner")
    lagged = tr.load_features(sample_con, [2024], lag=1).set_index("partner")
    common = same.index.intersection(lagged.index)
    assert len(common) > 0
    for col in ["total_generation_twh", "wind_capacity_gw", "solar_capacity_gw"]:
        assert lagged.loc[common, col].to_numpy() == pytest.approx(same.loc[common, col].to_numpy())
    assert (lagged["year"] == 2024).all()  # the target year stays 2024


def test_expected_cost_and_the_cost_based_threshold():
    y = np.array([1, 1, 1, 0, 0, 0])
    score = np.array([0.9, 0.8, 0.3, 0.6, 0.2, 0.1])
    costs = {"false_negative": 3, "false_positive": 1}
    assert ev.expected_cost(y, score, 0.5, costs) == pytest.approx((3 * 1 + 1 * 1) / 6)
    misses_cost_more = ev.best_threshold(y, score, {"false_negative": 10, "false_positive": 1})
    false_alarms_cost_more = ev.best_threshold(y, score, {"false_negative": 1, "false_positive": 10})
    assert misses_cost_more < false_alarms_cost_more  # expensive misses -> flag more countries
    assert "cost" in ev.classification_metrics(y, score, 0.5, costs)


def test_engine_reports_cost_and_its_spread_for_classification(engine):
    summary = engine["classification"]["summary"]
    assert {"cost", "cost_sd", "AUC_sd"} <= set(summary.columns)
    assert "MAE_sd" in engine["regression"]["summary"].columns


def test_bootstrap_ci_resamples_countries_and_brackets_the_estimate(engine):
    test = engine["test"]
    pred = engine["regression"]["model"]["fitted"].predict(test[tr.feature_columns(CONFIG)])
    ci = ev.bootstrap_ci(test["log10_imports"], pred, test["country"], "regression", "MAE", n_boot=300)
    assert ci["ci_low"] <= ci["estimate"] <= ci["ci_high"]
    assert ci["estimate"] == pytest.approx(engine["regression"]["model"]["test"]["MAE"])


def test_split_comparison_scores_by_country_and_by_time(data):
    pipe = tr.build_pipeline(LinearRegression(), CONFIG)
    table = ev.split_comparison({"same year": data}, pipe, tr.feature_columns(CONFIG), "log10_imports",
                                "regression", [2023], [2024], n_splits=3)
    assert table["split"].tolist() == ["By country (cross-validated)", "By time: train 2023, test 2024"]
    assert table["MAE"].notna().all()


def test_bundle_records_provenance(engine, quick_config):
    bundle = tr.model_bundle(engine, quick_config, "synthetic")
    record = bundle["provenance"]
    assert len(record["data"]["sha256"]) == 64 and record["data"]["rows"] == len(engine["data"])
    assert record["config"] == quick_config and record["random_state"] == quick_config["split"]["random_state"]
    assert {"commit", "uncommitted_changes"} <= set(record["code"])
    assert {"python", "scikit-learn", "numpy"} <= set(record["environment"])
    cols = ["country", "year", "log10_imports"]
    data = engine["data"]
    assert tr.data_fingerprint(data, cols) == tr.data_fingerprint(data.copy(), cols)
    changed = data.copy()
    changed.loc[0, "log10_imports"] += 1
    assert tr.data_fingerprint(changed, cols) != tr.data_fingerprint(data, cols)


def test_recommend_turns_predictions_into_actions():
    bundle = {"target": {"major_buyer_kg": 10000}, "actions": {"far_above": 10, "far_below": 0.1}}
    table = pd.DataFrame({
        "country": ["New", "Tiny", "Hub", "Under", "Big", "Small", "Lagging"],
        "imports_from_china_kg": [np.nan, np.nan, 50000, 500, 200000, 300, 20000],
        "predicted_kg": [30000, 100, 1000, 40000, 150000, 400, 400000],
        "major_buyer_call": [True, False, False, True, True, False, True]})
    table["ratio_actual_to_expected"] = table["imports_from_china_kg"] / table["predicted_kg"]
    out = pr.recommend(table, bundle).set_index("country")["action"]
    assert out.to_dict() == {"New": "Approach", "Tiny": "Low priority", "Hub": "Verify", "Under": "Grow",
                             "Big": "Keep", "Small": "Low priority", "Lagging": "Grow"}
