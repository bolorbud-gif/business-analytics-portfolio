"""Evaluation for the analytics engine: metrics, cross-validation and leakage checks.

Every comparison includes the dummy baseline: a model is only useful if it beats a rule that
ignores the features. Cross-validation always splits by country (GroupKFold), because the same
country appears in 2023 and 2024 and a random split would let the model memorize it.
"""

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (accuracy_score, f1_score, mean_absolute_error, mean_squared_error,
                             precision_score, r2_score, recall_score, roc_auc_score, roc_curve)
from sklearn.model_selection import (GridSearchCV, GroupKFold, KFold, StratifiedGroupKFold,
                                     cross_val_predict)

THRESHOLDS = np.round(np.arange(0.05, 0.96, 0.05), 2)


# --- Metrics ----------------------------------------------------------------------------------

def regression_metrics(y_true, y_pred) -> dict:
    """MAE, RMSE and R-squared of predictions on the log10 scale.

    MAE is the typical error, RMSE punishes large misses more, and R-squared is the share
    of the variation explained (0 = no better than predicting the mean). Because the target
    is log10(kg), error_factor = 10**MAE reads as "typically off by this factor".
    """
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    mae = float(mean_absolute_error(y_true, y_pred))
    return {"MAE": mae, "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "R2": float(r2_score(y_true, y_pred)), "error_factor": float(10 ** mae)}


def expected_cost(y_true, y_score, threshold: float, costs: dict) -> float:
    """Average business cost per country of the calls made at `threshold`.

    costs: {"false_negative": cost of a missed major buyer, "false_positive": cost of
    flagging a smaller buyer}, in any common unit (only their ratio matters for decisions).
    """
    y_true = np.asarray(y_true).astype(int)
    flagged = np.asarray(y_score, dtype=float) >= threshold
    fn = int(((y_true == 1) & ~flagged).sum())
    fp = int(((y_true == 0) & flagged).sum())
    return float((costs["false_negative"] * fn + costs["false_positive"] * fp) / len(y_true))


def classification_metrics(y_true, y_score, threshold: float = 0.5, costs: dict | None = None) -> dict:
    """Precision, recall, F1, accuracy and ROC AUC for predicted probabilities, plus the
    expected business cost per country when `costs` are given.

    A country is predicted positive when its probability is at least `threshold`.
    Precision: of the countries flagged, the share that really are positive. Recall: of the
    real positives, the share flagged. F1 balances the two. ROC AUC doesn't depend on the
    threshold: the chance that a random positive gets a higher score than a random negative
    (0.5 = guessing, 1 = perfect).
    """
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score, dtype=float)
    y_pred = (y_score >= threshold).astype(int)
    two_classes = len(np.unique(y_true)) == 2
    out = {"AUC": float(roc_auc_score(y_true, y_score)) if two_classes else float("nan"),
           "precision": float(precision_score(y_true, y_pred, zero_division=0)),
           "recall": float(recall_score(y_true, y_pred, zero_division=0)),
           "F1": float(f1_score(y_true, y_pred, zero_division=0)),
           "accuracy": float(accuracy_score(y_true, y_pred)),
           "flagged": int(y_pred.sum()), "positives": int(y_true.sum()), "n": len(y_true)}
    if costs:
        out["cost"] = expected_cost(y_true, y_score, threshold, costs)
    return out


def confusion_table(y_true, y_score, threshold: float = 0.5,
                    labels: tuple = ("Smaller buyer", "Major buyer")) -> pd.DataFrame:
    """Counts of right and wrong calls at a threshold: rows are the truth, columns the call."""
    y_true = np.asarray(y_true).astype(int)
    y_pred = (np.asarray(y_score) >= threshold).astype(int)
    counts = [[int(((y_true == t) & (y_pred == p)).sum()) for p in (0, 1)] for t in (0, 1)]
    return pd.DataFrame(counts, index=[f"Actually: {lab}" for lab in labels],
                        columns=[f"Called: {lab}" for lab in labels])

def threshold_table(y_true, y_score, thresholds=(0.3, 0.4, 0.5, 0.6, 0.7),
                    costs: dict | None = None) -> pd.DataFrame:
    """Precision, recall, F1 (and expected cost, if `costs` are given) at several thresholds.

    Raising the threshold flags fewer countries: precision usually rises and recall falls.
    The right threshold is a business choice (is a missed buyer or a wasted call worse?),
    so it should be chosen on training data, never on the test set.
    """
    rows = [{"threshold": t, **classification_metrics(y_true, y_score, t, costs)} for t in thresholds]
    return pd.DataFrame(rows).drop(columns=["AUC", "positives", "n"])


