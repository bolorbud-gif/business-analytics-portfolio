"""Train the analytics engine: data, pipelines, split, tuning, final evaluation, saving.

Problem type: supervised learning with two tasks on the same rows (not clustering: every
row has a known outcome to learn from).
- Regression: a country's yearly imports of Chinese rare-earth compounds (HS 284690), log10 kg.
- Binary classification: is it a major buyer (at least target.major_buyer_kg a year)?
Only power-sector data are features. Use: size the market in countries without reliable
trade records, and flag countries that buy far more or less than their power sector suggests.

Run from the project root:
    uv run python -m src.modeling.train

Settings live in config/model_params.yaml. The workflow, in order:
1. Load the features and target; drop nothing silently.
2. Hold out a test set of whole countries (never seen in training or tuning).
3. For each candidate, including the dummy baseline: nested cross-validation by country.
4. Pick the best candidate on cross-validation (not on the test set).
5. Tune it on the whole training set and score it once on the test set.
6. Refit on all the data and save the pipeline with its metadata.
"""

import argparse
import hashlib
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from src.analysis import exploratory as ex
from src.modeling import evaluate as ev

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "model_params.yaml"
LOG_FLOOR = 0.001  # 1 MW or 1 GWh: keeps log10 finite for countries with no solar or wind
TASKS = ("regression", "classification")
PROBLEM_TYPES = {"regression": "Supervised regression: imports from China, log10 kg",
                 "classification": "Supervised binary classification: major buyer or not"}
# Columns that come from the power data (data2.xlsx); shifted together when features are lagged
POWER_COLUMNS = ["wind_generation_twh", "wind_generation_change_twh", "wind_capacity_gw",
                 "total_generation_twh", "renewables_twh", "wind_share_pct", "renewables_share_pct",
                 "solar_capacity_gw", "demand_twh", "emissions_intensity_g_per_kwh"]


# --- Settings and data ------------------------------------------------------------------------

