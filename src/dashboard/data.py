"""The dashboard's data-access layer: one results snapshot, built from two sources.

1. The Assignment 4 database (read through src.analysis.exploratory, the Assignment 5 functions):
   database_tables() returns concentration, prices, wind, the hypothesis tests and the models.
2. The Assignment 6 result artifact, the saved engine bundle (models/*.joblib):
   engine_tables() reads its evaluation evidence, then uses its pipelines for the actions and the
   forecast. Nothing is retrained.

build_snapshot() combines them into a folder of small CSV and JSON files (save_snapshot). The app
only ever reads such a folder (load_snapshot), which keeps it fast and makes every number it shows
reproducible: rebuild the snapshot from the same inputs and compare_snapshots() finds no
differences.

- data/published/                  snapshot of the real results (committed)
- data/processed/published_sample/ snapshot rebuilt from the synthetic data (git-ignored)
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# The analysis and modeling packages (statsmodels, scikit-learn, Pandera) are imported inside the
# build functions only: the dashboard just loads snapshots, and starts much faster without them.

ROOT = Path(__file__).resolve().parents[2]
PUBLISHED = ROOT / "data" / "published"
SAMPLE_SNAPSHOT = ROOT / "data" / "processed" / "published_sample"
ENGINE = ROOT / "models" / "rare_earth_engine.joblib"                  # Assignment 6 artifact (git-ignored)
SAMPLE_ENGINE = ROOT / "models" / "rare_earth_engine_synthetic.joblib"  # trained on synthetic data
TABLES = ("actions", "buyers", "concentration", "country_year", "coverage", "engine_cv", "engine_intervals",
          "engine_test", "forecast", "hypotheses", "models", "price_changes", "quality_checks",
          "regression_check", "robustness", "row_counts", "test_predictions", "trade_yearly",
          "train_scores", "wind_trend")


class SnapshotError(FileNotFoundError):
    """A snapshot folder is missing, incomplete or unreadable; the message says how to rebuild it."""
START, END, FORECAST = 2023, 2024, 2025
SIGNIFICANT = 10  # digits kept for floats, so rebuilt snapshots compare exactly
VOLATILE = {"created_utc", "git_commit", "uncommitted_changes", "versions"}  # ignored by compare


def relative_to_root(path: Path) -> str:
    """A path as shown to people: relative to the project root when it is inside it."""
    path = Path(path).resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


# --- Building ---------------------------------------------------------------------------------

def database_tables(con) -> tuple[dict, dict]:
    """From the Assignment 4 database: data quality, concentration, prices, wind, the hypothesis
    tests and the models (Assignment 5 functions).

    Returns (tables, summary): tables are DataFrames, summary holds headline numbers.
    """
    from src.analysis import exploratory as ex
    from src.analysis import statistical as st
    panel = ex.load_country_panel(con)
    sample = ex.analysis_sample(panel)
    trade = ex.load_trade(con)
    wind = ex.load_wind(con)
    exports = trade[trade["trade_flow"] == "Export"]
    growth = ex.growth_vs_wind(panel, END)
    drivers = [st.WIND, st.SIZE]

    resid = st.size_adjusted_residuals(sample, st.WIND, st.IMPORTS, [st.SIZE])
    country_year = sample[["country", "partner", "year", st.IMPORTS, st.WIND, "wind_generation_twh",
                           st.SIZE, "wind_share_pct", "size_group"]].assign(
        size_group=sample["size_group"].astype(str),
        wind_size_adjusted=resid["x_resid"].to_numpy(), imports_size_adjusted=resid["y_resid"].to_numpy())

    buyers = ex.buyers_by_year(trade)
    concentration = pd.DataFrame([{"year": y, **ex.concentration(ex.buyer_volumes(trade, y))}
                                  for y in sorted(exports["year"].unique())])

    tests = st.main_hypothesis_tests(sample, growth, exports, ex.SIZE_GROUPS, START, END)
    regression = st.regression_hypothesis_checks(sample, panel, exports, START, END).assign(
        main_test_result=tests["result"].to_numpy())
    wind_only = st.fit_log_ols(sample, st.IMPORTS, [st.WIND])
    with_size = st.fit_log_ols(sample, st.IMPORTS, drivers)
    models = pd.concat({"A: wind only": st.tidy_coefficients(wind_only),
                        "B: wind + size": st.tidy_coefficients(with_size)}, names=["model"]).reset_index()
    both_years = st.fit_log_ols(ex.balanced_panel(sample), st.IMPORTS, drivers)
    ppml = st.fit_ppml(ex.analysis_sample(panel, include_non_buyers=True), st.IMPORTS, drivers)
    robustness = st.compare_models({"B: all buyers (log-log OLS)": with_size,
                                    "B: buyers in both years only": both_years,
                                    "PPML: missing years as 0 kg": ppml},
                                   [f"log_{st.WIND}", f"log_{st.SIZE}"])
    trend, info = ex.wind_trend(wind, focus="China")
    checks = ex.check_database(con)
    decomposition = ex.price_mix_decomposition(trade, START, END)
    yearly = ex.yearly_trade(trade)
    change = ex.period_change(yearly, "Export", START, END)

    tables = {
        "country_year": country_year,
        "trade_yearly": yearly,
        "buyers": buyers,
        "concentration": concentration,
        "price_changes": ex.buyer_price_changes(trade, START, END).rename_axis("partner").reset_index(),
        "wind_trend": trend,
        "hypotheses": tests,
        "regression_check": regression,
        "models": models,
        "robustness": robustness,
        "row_counts": ex.table_row_counts(con).rename_axis("table").reset_index(name="rows"),
        "quality_checks": checks,
        "coverage": ex.coverage_by_year(con).reset_index(),
    }
    lw, ls = f"log_{st.WIND}", f"log_{st.SIZE}"
    summary = {
        "concentration_latest": concentration.iloc[-1].to_dict(),
        "price_decomposition": decomposition,
        "export_change_pct": change.to_dict(),
        "wind_trend": {"labels": info["labels"], "series": info["series"], "countries": info["countries"],
                       "first_year": int(trend["year"].iloc[0]), "last_year": int(trend["year"].iloc[-1])},
        "model_a": {"wind": float(wind_only.params[lw]), "r2": float(wind_only.rsquared),
                    "n": int(wind_only.nobs)},
        "model_b": {"wind": float(with_size.params[lw]), "size": float(with_size.params[ls]),
                    "wind_ci": [float(v) for v in with_size.conf_int().loc[lw]],
                    "r2": float(with_size.rsquared), "n": int(with_size.nobs)},
        "sample": {"rows": len(sample), "countries": int(sample["country"].nunique()),
                   "years": sorted(int(y) for y in sample["year"].unique())},
        "size_groups": list(ex.SIZE_GROUPS),
        "checks_passed": int(checks["passed"].sum()), "checks_total": len(checks),
    }
    return tables, summary


def train_engine_artifact(con, real: bool, path: Path, source: str = "", config: dict | None = None) -> Path:
    """Train the Assignment 6 engine and save its bundle (pipelines, evaluation, provenance).

    real=False trains on train.synthetic_dataset, as notebook 03 does, because the committed
    sample database is too small to model.
    """
    from src.modeling import train as tr
    config = config or tr.load_config()
    data = tr.load_dataset(con, config) if real else tr.synthetic_dataset(config)
    engine = tr.train_engine(data, config)
    return tr.save_bundle(tr.model_bundle(engine, config, source if real else "synthetic"), path)


def load_engine_artifact(path: Path) -> dict:
    """Load a saved engine bundle and check it carries the evaluation evidence the dashboard reads."""
    from src.modeling import predict as pr
    bundle = pr.load_engine(path)
    if "evaluation" not in bundle:
        raise SnapshotError(f"{path} was saved before evaluation evidence was stored with the engine. "
                            "Retrain it: uv run python -m src.modeling.train")
    return bundle


def engine_tables(bundle: dict, features_now: pd.DataFrame, features_next: pd.DataFrame) -> tuple[dict, dict]:
    """From the Assignment 6 artifact: cross-validation, test scores with intervals, predictions
    and the threshold explorer's inputs (all saved in the bundle at training time), plus the
    recommended actions and the forecast made with the saved pipelines.

    features_now: rows to compare with actual imports (END); features_next: rows to forecast.
    """
    from src.modeling import predict as pr
    evaluation = bundle["evaluation"]
    actions = pr.recommend(pr.expected_vs_actual(bundle, features_now), bundle)
    forecast = pr.expected_vs_actual(bundle, features_next)
    keep = ["country", "year", "imports_from_china_kg", "predicted_kg", "ratio_actual_to_expected",
            "p_major_buyer", "major_buyer_call"]
    tables = {
        "engine_cv": evaluation["cv"],
        "engine_test": evaluation["test"],
        "engine_intervals": evaluation["intervals"],
        "test_predictions": evaluation["test_predictions"],
        "train_scores": evaluation["train_scores"],
        "actions": actions[keep + ["action", "reason"]],
        "forecast": forecast[[c for c in keep if c not in ("imports_from_china_kg", "ratio_actual_to_expected")]],
    }
    record = bundle["provenance"]
    summary = {
        "models": bundle["models"], "params": bundle["params"], "threshold": bundle["threshold"],
        "costs": bundle["costs"], "actions_rules": bundle["actions"], "feature_lag_years": bundle["feature_lag_years"],
        "features": bundle["features"], "major_buyer_kg": bundle["target"]["major_buyer_kg"],
        **evaluation["split"], "years": {"actions": END, "forecast": FORECAST},
        "artifact": {"data_sha256": record["data"]["sha256"], "git_commit": record["code"]["commit"],
                     "created_utc": record["created_utc"], "random_state": record["random_state"]},
    }
    return tables, summary


def build_snapshot(con, bundle: dict, real: bool = True, source: str = "") -> dict:
    """Every table and headline number the dashboard shows: database_tables() from the Assignment 4
    database plus engine_tables() from the Assignment 6 artifact.

    real=False: the engine was trained on synthetic data, so its actions and forecast use the
    synthetic rows (train.synthetic_dataset) rather than the sample database.
    """
    import sklearn

    from src.modeling import train as tr
    config = tr.load_config()
    tables, summary = database_tables(con)
    lag = bundle.get("feature_lag_years", 0)
    if real:
        now, nxt = tr.load_features(con, [END], lag), tr.load_features(con, [FORECAST], lag)
    else:
        synthetic = tr.synthetic_dataset(config)
        now = synthetic[synthetic["year"] == END]
        nxt = now.assign(year=FORECAST, imports_from_china_kg=np.nan)
    engine, engine_summary = engine_tables(bundle, now, nxt)
    tables.update(engine)
    sample = tables["country_year"]
    code = tr.git_state()
    meta = {"source": "real" if real else "synthetic", "database": source,
            "data_sha256": tr.data_fingerprint(sample, list(sample.columns)),
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "versions": {"scikit-learn": sklearn.__version__, "pandas": pd.__version__},
            "git_commit": code["commit"], "uncommitted_changes": code["uncommitted_changes"]}
    return {"tables": tables, "summary": {"analysis": summary, "engine": engine_summary}, "meta": meta}


# --- Saving, loading, comparing -----------------------------------------------------------------

def _round(value):
    """Round floats to SIGNIFICANT digits (recursively), so files are stable across runs."""
    if isinstance(value, dict):
        return {str(k): _round(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(value) else float(f"{float(value):.{SIGNIFICANT}g}")
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def save_snapshot(snapshot: dict, out_dir: Path) -> Path:
    """Write each table as CSV and the summary and metadata as JSON."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, table in snapshot["tables"].items():
        table.to_csv(out_dir / f"{name}.csv", index=False, float_format=f"%.{SIGNIFICANT}g",
                     lineterminator="\n")
    for name in ("summary", "meta"):
        (out_dir / f"{name}.json").write_text(json.dumps(_round(snapshot[name]), indent=2, sort_keys=True)
                                              + "\n", encoding="utf-8")
    return out_dir