def roc_points(y_true, y_score) -> dict:
    """False- and true-positive rates for an ROC curve, plus its AUC."""
    fpr, tpr, _ = roc_curve(np.asarray(y_true).astype(int), y_score)
    return {"fpr": fpr, "tpr": tpr, "AUC": float(roc_auc_score(np.asarray(y_true).astype(int), y_score))}


def score(model, X, y, task: str, threshold: float = 0.5, costs: dict | None = None) -> dict:
    """The task's metrics for a fitted model on (X, y); classification uses `threshold` and
    reports the expected cost per country when `costs` are given."""
    if task == "regression":
        return regression_metrics(y, model.predict(X))
    return {**classification_metrics(y, model.predict_proba(X)[:, 1], threshold, costs),
            "threshold": threshold}


def out_of_fold_scores(model, X, y, groups, cv) -> np.ndarray:
    """Probability of the positive class for every training row, each predicted by a copy of
    the model fitted without that row's country (a tuned search's best model is used)."""
    model = getattr(model, "best_estimator_", model)
    return cross_val_predict(clone(model), X, y, groups=groups, cv=cv, method="predict_proba")[:, 1]


def operating_point(y_true, y_score, threshold: float) -> dict:
    """Where a threshold sits on the ROC curve: its false- and true-positive rates."""
    y_true = np.asarray(y_true).astype(int)
    flagged = np.asarray(y_score) >= threshold
    return {"fpr": float(flagged[y_true == 0].mean()), "tpr": float(flagged[y_true == 1].mean())}

def best_threshold(y_true, y_score, costs: dict | None = None) -> float:
    """The threshold (0.05 to 0.95) with the lowest expected cost, or the best F1 if no
    costs are given. On a tie, the one closest to 0.5."""
    if costs:
        values = [-expected_cost(y_true, y_score, t, costs) for t in THRESHOLDS]
    else:
        values = [f1_score(y_true, (np.asarray(y_score) >= t).astype(int), zero_division=0)
                  for t in THRESHOLDS]
    ties = [t for t, v in zip(THRESHOLDS, values) if v == max(values)]
    return float(min(ties, key=lambda t: abs(t - 0.5)))


def choose_threshold(model, X, y, groups, cv, costs: dict | None = None) -> float:
    """The probability threshold with the lowest business cost (or best F1 without costs),
    chosen on training data only.

    Uses out-of-fold probabilities (each training row is predicted by a model that didn't
    see its country). Choosing the threshold on the test set would be leakage.
    """
    return best_threshold(y, out_of_fold_scores(model, X, y, groups, cv), costs)


# --- Cross-validation -------------------------------------------------------------------------

def group_folds(task: str, n_splits: int = 5, random_state: int = 42):
    """Folds that keep each country in one fold. Classification folds are also stratified,
    so every fold has both classes."""
    if task == "classification":
        return StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    return GroupKFold(n_splits=n_splits)


def cv_scores(pipeline, X, y, groups, cv, task: str) -> pd.DataFrame:
    """Fit a fresh copy of the pipeline on each training fold and score it on the held-out
    fold. One row per fold; preprocessing is refitted inside every fold."""
    rows = []
    splits = cv.split(X, y) if isinstance(cv, KFold) else cv.split(X, y, groups)
    for fold, (train, test) in enumerate(splits):
        model = clone(pipeline).fit(X.iloc[train], y.iloc[train])
        rows.append({"fold": fold + 1, **score(model, X.iloc[test], y.iloc[test], task)})
    return pd.DataFrame(rows)


def tune(pipeline, grid: dict, X, y, groups, cv, scoring: str):
    """Grid search over the pipeline's hyperparameters, with folds split by country.

    The preprocessing is part of the pipeline, so it is refitted on each training fold. A
    model with no grid (the baselines) is simply fitted. Returns the fitted search (or model).
    Runs serially: parallel workers trip a joblib clean-up bug on Windows, and the data are small.
    """
    if not grid:
        return clone(pipeline).fit(X, y)
    search = GridSearchCV(clone(pipeline), grid, cv=cv, scoring=scoring)
    return search.fit(X, y, groups=groups)