def load_config(path: Path = CONFIG) -> dict:
    """Read the engine's settings (features, target, split, tuning grids, output path)."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def feature_columns(config: dict) -> list[str]:
    """Every feature the models use, size features first."""
    return config["features"]["size"] + config["features"]["other"]


def load_features(con, years: list[int], lag: int = 0) -> pd.DataFrame:
    """One row per partner country and year with power data: the engine's features, the
    actual imports from China (NaN = none recorded) and the trade value.

    Only electricity data are features. The trade value is kept so the leakage check can
    show why it must not be used: it comes from the same trade records as the target.
    lag=1 pairs each year's imports with the previous year's power data, which is already
    published when the year starts: the setting for a forecast.
    """
    panel = ex.load_country_panel(con)
    power = pd.read_sql("""
        SELECT country, year,
               MAX(CASE WHEN source = 'Solar' THEN capacity_gw END) AS solar_capacity_gw,
               MAX(CASE WHEN source = 'Demand' THEN generation_twh END) AS demand_twh,
               MAX(CASE WHEN source = 'Total generation' THEN emissions_intensity_g_per_kwh END)
                   AS emissions_intensity_g_per_kwh
        FROM electricity_generation_detail
        GROUP BY country, year
    """, con)
    value = pd.read_sql("SELECT partner, year, imports_from_china_value_kusd FROM trade_wind_wide", con)
    d = (panel.merge(power, on=["country", "year"], how="left")
              .merge(value, on=["partner", "year"], how="left"))
    if lag:
        earlier = d[["partner", "year", *POWER_COLUMNS]].assign(year=d["year"] + lag)
        d = d.drop(columns=POWER_COLUMNS).merge(earlier, on=["partner", "year"], how="left")
    return d[d["year"].isin(years) & (d["total_generation_twh"] > 0)].reset_index(drop=True)


def load_dataset(con, config: dict, lag: int | None = None) -> pd.DataFrame:
    """The modeling data: the Assignment 5 analysis sample (country-years with imports, wind
    capacity and total generation all positive), with the two targets added.

    log10_imports is the regression target; major_buyer (imports of at least
    target.major_buyer_kg in the year) is the classification target. lag defaults to
    data.feature_lag_years in the config (0: same-year power data).
    """
    t = config["target"]
    lag = config["data"].get("feature_lag_years", 0) if lag is None else lag
    d = load_features(con, config["data"]["years"], lag)
    d = d[(d[t["column"]] > 0) & (d["wind_capacity_gw"] > 0)].reset_index(drop=True)
    d["log10_imports"] = np.log10(d[t["column"]])
    d["major_buyer"] = (d[t["column"]] >= t["major_buyer_kg"]).astype(int)
    return d


def synthetic_dataset(config: dict, n_countries: int = 60, seed: int = 751) -> pd.DataFrame:
    """Random data with the same columns as load_dataset, for running the notebook and the
    tests without the restricted data. The numbers are fake.

    Like the real data, imports rise steeply with country size (elasticity about 1.7), each
    country has a persistent level of its own, and the trade value tracks the quantity.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_countries):
        size = 10 ** rng.uniform(0.7, 3.6)            # total generation, TWh
        wind_share, solar_share = rng.uniform(0.005, 0.3), rng.uniform(0.005, 0.2)
        country_level = rng.normal(0, 0.9)            # persistent: same in both years
        previous = None
        for year in config["data"]["years"]:
            gen = size * rng.uniform(0.97, 1.05)
            kg = 10 ** (1.7 * np.log10(gen) + country_level + rng.normal(0, 0.3))
            rows.append({
                "partner": f"Country {i + 1:02d}", "country": f"Country {i + 1:02d}", "year": year,
                "total_generation_twh": gen, "demand_twh": gen * rng.uniform(0.95, 1.1),
                "wind_generation_twh": gen * wind_share,
                "wind_capacity_gw": gen * wind_share / rng.uniform(2, 3),
                "solar_capacity_gw": gen * solar_share / rng.uniform(1, 1.5),
                "renewables_share_pct": (wind_share + solar_share + rng.uniform(0, 0.4)) * 100,
                "emissions_intensity_g_per_kwh": rng.uniform(50, 800),
                config["target"]["column"]: kg,
                "imports_from_china_value_kusd": kg * 10 ** rng.normal(1.2, 0.4) / 1000,
                "import_growth_pct": (kg / previous - 1) * 100 if previous else np.nan,
            })
            previous = kg
    d = pd.DataFrame(rows)
    d["log10_imports"] = np.log10(d[config["target"]["column"]])
    d["major_buyer"] = (d[config["target"]["column"]] >= config["target"]["major_buyer_kg"]).astype(int)
    return d


def targets(config: dict) -> dict:
    """The column each task predicts."""
    return {"regression": "log10_imports", "classification": "major_buyer"}


# --- Pipelines --------------------------------------------------------------------------------

def safe_log10(X):
    """log10 with a floor of LOG_FLOOR, so a zero (no solar, no wind) stays finite."""
    return np.log10(np.clip(np.asarray(X, dtype=float), LOG_FLOOR, None))


def build_preprocessor(config: dict) -> ColumnTransformer:
    """Preprocessing that is fitted on training rows only, because it sits in the pipeline.

    Size features (capacity, generation, demand) are skewed, so: fill missing values with
    the training median, take log10, standardize. Shares, intensity and year: fill missing
    with the median, standardize.
    """
    size = Pipeline([("impute", SimpleImputer(strategy="median")),
                     ("log10", FunctionTransformer(safe_log10, feature_names_out="one-to-one")),
                     ("scale", StandardScaler())])
    other = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    return ColumnTransformer([("size", size, config["features"]["size"]),
                              ("other", other, config["features"]["other"])])


def build_pipeline(estimator, config: dict) -> Pipeline:
    """Preprocessing and model in one object, so every fit (in CV, tuning or final training)
    learns the medians and scales from the training rows alone."""
    return Pipeline([("prep", build_preprocessor(config)), ("model", estimator)])


