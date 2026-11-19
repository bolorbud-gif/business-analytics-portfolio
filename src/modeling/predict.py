"""Use the saved analytics engine: load it, check it, predict.

Run from the project root, after `uv run python -m src.modeling.train`:
    uv run python -m src.modeling.predict --year 2024 --top 10

For every country with power data in that year, prints its expected imports from China, its
probability of being a major buyer, how its actual imports compare with the expectation, and
a recommended action. Countries with no recorded imports get an estimate too.

Who acts on it: the market-development team of a rare-earth supplier deciding where to spend
sales and sourcing effort (recommend() explains the rules).
"""

import argparse
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from src.analysis import exploratory as ex
from src.modeling import train as tr

REQUIRED_KEYS = {"regressor", "classifier", "features", "target", "threshold", "versions"}
ACTIONS = {
    "Approach": "No recorded imports, but a major-buyer profile: a possible new market. Investigate and approach.",
    "Grow": "A major-buyer profile, but buys under 10 t a year or under a tenth of what its power "
            "sector suggests: under-served. Prioritise outreach.",
    "Verify": "Buys far more than its power sector explains (industry or re-exports): plan on its purchase "
              "history, not this model, and check end use.",
    "Keep": "An established major buyer, within a factor of 10 of what its power sector suggests: "
            "maintain the relationship.",
    "Low priority": "A small market, as its power sector suggests.",
}


def load_engine(path=None) -> dict:
    """Load a saved engine bundle and check it before use.

    Raises a clear error if the file is missing or isn't an engine bundle, and warns if it
    was saved with a different scikit-learn version (pickled models can change behaviour
    between versions).
    """
    path = Path(path) if path else tr.ROOT / tr.load_config()["output"]["model_path"]
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Train it first: uv run python -m src.modeling.train")
    bundle = joblib.load(path)
    missing = REQUIRED_KEYS - set(bundle) if isinstance(bundle, dict) else REQUIRED_KEYS
    if missing:
        raise ValueError(f"{path} is not an engine bundle (missing {sorted(missing)})")
    saved = bundle["versions"]["scikit-learn"]
    if saved != sklearn.__version__:
        warnings.warn(f"Engine saved with scikit-learn {saved}, running {sklearn.__version__}; "
                      "retrain if predictions look wrong.")
    return bundle


def predict(bundle: dict, features: pd.DataFrame) -> pd.DataFrame:
    """Predictions for each row of `features` (which needs every column in bundle["features"];
    missing values are allowed and filled by the pipeline).

    Returns the expected imports in kg (and log10 kg), the probability of being a major
    buyer, and the yes/no call at the engine's threshold.
    """
    missing = [c for c in bundle["features"] if c not in features]
    if missing:
        raise ValueError(f"Missing feature columns: {missing}")
    X = features[bundle["features"]]
    log10_kg = bundle["regressor"].predict(X)
    p_major = bundle["classifier"].predict_proba(X)[:, 1]
    return pd.DataFrame({"predicted_log10_kg": log10_kg, "predicted_kg": 10 ** log10_kg,
                         "p_major_buyer": p_major,
                         "major_buyer_call": p_major >= bundle["threshold"]}, index=features.index)


def expected_vs_actual(bundle: dict, features: pd.DataFrame) -> pd.DataFrame:
    """Expected and actual imports from China for each row of `features` (for example
    train.load_features(con, [2025], bundle["feature_lag_years"]): every country with power
    data, paired the way the engine was trained).

    ratio = actual / expected; above 1 the country buys more than its power sector suggests.
    Countries with no recorded imports have no ratio, but still get an expected value.
    """
    out = pd.concat([features[["country", "year", "imports_from_china_kg"]],
                     predict(bundle, features)], axis=1)
    out["ratio_actual_to_expected"] = out["imports_from_china_kg"] / out["predicted_kg"]
    return out.sort_values("predicted_kg", ascending=False, ignore_index=True)