def nested_cv(pipeline, grid: dict, X, y, groups, task: str, n_splits: int = 5,
              random_state: int = 42, costs: dict | None = None) -> pd.DataFrame:
    """Honest performance of a *tuned* model: tuning runs inside each outer training fold.

    Tuning and scoring on the same folds would overstate performance (the best of many
    tries looks good partly by luck). Here each outer fold is scored by a model whose
    hyperparameters (and, for classification, probability threshold) were chosen without
    seeing that fold. One row per outer fold, with the chosen parameters.
    """
    scoring = "neg_mean_absolute_error" if task == "regression" else "roc_auc"
    outer = group_folds(task, n_splits, random_state)
    rows = []
    for fold, (train, test) in enumerate(outer.split(X, y, groups)):
        inner = group_folds(task, n_splits, random_state + fold + 1)
        fitted = tune(pipeline, grid, X.iloc[train], y.iloc[train], groups.iloc[train], inner, scoring)
        threshold = (choose_threshold(fitted, X.iloc[train], y.iloc[train], groups.iloc[train],
                                      inner, costs) if task == "classification" else 0.5)
        rows.append({"fold": fold + 1,
                     **score(fitted, X.iloc[test], y.iloc[test], task, threshold, costs),
                     "params": getattr(fitted, "best_params_", {})})
    return pd.DataFrame(rows)


def summarize_cv(results: dict, task: str) -> pd.DataFrame:
    """One row per model: the mean and standard deviation of each metric over the folds,
    and whether the model beats the baseline (the first model) on the main metric."""
    metrics = ["MAE", "RMSE", "R2"] if task == "regression" else ["AUC", "precision", "recall", "F1"]
    if task == "classification" and "cost" in next(iter(results.values())):
        metrics.append("cost")
    rows = []
    for name, folds in results.items():
        row = {"model": name}
        for m in metrics:
            row[m] = folds[m].mean()
            row[f"{m}_sd"] = folds[m].std()
        rows.append(row)
    table = pd.DataFrame(rows)
    main = "MAE" if task == "regression" else "AUC"
    baseline = table.loc[0, main]
    better = table[main] < baseline if task == "regression" else table[main] > baseline
    table["beats_baseline"] = better
    table.loc[0, "beats_baseline"] = False
    return table


# --- Leakage checks ---------------------------------------------------------------------------

def classic_leak_vs_pipeline(pipeline, X, y, groups, task: str, n_splits: int = 5) -> pd.DataFrame:
    """Three ways to score the same pipeline, from most to least leaky.

    - "No split": fit and score on the same rows. The model is graded on data it memorised.
    - "Classic leak": fit the preprocessing (imputer, scaler) on every row, then
      cross-validate only the final model, so preprocessing has already seen the held-out folds.
    - "Pipeline": refit the whole pipeline inside each training fold, as it should be.
    """
    cv = group_folds(task, n_splits)
    prep_name, model_name = pipeline.steps[0][0], pipeline.steps[-1][0]
    leaked = clone(pipeline.named_steps[prep_name]).fit_transform(X)
    leaked = pd.DataFrame(leaked, index=X.index)
    in_sample = score(clone(pipeline).fit(X, y), X, y, task)
    classic = cv_scores(clone(pipeline.named_steps[model_name]), leaked, y, groups, cv, task)
    proper = cv_scores(pipeline, X, y, groups, cv, task)
    return pd.DataFrame({"No split: score on the training rows": pd.Series(in_sample),
                         "Classic leak: preprocess all rows, then split": classic.mean(numeric_only=True),
                         "Pipeline: preprocess inside each fold": proper.mean(numeric_only=True)}
                        ).drop(index=["fold", "threshold"], errors="ignore").T


def random_vs_group_cv(pipeline, X, y, groups, task: str = "regression", n_splits: int = 5,
                       random_state: int = 42) -> pd.DataFrame:
    """Group leakage: random folds put the same country in training and test.

    A country's imports barely change between 2023 and 2024, so with random folds the model
    can recognise a country it has already seen. Splitting by country (GroupKFold) measures
    what the engine is for: predicting countries it hasn't seen.
    """
    random_cv = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    rows = {"Random rows (leaky)": cv_scores(pipeline, X, y, groups, random_cv, task),
            "By country (GroupKFold)": cv_scores(pipeline, X, y, groups,
                                                 group_folds(task, n_splits, random_state), task)}
    return pd.DataFrame({k: v.mean(numeric_only=True) for k, v in rows.items()}).drop(index="fold").T