def candidates(task: str, config: dict) -> dict:
    """The models to compare, each as (pipeline, hyperparameter grid). The first is always
    the dummy baseline, which ignores the features."""
    seed = config["split"]["random_state"]
    grids = config["tuning"][task]
    if task == "regression":
        models = {
            "Baseline: mean (DummyRegressor)": (DummyRegressor(strategy="mean"), {}),
            # No hyperparameters to tune; Ridge is its tuned, regularised version
            "Linear regression (log-log OLS)": (LinearRegression(), {}),
            "Ridge regression": (Ridge(random_state=seed), grids["ridge"]),
            "Random forest": (RandomForestRegressor(n_estimators=100, random_state=seed), grids["random_forest"]),
        }
    else:
        models = {
            "Baseline: class share (DummyClassifier)": (DummyClassifier(strategy="prior", random_state=seed), {}),
            "Logistic regression": (LogisticRegression(max_iter=2000, random_state=seed), grids["logistic"]),
            "Random forest": (RandomForestClassifier(n_estimators=100, random_state=seed), grids["random_forest"]),
        }
    return {name: (build_pipeline(est, config), grid) for name, (est, grid) in models.items()}


# --- Split, select, train ---------------------------------------------------------------------

def split_by_country(df: pd.DataFrame, config: dict, label: str = "major_buyer",
                     group: str = "country") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hold out whole countries as the test set, stratified on the major-buyer label.

    A country's 2023 and 2024 rows always land on the same side, so the test set measures
    performance on countries the engine has never seen.
    """
    s = config["split"]
    folds = StratifiedGroupKFold(n_splits=round(1 / s["test_share"]), shuffle=True,
                                 random_state=s["random_state"])
    train_idx, test_idx = next(folds.split(df, df[label], df[group]))
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)


def select_model(task: str, train: pd.DataFrame, config: dict, group: str = "country") -> dict:
    """Nested cross-validation of every candidate on the training set; the best one wins.

    The test set isn't touched here. Returns the per-fold results, the summary table and
    the winner's name (lowest MAE, or highest AUC).
    """
    X, y, groups = train[feature_columns(config)], train[targets(config)[task]], train[group]
    folds = config["split"]["cv_folds"]
    seed = config["split"]["random_state"]
    costs = config["costs"] if task == "classification" else None
    results = {name: ev.nested_cv(pipe, grid, X, y, groups, task, folds, seed, costs)
               for name, (pipe, grid) in candidates(task, config).items()}
    table = ev.summarize_cv(results, task)
    contenders = table.iloc[1:]
    best = (contenders.loc[contenders["MAE"].idxmin()] if task == "regression"
            else contenders.loc[contenders["AUC"].idxmax()])["model"]
    return {"folds": results, "summary": table, "best": best}


def fit_and_test(task: str, name: str, train: pd.DataFrame, test: pd.DataFrame, config: dict,
                 group: str = "country") -> dict:
    """Tune the chosen candidate on the whole training set, then score it once on the test
    set. The dummy baseline is scored on the same test set for comparison. For
    classification the probability threshold is also chosen on the training set: the one with
    the lowest expected business cost (config costs)."""
    features, target = feature_columns(config), targets(config)[task]
    scoring = "neg_mean_absolute_error" if task == "regression" else "roc_auc"
    cv = ev.group_folds(task, config["split"]["cv_folds"], config["split"]["random_state"])
    pool = candidates(task, config)
    costs = config["costs"] if task == "classification" else None
    baseline_name = next(iter(pool))
    out = {}
    for label, model_name in [("baseline", baseline_name), ("model", name)]:
        pipe, grid = pool[model_name]
        fitted = ev.tune(pipe, grid, train[features], train[target], train[group], cv, scoring)
        threshold = (ev.choose_threshold(fitted, train[features], train[target], train[group], cv, costs)
                     if task == "classification" else 0.5)
        out[label] = {"name": model_name, "fitted": fitted, "threshold": threshold,
                      "params": getattr(fitted, "best_params_", {}),
                      "test": ev.score(fitted, test[features], test[target], task, threshold, costs)}
    return out


def final_model(task: str, name: str, params: dict, data: pd.DataFrame, config: dict):
    """Refit the chosen pipeline, with its tuned hyperparameters, on all the data.

    The test score was already measured on held-out countries; using every row for the
    model that is saved gives it the most information for future predictions.
    """
    pipe, _ = candidates(task, config)[name]
    return pipe.set_params(**params).fit(data[feature_columns(config)], data[targets(config)[task]])


def train_engine(data: pd.DataFrame, config: dict) -> dict:
    """Run the whole workflow for both tasks on a dataset from load_dataset (or
    synthetic_dataset) and return everything needed to report and save it: data, split,
    cross-validation, test scores and the final pipelines."""
    train, test = split_by_country(data, config)
    engine = {"data": data, "train": train, "test": test}
    for task in TASKS:
        selection = select_model(task, train, config)
        tested = fit_and_test(task, selection["best"], train, test, config)
        engine[task] = finish_task(task, selection, tested, data, config)
    return engine


def finish_task(task: str, selection: dict, tested: dict, data: pd.DataFrame, config: dict) -> dict:
    """Combine one task's model selection and test results with its final pipeline, refitted
    on all the data with the tuned hyperparameters."""
    final = final_model(task, selection["best"], tested["model"]["params"], data, config)
    return {**selection, **tested, "final": final}


def data_fingerprint(data: pd.DataFrame, columns: list[str]) -> str:
    """SHA-256 of the training rows (the given columns, in order): the same data always
    gives the same fingerprint, so a saved model can be traced to the exact data behind it."""
    hashed = pd.util.hash_pandas_object(data[columns].reset_index(drop=True), index=True)
    return hashlib.sha256(hashed.to_numpy().tobytes()).hexdigest()


def git_state(root: Path = ROOT) -> dict:
    """The code version: current git commit and whether there were uncommitted changes
    (None if git isn't available)."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                                text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                    cwd=root, capture_output=True, text=True, check=True).stdout.strip())
        return {"commit": commit, "uncommitted_changes": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "uncommitted_changes": None}


def provenance(data: pd.DataFrame, config: dict, source: str) -> dict:
    """Where a saved model came from: data (source, size, years, fingerprint), code (git
    commit), settings (a full copy of the config, random_state) and environment."""
    columns = ["country", "year", *feature_columns(config), "log10_imports", "major_buyer"]
    return {
        "data": {"source": source, "rows": len(data), "countries": int(data["country"].nunique()),
                 "years": sorted(int(y) for y in data["year"].unique()),
                 "sha256": data_fingerprint(data, columns)},
        "code": git_state(),
        "config": config,
        "random_state": config["split"]["random_state"],
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "scikit-learn": sklearn.__version__, "pandas": pd.__version__,
                        "numpy": np.__version__, "joblib": joblib.__version__},
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def evaluation_artifacts(engine: dict, config: dict) -> dict:
    """The evidence behind the engine's scores, computed once at training time and saved with it,
    so a reviewer (or the dashboard) can inspect it without retraining. Tables:

    - cv: both tasks' nested cross-validation summaries (mean and SD of each metric, per model)
    - test: test-set metrics of the chosen model and of the dummy baseline
    - intervals: 95% bootstrap intervals for the test metrics (whole countries resampled)
    - test_predictions: each test country-year's predicted log10 imports and P(major buyer)
    - train_scores: out-of-fold P(major buyer) for the training countries (used to set the threshold)
    """
    train, test = engine["train"], engine["test"]
    features, seed = feature_columns(config), config["split"]["random_state"]
    reg, clf = engine["regression"], engine["classification"]
    threshold = clf["model"]["threshold"]
    pred = reg["model"]["fitted"].predict(test[features])
    p_test = clf["model"]["fitted"].predict_proba(test[features])[:, 1]
    cv = ev.group_folds("classification", config["split"]["cv_folds"], seed)
    oof = ev.out_of_fold_scores(clf["model"]["fitted"], train[features], train["major_buyer"], train["country"], cv)
    tests = [{"task": task, "role": role, "model": t[role]["name"], **t[role]["test"]}
             for task, t in [("regression", reg), ("classification", clf)] for role in ("baseline", "model")]
    intervals = [{"task": "regression", **ev.bootstrap_ci(test["log10_imports"], pred, test["country"],
                                                          "regression", m, random_state=seed)}
                 for m in ("MAE", "R2")]
    intervals += [{"task": "classification",
                   **ev.bootstrap_ci(test["major_buyer"], p_test, test["country"], "classification", m,
                                     random_state=seed, threshold=threshold, costs=config["costs"])}
                  for m in ("AUC", "cost", "recall", "precision")]
    return {
        "cv": pd.concat({"regression": reg["summary"], "classification": clf["summary"]},
                        names=["task"]).reset_index(level=0).reset_index(drop=True),
        "test": pd.DataFrame(tests),
        "intervals": pd.DataFrame(intervals),
        "test_predictions": pd.DataFrame({
            "country": test["country"], "year": test["year"], "actual_log10": test["log10_imports"],
            "predicted_log10": pred, "major_buyer": test["major_buyer"], "p_major_buyer": p_test}),
        "train_scores": pd.DataFrame({"country": train["country"], "major_buyer": train["major_buyer"],
                                      "p_major_buyer": oof}),
        "split": {"rows": len(engine["data"]), "train_rows": len(train), "test_rows": len(test),
                  "train_countries": int(train["country"].nunique()),
                  "test_countries": int(test["country"].nunique())},
    }


def model_bundle(engine: dict, config: dict, source: str) -> dict:
    """What gets saved: both final pipelines (preprocessing included) plus what's needed to
    use and audit them: problem types, features, target, threshold, business costs, scores,
    the evaluation evidence (evaluation_artifacts) and provenance."""
    record = provenance(engine["data"], config, source)
    return {
        "problem_types": PROBLEM_TYPES,
        "regressor": engine["regression"]["final"],
        "classifier": engine["classification"]["final"],
        "features": feature_columns(config),
        "feature_lag_years": config["data"].get("feature_lag_years", 0),
        "target": config["target"],
        "models": {task: engine[task]["best"] for task in TASKS},
        "params": {task: engine[task]["model"]["params"] for task in TASKS},
        "threshold": engine["classification"]["model"]["threshold"],
        "costs": config["costs"],
        "actions": config["actions"],
        "cv": {task: engine[task]["summary"].to_dict("records") for task in TASKS},
        "test": {task: {"model": engine[task]["model"]["test"],
                        "baseline": engine[task]["baseline"]["test"]} for task in TASKS},
        "evaluation": evaluation_artifacts(engine, config),
        "trained_on": {"rows": len(engine["data"]), "countries": int(engine["data"]["country"].nunique()),
                       "years": config["data"]["years"], "database": source},
        "versions": {k: v for k, v in record["environment"].items() if k not in ("python", "platform")},
        "provenance": record,
        "created_utc": record["created_utc"],
    }


def save_bundle(bundle: dict, path: Path) -> Path:
    """Save the bundle with joblib (models/ is git-ignored: the models encode restricted data)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)
    return path


def main(argv=None) -> int:
    """Command line: train, evaluate and save the engine."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    con, db_path = ex.open_database()
    engine = train_engine(load_dataset(con, config), config)
    for task in TASKS:
        print(f"\n{task.upper()}: cross-validation by country (training set)")
        print(engine[task]["summary"].round(3).to_string(index=False))
        t = engine[task]
        print(f"Chosen: {t['best']} {t['model']['params']}")
        print(f"Test set: model {pd.Series(t['model']['test']).round(3).to_dict()}")
        print(f"          baseline {pd.Series(t['baseline']['test']).round(3).to_dict()}")
    path = save_bundle(model_bundle(engine, config, db_path.name), ROOT / config["output"]["model_path"])
    print(f"\nSaved {path.relative_to(ROOT)} (trained on {db_path.name})")
    return 0


if __name__ == "__main__":
    # Run through the importable module, so the saved pipelines refer to
    # src.modeling.train.safe_log10. Under `python -m` this file is __main__, and a pipeline
    # pickled from here would point at __main__.safe_log10, which can't be loaded later.
    from src.modeling.train import main as run
    raise SystemExit(run())
