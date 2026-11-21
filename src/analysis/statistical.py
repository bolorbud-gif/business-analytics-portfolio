"""Statistical analysis: correlation, partial correlation, regression, hypothesis tests.

Trade and electricity values are heavily right-skewed (a few large countries), so the
functions default to rank (Spearman) correlation or work on log10 values. Every test
returns an effect size next to its p-value, and the assumption checks (Shapiro-Wilk,
Levene, regression diagnostics) say which test is safe to use.

Regressions: log-log OLS (fit_log_ols), the same in year-on-year changes
(fit_log_change_ols), and Poisson pseudo-maximum likelihood (fit_ppml), which keeps
country-years with no imports.
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats


def strength(r: float) -> str:
    """Plain-language size of a correlation coefficient."""
    a = abs(r)
    size = ("very weak" if a < 0.2 else "weak" if a < 0.4 else "moderate" if a < 0.6
            else "strong" if a < 0.8 else "very strong")
    return f"{size} {'positive' if r > 0 else 'negative'}" if a >= 0.2 else size


def log10_positive(s: pd.Series) -> pd.Series:
    """log10 of the positive values; zero or negative becomes NaN (log is undefined)."""
    return np.log10(s.where(s > 0))


def correlation(df: pd.DataFrame, x: str, y: str, method: str = "spearman") -> dict:
    """Correlation between two columns over rows where both are present."""
    d = df[[x, y]].dropna()
    if method == "spearman":
        r, p = stats.spearmanr(d[x], d[y])
    elif method == "pearson":
        r, p = stats.pearsonr(d[x], d[y])
    else:
        raise ValueError("method must be 'spearman' or 'pearson'")
    return {"x": x, "y": y, "method": method, "n": len(d), "r": float(r), "p": float(p),
            "strength": strength(r)}


def correlation_table(df: pd.DataFrame, pairs: list[tuple[str, str]],
                      method: str = "spearman") -> pd.DataFrame:
    """correlation() for several column pairs, one row each."""
    return pd.DataFrame([correlation(df, x, y, method) for x, y in pairs])


def correlation_matrix(df: pd.DataFrame, columns: list[str], method: str = "spearman",
                       log: bool = False) -> pd.DataFrame:
    """Pairwise correlation matrix of the columns (Spearman by default).

    log=True correlates log10 values (zero or negative become missing). With
    method="pearson" that is the linear association a log-log regression works with.
    """
    d = df[columns].apply(log10_positive) if log else df[columns]
    return d.corr(method=method)


def residualize(df: pd.DataFrame, column: str, controls: list[str]) -> pd.Series:
    """What is left of `column` after a linear fit on the controls (with intercept)."""
    X = np.column_stack([np.ones(len(df))] + [df[c] for c in controls])
    beta, *_ = np.linalg.lstsq(X, df[column], rcond=None)
    return df[column] - X @ beta


def size_adjusted_residuals(df: pd.DataFrame, x: str, y: str, controls: list[str],
                            log: bool = True) -> pd.DataFrame:
    """Residuals of x and y after removing the controls (log10 first if log=True).

    Their correlation is the partial correlation; plotting them shows the relationship
    with the controls held constant. Returns columns x_resid and y_resid.
    """
    d = df[[x, y, *controls]]
    if log:
        d = d.apply(log10_positive)
    d = d.dropna()
    return pd.DataFrame({"x_resid": residualize(d, x, controls),
                         "y_resid": residualize(d, y, controls)})


def partial_correlation(df: pd.DataFrame, x: str, y: str, controls: list[str],
                        log: bool = True, method: str = "pearson") -> dict:
    """Correlation of x and y after removing what the controls explain.

    With log=True all columns are log10-transformed first (rows with values <= 0 are
    dropped). method="spearman" works on ranks instead, so it needs no normality: use it
    as a check when the residuals fail Shapiro-Wilk. The p-value uses n - 2 - (number of
    controls) degrees of freedom.
    """
    if method not in ("pearson", "spearman"):
        raise ValueError("method must be 'pearson' or 'spearman'")
    cols = [x, y, *controls]
    d = df[cols].copy()
    if log:
        d = d.apply(log10_positive)
    d = d.dropna()
    if method == "spearman":
        d = d.rank()
    rx, ry = residualize(d, x, controls), residualize(d, y, controls)
    r = float(np.corrcoef(rx, ry)[0, 1])
    dof = len(d) - 2 - len(controls)
    t = r * np.sqrt(dof / (1 - r ** 2))
    p = float(2 * stats.t.sf(abs(t), dof))
    return {"x": x, "y": y, "controls": ", ".join(controls), "log": log, "method": method,
            "n": len(d), "r": r, "p": p, "strength": strength(r)}


def fold_change(elasticity: float, factor: float = 10.0) -> float:
    """Business reading of an elasticity: y is multiplied by this when x is multiplied by
    `factor`. An elasticity of 0.94 means 10x the wind capacity goes with 8.7x the imports."""
    return float(factor ** elasticity)


def fit_log_ols(df: pd.DataFrame, y: str, xs: list[str], year_effects: bool = True,
                cluster: str | None = "partner"):
    """OLS of log10(y) on log10(xs), with optional year fixed effects.

    Coefficients are elasticities: a 1% higher x goes with a b% higher y. Standard
    errors are clustered by `cluster` because the same country appears in several years.
    """
    keep = [y, *xs, "year"] + ([cluster] if cluster else [])
    d = df[keep].copy()
    for col in [y, *xs]:
        d[f"log_{col}"] = log10_positive(d[col])
    d = d.dropna()
    formula = f"log_{y} ~ " + " + ".join(f"log_{x}" for x in xs)
    if year_effects and d["year"].nunique() > 1:
        formula += " + C(year)"
    model = smf.ols(formula, data=d)
    if cluster:
        groups = pd.factorize(d[cluster])[0]
        return model.fit(cov_type="cluster", cov_kwds={"groups": groups})
    return model.fit()


def tidy_coefficients(result) -> pd.DataFrame:
    """Coefficient table: estimate, standard error, p-value and 95% interval."""
    ci = result.conf_int()
    return pd.DataFrame({
        "coef": result.params, "std_err": result.bse, "p": result.pvalues,
        "ci_low": ci[0], "ci_high": ci[1],
    }).rename_axis("term")


def fit_ppml(df: pd.DataFrame, y: str, xs: list[str], year_effects: bool = True,
             cluster: str | None = "partner"):
    """Poisson pseudo-maximum likelihood (PPML), the standard regression for trade flows.

    y stays in levels, so zero imports are kept instead of dropped (log 0 is undefined),
    and the estimates stay consistent when the spread of the errors differs between
    countries. The drivers enter as natural logs named log_<x>, so each coefficient is an
    elasticity, comparable with fit_log_ols. Standard errors are clustered by `cluster`.
    """
    keep = [y, *xs, "year"] + ([cluster] if cluster else [])
    d = df[keep].copy()
    for col in xs:
        d[f"log_{col}"] = np.log(d[col].where(d[col] > 0))
    d = d.dropna()
    formula = f"{y} ~ " + " + ".join(f"log_{x}" for x in xs)
    if year_effects and d["year"].nunique() > 1:
        formula += " + C(year)"
    model = smf.glm(formula, data=d, family=sm.families.Poisson())
    if cluster:
        return model.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d[cluster])[0]})
    return model.fit()


def log_changes(df: pd.DataFrame, columns: list[str], entity: str, period: str, start,
                end) -> pd.DataFrame:
    """Each entity's change from `start` to `end`, for entities with positive values of
    every column in both periods.

    dlog_<column> is the natural log of end / start; ratio_<column> is end / start itself
    (2.0 = doubled), which reads better on a chart.
    """
    d = pd.DataFrame({f"dlog_{c}": paired_log_ratios(df, entity, period, c, start, end)
                      for c in columns}).dropna()
    for c in columns:
        d[f"ratio_{c}"] = np.exp(d[f"dlog_{c}"])
    return d.rename_axis(entity)


def fit_log_change_ols(df: pd.DataFrame, y: str, xs: list[str], entity: str, period: str,
                       start, end, cov_type: str = "HC1"):
    """OLS in changes: log(y_end / y_start) on log(x_end / x_start), one row per entity.

    Each entity is compared with itself, so anything about it that doesn't change between
    the two periods (its size, location, industry) drops out. The coefficients are
    elasticities of growth: 1% faster growth in x goes with b% faster growth in y. With no
    xs, the intercept is the mean log change of y. Robust (HC1) standard errors.
    """
    d = log_changes(df, [y, *xs], entity, period, start, end)
    formula = f"dlog_{y} ~ " + (" + ".join(f"dlog_{x}" for x in xs) if xs else "1")
    return smf.ols(formula, data=d).fit(cov_type=cov_type)


def within_share(df: pd.DataFrame, column: str, entity: str = "country", log: bool = True) -> float:
    """Share of a variable's variance that is within entities (over time), not between them.

    Country fixed-effects models use only the within part. Near 0 means each entity barely
    changes, so a fixed-effects estimate would rest on almost no information.
    """
    v = log10_positive(df[column]) if log else df[column]
    d = pd.DataFrame({"v": v, "e": df[entity]}).dropna()
    within = d["v"] - d.groupby("e")["v"].transform("mean")
    return float(within.var() / d["v"].var())


def coefficient_evidence(result, term: str, factor: float = 10.0) -> dict:
    """One coefficient of a log-log model, as evidence for a hypothesis.

    Returns the estimate with its 95% interval, test statistic and p-value; its business
    reading as a fold change (factor x the driver goes with fold x the outcome, with the
    interval ends); and the Shapiro-Wilk p-value of the residuals. A low residual p means
    the p-value rests on a broken normality assumption (NaN for models, such as PPML,
    that don't assume normal errors).
    """
    low, high = result.conf_int().loc[term]
    coef = float(result.params[term])
    resid = getattr(result, "resid", None)
    return {"term": term, "n": int(result.nobs), "coef": coef, "ci_low": float(low),
            "ci_high": float(high), "statistic": float(result.tvalues[term]),
            "p": float(result.pvalues[term]), "fold": fold_change(coef, factor),
            "fold_low": fold_change(low, factor), "fold_high": fold_change(high, factor),
            "residual_shapiro_p": float(stats.shapiro(resid).pvalue)
            if resid is not None and len(resid) >= 3 else float("nan")}


def compare_models(models: dict, terms: list[str]) -> pd.DataFrame:
    """The same coefficients across several fitted models, one row per model and term.

    Used for robustness checks: if the estimates barely move when the sample or the
    estimator changes, the conclusion doesn't depend on that choice. fold_10x is the
    business reading of an elasticity: 10x the driver goes with fold_10x times the outcome.
    """
    rows = []
    for name, result in models.items():
        tidy = tidy_coefficients(result)
        for term in terms:
            r = tidy.loc[term]
            rows.append({"model": name, "term": term, "n": int(result.nobs), "coef": r["coef"],
                         "ci_low": r["ci_low"], "ci_high": r["ci_high"], "p": r["p"],
                         "fold_10x": fold_change(r["coef"])})
    return pd.DataFrame(rows)


def growth_summary(growth_pct: pd.Series, extreme: float = 500.0) -> dict:
    """Summary of percentage growth rates. Rates from tiny bases explode, so the median
    and interquartile range are reported instead of the mean."""
    g = growth_pct.dropna()
    return {
        "n": len(g),
        "median_pct": float(g.median()),
        "q1_pct": float(g.quantile(0.25)),
        "q3_pct": float(g.quantile(0.75)),
        "share_growing": float((g > 0).mean()),
        "extreme_count": int((g.abs() > extreme).sum()),
        "mean_pct": float(g.mean()),
    }


def descriptive_table(df: pd.DataFrame, columns: list[str], log_columns: list[str] = (),
                      labels: dict | None = None, alpha: float = 0.05) -> pd.DataFrame:
    """Descriptive statistics of a model's variables (the usual "Table 1").

    One row per column, plus a log10 row for each column in log_columns: n, mean, standard
    deviation, min, quartiles, max, skew and the Shapiro-Wilk p-value. Comparing a raw row
    with its log10 row shows whether the log scale makes a skewed variable close to normal.
    """
    labels = labels or {}
    rows = []
    for col in columns:
        for log in [False] + ([True] if col in log_columns else []):
            v = df[col].dropna()
            v = log10_positive(v).dropna() if log else v
            shape = normality_test(v, alpha=alpha)
            name = labels.get(col, col)
            rows.append({"variable": f"log10 {name}" if log else name, "n": len(v),
                         "mean": v.mean(), "sd": v.std(), "min": v.min(),
                         "p25": v.quantile(0.25), "median": v.median(), "p75": v.quantile(0.75),
                         "max": v.max(), "skew": shape["skew"], "shapiro_p": shape["p"],
                         "normal": shape["normal"]})
    return pd.DataFrame(rows).set_index("variable")


# --- Hypothesis tests and assumption checks ----------------------------------------------

def normality_test(values: pd.Series, log: bool = False, alpha: float = 0.05) -> dict:
    """Shapiro-Wilk test of normality (on log10 values if log=True). Low p = not normal.

    Also returns the skew, which says in which direction the data depart from normal.
    """
    v = values.dropna()
    if log:
        v = log10_positive(v).dropna()
    w, p = stats.shapiro(v)
    return {"test": "Shapiro-Wilk", "scale": "log10" if log else "raw", "n": len(v),
            "statistic": float(w), "p": float(p), "skew": float(stats.skew(v)),
            "normal": bool(p >= alpha)}


def group_assumptions(df: pd.DataFrame, value: str, group: str, order: list | None = None,
                      log: bool = False, alpha: float = 0.05) -> pd.DataFrame:
    """Assumption checks for comparing groups: Shapiro-Wilk in each group, Levene across them.

    Levene is median-centred (the Brown-Forsythe form), which stays reliable when the data
    aren't normal. With log=True both run on log10 values. One row per check:
    check, test, scale, n, statistic, p, ok (p >= alpha: no evidence the assumption fails).
    """
    order = order or sorted(df[group].dropna().unique())
    samples = [df.loc[df[group] == g, value].dropna() for g in order]
    if log:
        samples = [log10_positive(s).dropna() for s in samples]
    scale = "log10" if log else "raw"
    rows = []
    for g, s in zip(order, samples):
        w, p = stats.shapiro(s)
        rows.append((f"Normal within {g}", "Shapiro-Wilk", scale, len(s), w, p))
    stat, p = stats.levene(*samples, center="median")
    rows.append(("Equal variances across groups", "Levene (median-centred)", scale,
                 int(sum(len(s) for s in samples)), stat, p))
    out = pd.DataFrame(rows, columns=["check", "test", "scale", "n", "statistic", "p"])
    out["ok"] = out["p"] >= alpha
    return out


def _epsilon_size(e2: float) -> str:
    """Conventional label for epsilon-squared: small from 0.01, medium 0.08, large 0.26."""
    return ("negligible" if e2 < 0.01 else "small" if e2 < 0.08 else "medium" if e2 < 0.26
            else "large")


def compare_groups(df: pd.DataFrame, value: str, group: str, order: list | None = None) -> dict:
    """Kruskal-Wallis test: do the groups' distributions differ? (no normality assumed)

    The effect size is epsilon-squared, H / (n - 1): the share of the variation in ranks
    explained by the groups (0 to 1).
    """
    order = order or sorted(df[group].dropna().unique())
    samples = [df.loc[df[group] == g, value].dropna() for g in order]
    h, p = stats.kruskal(*samples)
    n = int(sum(len(s) for s in samples))
    e2 = float(h / (n - 1))
    return {"test": "Kruskal-Wallis", "groups": len(order), "n": n,
            "statistic": float(h), "p": float(p), "epsilon_sq": e2, "effect": _epsilon_size(e2),
            "medians": {str(g): float(s.median()) for g, s in zip(order, samples)}}


def log_ratio_to_pct(v: float) -> float:
    """A natural-log ratio as a percent change: log(0.5) -> -50.0."""
    return float((np.exp(v) - 1) * 100)


def paired_log_ratios(df: pd.DataFrame, entity: str, period: str, value: str, start,
                      end) -> pd.Series:
    """log(end / start) of `value` for each entity seen, with a positive value, in both periods."""
    wide = df.pivot_table(index=entity, columns=period, values=value, aggfunc="mean")
    pair = wide[[start, end]].dropna()
    pair = pair[(pair > 0).all(axis=1)]
    return np.log(pair[end] / pair[start]).rename("log_ratio")


def paired_change(df: pd.DataFrame, entity: str, period: str, value: str, start, end,
                  test: str = "wilcoxon") -> dict:
    """Paired test of the change in `value` for entities seen in both periods.

    Works on the log ratio end/start, so a halving and a doubling count equally.
    test="wilcoxon" (signed-rank) assumes the changes are symmetric around their median;
    test="sign" only counts rises and falls, so it assumes nothing about their shape: use
    it when the log ratios are skewed. Both p-values are always returned, plus the paired
    t-test's (t_test_p) for comparison only: it is valid only if the log ratios are normal.

    Effect sizes: the median change in percent with a 95% bootstrap interval (the business
    magnitude), the share of entities whose value fell, and the matched-pairs rank-biserial
    correlation (-1 = all fell, +1 = all rose).
    """
    if test not in ("wilcoxon", "sign"):
        raise ValueError("test must be 'wilcoxon' or 'sign'")
    ratio = paired_log_ratios(df, entity, period, value, start, end)
    w, wilcoxon_p = stats.wilcoxon(ratio)
    moved = ratio[ratio != 0]
    falls = int((moved < 0).sum())
    sign_p = float(stats.binomtest(falls, len(moved)).pvalue)
    ranks = stats.rankdata(moved.abs())
    up, down = ranks[moved.to_numpy() > 0].sum(), ranks[moved.to_numpy() < 0].sum()
    ci = bootstrap_ci(ratio, np.median)
    pct = log_ratio_to_pct
    return {"test": "Wilcoxon signed-rank" if test == "wilcoxon" else "Sign test",
            "n": len(ratio), "statistic": float(w) if test == "wilcoxon" else falls,
            "p": float(wilcoxon_p) if test == "wilcoxon" else sign_p,
            "wilcoxon_p": float(wilcoxon_p), "sign_p": sign_p,
            "t_test_p": float(stats.ttest_1samp(ratio, 0).pvalue),
            "median_change_pct": pct(ratio.median()),
            "ci_low_pct": pct(ci["ci_low"]), "ci_high_pct": pct(ci["ci_high"]),
            "share_falling": float((ratio < 0).mean()),
            "rank_biserial": float((up - down) / (up + down)),
            "skew": float(stats.skew(ratio))}


def split_medians(df: pd.DataFrame, value: str, by: str) -> dict:
    """Business reading of a correlation: the median of `value` where `by` is above its
    median, versus where it is at or below it."""
    d = df[[value, by]].dropna()
    above = d[by] > d[by].median()
    return {"above": float(d.loc[above, value].median()), "below": float(d.loc[~above, value].median()),
            "n_above": int(above.sum()), "n_below": int((~above).sum())}


def top_share(values, k: int = 5) -> float:
    """Share of the total held by the k largest values."""
    v = np.sort(np.asarray(values, dtype=float))[::-1]
    return float(v[:k].sum() / v.sum())


def bootstrap_ci(values, statistic, n_boot: int = 2000, level: float = 0.95, seed: int = 0) -> dict:
    """Percentile bootstrap confidence interval for any statistic of a 1-D sample."""
    v = np.asarray(pd.Series(values).dropna(), dtype=float)
    rng = np.random.default_rng(seed)
    boots = np.array([statistic(rng.choice(v, len(v), replace=True)) for _ in range(n_boot)])
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(boots, [tail, 100 - tail])
    return {"estimate": float(statistic(v)), "ci_low": float(low), "ci_high": float(high),
            "level": level, "n_boot": n_boot}


def regression_diagnostics(result) -> pd.DataFrame:
    """Assumption checks for an OLS result: unequal variance, residual normality, collinearity.

    Breusch-Pagan is the regression counterpart of Levene's test; residual normality is
    checked twice, with Shapiro-Wilk and Jarque-Bera.
    """
    from statsmodels.stats.diagnostic import het_breuschpagan
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.stats.stattools import jarque_bera

    exog, names = result.model.exog, result.model.exog_names
    bp_p = het_breuschpagan(result.resid, exog)[1]
    sw_p = stats.shapiro(result.resid).pvalue
    jb_p = jarque_bera(result.resid)[1]
    vifs = {n: variance_inflation_factor(exog, i) for i, n in enumerate(names) if n != "Intercept"}
    worst = max(vifs, key=vifs.get)
    rows = [
        ("Equal variance of residuals", "Breusch-Pagan", bp_p, bp_p >= 0.05,
         "no heteroskedasticity" if bp_p >= 0.05 else "heteroskedastic: rely on robust SEs"),
        ("Residuals normally distributed", "Shapiro-Wilk", sw_p, sw_p >= 0.05,
         "normal" if sw_p >= 0.05 else "not normal: interpret p-values with care"),
        ("Residuals normally distributed", "Jarque-Bera", jb_p, jb_p >= 0.05,
         "normal" if jb_p >= 0.05 else "not normal: interpret p-values with care"),
        ("No multicollinearity", f"max VIF ({worst})", vifs[worst], vifs[worst] < 5,
         "VIF < 5" if vifs[worst] < 5 else "VIF >= 5: coefficients unstable"),
    ]
    return pd.DataFrame(rows, columns=["assumption", "test", "value", "ok", "meaning"])


HYPOTHESIS_COLUMNS = ["hypothesis", "magnitude", "effect_measure", "effect_size", "effect", "test",
                      "n", "statistic", "p", "p_holm", "statistically_significant", "result"]


def hypothesis_table(tests: list[dict], alpha: float = 0.05) -> pd.DataFrame:
    """Collect hypothesis tests and adjust for testing several at once (Holm method).

    Each dict needs: hypothesis, test, statistic, p. Give each one its business magnitude
    ("magnitude", in plain units) and effect size ("effect_measure", "effect_size",
    "effect") too: they come first in the table, because a p-value alone says nothing
    about how large or important an effect is.

    A hypothesis is "Supported" when its Holm-adjusted p-value is below alpha. That is
    statistical significance only; whether the effect matters is a separate, business
    judgement made from the magnitude.
    """
    from statsmodels.stats.multitest import multipletests

    df = pd.DataFrame(tests)
    reject, adjusted, *_ = multipletests(df["p"], alpha=alpha, method="holm")
    df["p_holm"] = adjusted
    df["statistically_significant"] = reject
    df["result"] = np.where(reject, "Supported", "Not supported")
    ordered = [c for c in HYPOTHESIS_COLUMNS if c in df]
    return df[ordered + [c for c in df if c not in ordered]]


# --- The project's hypothesis tests, in one place (used by notebook 02 and the dashboard) ---------

IMPORTS, WIND, SIZE = "imports_from_china_kg", "wind_capacity_gw", "total_generation_twh"


def main_hypothesis_tests(sample: pd.DataFrame, growth: pd.DataFrame, exports: pd.DataFrame,
                          order: list = ("Small", "Medium", "Large"), start: int = 2023,
                          end: int = 2024) -> pd.DataFrame:
    """H1-H5 with the tests chosen after the assumption checks, Holm-corrected.

    sample: exploratory.analysis_sample(panel); growth: exploratory.growth_vs_wind(panel, end);
    exports: the Export trade rows (partner, year, unit_value_usd_per_kg). Each row leads with
    its business magnitude and effect size (see hypothesis_table).
    """
    a = tidy_coefficients(fit_log_ols(sample, IMPORTS, [WIND]))
    b = tidy_coefficients(fit_log_ols(sample, IMPORTS, [WIND, SIZE]))
    w = f"log_{WIND}"
    h1 = correlation(sample, IMPORTS, WIND)
    h2 = partial_correlation(sample, IMPORTS, WIND, [SIZE])
    h3 = correlation(growth, "import_growth_pct", "wind_generation_change_twh")
    h4 = paired_change(exports, "partner", "year", "unit_value_usd_per_kg", start, end, test="sign")
    h5 = compare_groups(sample, IMPORTS, "size_group", list(order))
    split = split_medians(growth, "import_growth_pct", "wind_generation_change_twh")
    return hypothesis_table([
        {"hypothesis": "H1: imports rise with wind capacity",
         "magnitude": f"10x the wind capacity, {fold_change(a.loc[w, 'coef']):.1f}x the imports",
         "effect_measure": "Spearman rho", "effect_size": h1["r"], "effect": h1["strength"],
         "test": "Spearman correlation", "n": h1["n"], "statistic": h1["r"], "p": h1["p"]},
        {"hypothesis": "H2: wind matters after controlling for size",
         "magnitude": f"Same size, 10x the wind: {fold_change(b.loc[w, 'coef']):.1f}x the imports "
                      f"(95% CI {fold_change(b.loc[w, 'ci_low']):.2f}x to {fold_change(b.loc[w, 'ci_high']):.1f}x)",
         "effect_measure": "partial r", "effect_size": h2["r"], "effect": h2["strength"],
         "test": "Partial correlation (log10)", "n": h2["n"], "statistic": h2["r"], "p": h2["p"]},
        {"hypothesis": f"H3: faster wind growth, faster import growth ({end})",
         "magnitude": f"Median import growth {split['above']:+.0f}% where wind grew most, "
                      f"{split['below']:+.0f}% elsewhere",
         "effect_measure": "Spearman rho", "effect_size": h3["r"], "effect": h3["strength"],
         "test": "Spearman correlation", "n": h3["n"], "statistic": h3["r"], "p": h3["p"]},
        {"hypothesis": f"H4: buyers paid less per kg in {end} than {start}",
         "magnitude": f"Median buyer {h4['median_change_pct']:+.0f}% (95% CI {h4['ci_low_pct']:+.0f}% to "
                      f"{h4['ci_high_pct']:+.0f}%); {h4['share_falling']:.0%} paid less",
         "effect_measure": "rank-biserial r", "effect_size": h4["rank_biserial"],
         "effect": strength(h4["rank_biserial"]),
         "test": "Sign test (paired)", "n": h4["n"], "statistic": h4["statistic"], "p": h4["p"]},
        {"hypothesis": "H5: imports differ by country size",
         "magnitude": f"Large countries' median imports "
                      f"{h5['medians'][order[-1]] / h5['medians'][order[0]]:,.0f}x small countries'",
         "effect_measure": "epsilon-squared", "effect_size": h5["epsilon_sq"], "effect": h5["effect"],
         "test": "Kruskal-Wallis", "n": h5["n"], "statistic": h5["statistic"], "p": h5["p"]},
    ])


def regression_hypothesis_checks(sample: pd.DataFrame, panel: pd.DataFrame, exports: pd.DataFrame,
                                 start: int = 2023, end: int = 2024) -> pd.DataFrame:
    """Each hypothesis re-tested as a regression, with a residual normality check, Holm-corrected.

    H1, H2, H5: log-log OLS (wind only; wind + size). H3: OLS in log changes between start and
    end, size growth controlled. H4: OLS of the log price change on a constant, which is the
    paired t-test (its residual check shows whether that is valid).
    """
    wind_only = fit_log_ols(sample, IMPORTS, [WIND])
    with_size = fit_log_ols(sample, IMPORTS, [WIND, SIZE])
    growth_model = fit_log_change_ols(panel, IMPORTS, ["wind_generation_twh", SIZE], "country", "year",
                                      start, end)
    price_model = fit_log_change_ols(exports, "unit_value_usd_per_kg", [], "partner", "year", start, end)
    ev = {"H1": coefficient_evidence(wind_only, f"log_{WIND}"),
          "H2": coefficient_evidence(with_size, f"log_{WIND}"),
          "H3": coefficient_evidence(growth_model, "dlog_wind_generation_twh", factor=2),
          "H4": coefficient_evidence(price_model, "Intercept"),
          "H5": coefficient_evidence(with_size, f"log_{SIZE}")}
    keys = ["n", "statistic", "p", "residual_shapiro_p"]
    pct = log_ratio_to_pct
    return hypothesis_table([
        {"hypothesis": "H1: imports rise with wind capacity",
         "magnitude": f"10x the wind, {ev['H1']['fold']:.1f}x the imports "
                      f"({ev['H1']['fold_low']:.1f}x to {ev['H1']['fold_high']:.1f}x)",
         "effect_measure": "elasticity", "effect_size": ev["H1"]["coef"],
         "test": "Log-log OLS, wind only (Model A)", **{k: ev["H1"][k] for k in keys}},
        {"hypothesis": "H2: wind matters after controlling for size",
         "magnitude": f"Same size, 10x the wind: {ev['H2']['fold']:.1f}x the imports "
                      f"({ev['H2']['fold_low']:.2f}x to {ev['H2']['fold_high']:.1f}x)",
         "effect_measure": "elasticity", "effect_size": ev["H2"]["coef"],
         "test": "Log-log OLS, wind + size (Model B)", **{k: ev["H2"][k] for k in keys}},
        {"hypothesis": f"H3: faster wind growth, faster import growth ({end})",
         "magnitude": f"Doubling wind output: {ev['H3']['fold']:.2f}x the import growth "
                      f"({ev['H3']['fold_low']:.2f}x to {ev['H3']['fold_high']:.0f}x)",
         "effect_measure": "growth elasticity", "effect_size": ev["H3"]["coef"],
         "test": "OLS in log changes, size growth controlled", **{k: ev["H3"][k] for k in keys}},
        {"hypothesis": f"H4: buyers paid less per kg in {end} than {start}",
         "magnitude": f"Mean buyer {pct(ev['H4']['coef']):+.0f}% "
                      f"({pct(ev['H4']['ci_low']):+.0f}% to {pct(ev['H4']['ci_high']):+.0f}%)",
         "effect_measure": "mean log change", "effect_size": ev["H4"]["coef"],
         "test": "OLS of log price change on a constant (= paired t-test)",
         **{k: ev["H4"][k] for k in keys}},
        {"hypothesis": "H5: imports differ by country size",
         "magnitude": f"Same wind, 10x the size: {ev['H5']['fold']:.0f}x the imports "
                      f"({ev['H5']['fold_low']:.0f}x to {ev['H5']['fold_high']:.0f}x)",
         "effect_measure": "elasticity", "effect_size": ev["H5"]["coef"],
         "test": "Log-log OLS, wind + size (Model B)", **{k: ev["H5"][k] for k in keys}},
    ])