def load_snapshot(path: Path) -> dict:
    """Read a snapshot folder back: {"tables": {name: DataFrame}, "summary": ..., "meta": ...}.

    Raises SnapshotError, with the command that fixes it, if the folder is missing, a table or
    JSON file is missing, or a file can't be read.
    """
    path = Path(path)
    fix = "Rebuild it: uv run python scripts/deploy.py build --sample (or build, with the real data)."
    if not (path / "meta.json").exists():
        raise SnapshotError(f"No dashboard snapshot in {path}. {fix}")
    missing = [t for t in TABLES if not (path / f"{t}.csv").exists()]
    missing += [f for f in ("summary.json",) if not (path / f).exists()]
    if missing:
        raise SnapshotError(f"The snapshot in {path} is incomplete (missing {', '.join(missing)}). {fix}")
    try:
        tables = {t: pd.read_csv(path / f"{t}.csv") for t in TABLES}
        summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    except (ValueError, OSError) as err:  # pandas parser errors and JSON errors are ValueErrors
        raise SnapshotError(f"The snapshot in {path} can't be read ({err}). {fix}") from err
    return {"tables": tables, "summary": summary, "meta": meta}


def compare_snapshots(a: Path, b: Path, rtol: float = 1e-6) -> list[str]:
    """Differences between two snapshot folders (empty list = the same results).

    Numbers are compared with a relative tolerance, everything else exactly; the build time,
    git commit and library versions are ignored.
    """
    sa, sb = load_snapshot(a), load_snapshot(b)
    problems = []
    for name in sorted(set(sa["tables"]) | set(sb["tables"])):
        if name not in sa["tables"] or name not in sb["tables"]:
            problems.append(f"{name}: only in one snapshot")
            continue
        ta, tb = sa["tables"][name], sb["tables"][name]
        if list(ta.columns) != list(tb.columns) or len(ta) != len(tb):
            problems.append(f"{name}: different columns or row count")
            continue
        for col in ta.columns:
            x, y = ta[col], tb[col]
            if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
                same = np.isclose(x.astype(float), y.astype(float), rtol=rtol, equal_nan=True)
            else:
                same = (x.astype(str) == y.astype(str)).to_numpy()
            if not same.all():
                problems.append(f"{name}.{col}: {int((~same).sum())} value(s) differ")
    for part in ("summary", "meta"):
        flat_a, flat_b = _flatten(sa[part]), _flatten(sb[part])
        for key in sorted(set(flat_a) | set(flat_b)):
            if key.split(".")[0] in VOLATILE or key.split(".")[-1] in VOLATILE:
                continue
            va, vb = flat_a.get(key), flat_b.get(key)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and not isinstance(va, bool):
                if not math.isclose(va, vb, rel_tol=rtol, abs_tol=1e-12):
                    problems.append(f"{part}.{key}: {va} vs {vb}")
            elif va != vb:
                problems.append(f"{part}.{key}: {va!r} vs {vb!r}")
    return problems


def _flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out