def recommend(table: pd.DataFrame, bundle: dict) -> pd.DataFrame:
    """Add a recommended action (and the reason) to an expected_vs_actual table.

    Rules, in order: no recorded imports -> Approach if the classifier calls it a major
    buyer, else Low priority; actual far above expected (actions.far_above) -> Verify; a
    major-buyer call but buying under target.major_buyer_kg, or far below expected
    (actions.far_below) -> Grow; already a major buyer -> Keep; everything else -> Low priority.
    """
    actual, ratio, call = (table["imports_from_china_kg"], table["ratio_actual_to_expected"],
                           table["major_buyer_call"].astype(bool))
    major_now = actual >= bundle["target"]["major_buyer_kg"]
    rules = bundle["actions"]
    conditions = [actual.isna() & call, actual.isna(), ratio >= rules["far_above"],
                  call & (~major_now | (ratio <= rules["far_below"])), major_now]
    action = np.select(conditions, ["Approach", "Low priority", "Verify", "Grow", "Keep"], "Low priority")
    return table.assign(action=action, reason=[ACTIONS[a] for a in action])


def main(argv=None) -> int:
    """Command line: expected vs actual imports for one year, with recommended actions."""
    parser = argparse.ArgumentParser(description="Predict imports of Chinese rare-earth compounds")
    parser.add_argument("--year", type=int, default=2024,
                        help="year to predict imports for (a year with no trade data yet, such as "
                             "2025, gives a forecast without actions)")
    parser.add_argument("--top", type=int, default=10, help="rows to print in each table")
    parser.add_argument("--model", type=Path, default=None)
    args = parser.parse_args(argv)
    bundle = load_engine(args.model)
    con, db_path = ex.open_database()
    lag = bundle.get("feature_lag_years", 0)
    table = expected_vs_actual(bundle, tr.load_features(con, [args.year], lag))
    with pd.option_context("display.float_format", lambda v: f"{v:,.2f}", "display.width", 160):
        print(f"Engine: {bundle['models']} trained {bundle['created_utc']} on "
              f"{bundle['trained_on']['database']}; data: {db_path.name}")
        print(f"Features: power data from {args.year - lag} (lag {lag} year) for imports in {args.year}")
        if table["imports_from_china_kg"].isna().all():
            # No trade records for this year at all: a missing value means "not reported yet",
            # not "bought nothing", so the action rules (which compare with actual imports) don't apply.
            print(f"\nNo trade data for {args.year} yet: forecast only, no actions.")
            print(table[["country", "predicted_kg", "p_major_buyer", "major_buyer_call"]]
                  .head(args.top).to_string(index=False))
            return 0 if np.isfinite(table["predicted_kg"]).all() else 1
    table = recommend(table, bundle)
    cols = ["country", "imports_from_china_kg", "predicted_kg", "ratio_actual_to_expected",
            "p_major_buyer", "action"]
    with pd.option_context("display.float_format", lambda v: f"{v:,.2f}", "display.width", 160):
        print(f"\nLargest expected buyers, {args.year}:")
        print(table[cols].head(args.top).to_string(index=False))
        buyers = table.dropna(subset=["ratio_actual_to_expected"])
        print(f"\nBuying most above expectation (actual / expected):")
        print(buyers.nlargest(args.top, "ratio_actual_to_expected")[cols].to_string(index=False))
        none = table[table["imports_from_china_kg"].isna()]
        print(f"\nNo recorded imports in {args.year}: estimated potential demand")
        print(none[cols[:3] + ["p_major_buyer", "action"]].head(args.top).to_string(index=False))
        print("\nRecommended actions:")
        for action, group in table.groupby("action", sort=False):
            print(f"  {action} ({len(group)}): {ACTIONS[action]}")
            print(f"    {', '.join(group['country'].head(8))}")
    return 0 if np.isfinite(table["predicted_kg"]).all() else 1


if __name__ == "__main__":
    raise SystemExit(main())