def leakage_screen(df: pd.DataFrame, columns: list[str], target: str, forbidden: list[str],
                   threshold: float = 0.9) -> pd.DataFrame:
    """Flag candidate features that could leak the target.

    A column is flagged if it is on the forbidden list (derived from the target or from the
    same trade records) or if its rank correlation with the target is suspiciously high
    (|rho| >= threshold): almost no honest predictor is that strong.
    """
    rows = []
    for col in columns:
        d = df[[col, target]].dropna()
        rho = float(d[col].corr(d[target], method="spearman")) if len(d) > 2 else float("nan")
        reason = ("derived from the target or its trade records" if col in forbidden
                  else "suspiciously strong correlation" if abs(rho) >= threshold else "")
        rows.append({"column": col, "spearman_rho": rho, "flagged": bool(reason), "reason": reason})
    return pd.DataFrame(rows).sort_values("spearman_rho", key=abs, ascending=False, ignore_index=True)


# --- Checklist checks: feature availability, time-aware split, test uncertainty ---------------

def feature_availability(features: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Is every feature available when the engine is used? One row per feature.

    `features` is the data the engine will predict for (for example every country with power
    data in the latest year). Shows the documented source and timing from the config, the
    share of those rows where the feature is present (missing values are filled by the
    pipeline's median), and whether the feature could leak the target.
    """
    documented = config["features"].get("availability", {})
    rows = []
    for col in config["features"]["size"] + config["features"]["other"]:
        present = float(features[col].notna().mean()) if col in features else 0.0
        rows.append({"feature": col, "known_when": documented.get(col, "NOT DOCUMENTED"),
                     "share_present": present,
                     "from_trade_records": col in config["features"]["forbidden"]})
    return pd.DataFrame(rows)


def split_comparison(datasets: dict, pipeline, features: list[str], target: str, task: str,
                     train_years: list[int], test_years: list[int], n_splits: int = 5,
                     random_state: int = 42, group: str = "country") -> pd.DataFrame:
    """The same pipeline scored two ways on each dataset: cross-validated by country, and
    time-aware (train on earlier years, test on later ones).

    datasets: {label: data}, e.g. same-year and last-year power features. The time-aware
    score says how the engine would do as a forecast; the country score, how it does on
    countries it has never seen.
    """
    rows = []
    for label, data in datasets.items():
        X, y, g = data[features], data[target], data[group]
        by_country = cv_scores(pipeline, X, y, g, group_folds(task, n_splits, random_state), task)
        rows.append({"features": label, "split": "By country (cross-validated)",
                     **by_country.mean(numeric_only=True).drop(["fold", "threshold"], errors="ignore")})
        past, future = data[data["year"].isin(train_years)], data[data["year"].isin(test_years)]
        model = clone(pipeline).fit(past[features], past[target])
        rows.append({"features": label,
                     "split": f"By time: train {'+'.join(map(str, train_years))}, "
                              f"test {'+'.join(map(str, test_years))}",
                     **pd.Series(score(model, future[features], future[target], task)
                                 ).drop(["threshold"], errors="ignore")})
    return pd.DataFrame(rows)


def bootstrap_ci(y_true, y_hat, groups, task: str, metric: str, n_boot: int = 1000,
                 random_state: int = 42, threshold: float = 0.5, costs: dict | None = None) -> dict:
    """95% interval for a test-set metric, resampling whole countries (with replacement).

    A test set of a few dozen rows gives a noisy score; the interval shows how noisy.
    Countries are resampled, not rows, because a country's two years aren't independent.
    """
    y_true, y_hat = np.asarray(y_true), np.asarray(y_hat, dtype=float)
    groups = np.asarray(groups)
    ids = np.unique(groups)
    rows = {g: np.flatnonzero(groups == g) for g in ids}
    rng = np.random.default_rng(random_state)

    def value(idx):
        if task == "regression":
            return regression_metrics(y_true[idx], y_hat[idx])[metric]
        return classification_metrics(y_true[idx], y_hat[idx], threshold, costs)[metric]

    draws = []
    for _ in range(n_boot):
        idx = np.concatenate([rows[g] for g in rng.choice(ids, len(ids), replace=True)])
        v = value(idx)
        if np.isfinite(v):  # AUC is undefined when a resample has only one class
            draws.append(v)
    low, high = np.percentile(draws, [2.5, 97.5])
    return {"metric": metric, "estimate": float(value(np.arange(len(y_true)))),
            "ci_low": float(low), "ci_high": float(high), "n_boot": len(draws)}
