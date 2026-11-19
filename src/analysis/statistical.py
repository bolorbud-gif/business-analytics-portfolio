"""Statistical analysis: correlation, partial correlation, regression and growth summaries.

Trade and electricity values are heavily right-skewed (a few large countries), so the
functions default to rank (Spearman) correlation or work on log10 values.
"""

import numpy as np
import pandas as pd
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


def correlation_matrix(df: pd.DataFrame, columns: list[str], method: str = "spearman") -> pd.DataFrame:
    """Pairwise correlation matrix of the columns (Spearman by default)."""
    return df[columns].corr(method=method)


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
                        log: bool = True) -> dict:
    """Correlation of x and y after removing what the controls explain.

    With log=True all columns are log10-transformed first (rows with values <= 0 are
    dropped). The p-value uses n - 2 - (number of controls) degrees of freedom.
    """
    cols = [x, y, *controls]
    d = df[cols].copy()
    if log:
        d = d.apply(log10_positive)
    d = d.dropna()
    rx, ry = residualize(d, x, controls), residualize(d, y, controls)
    r = float(np.corrcoef(rx, ry)[0, 1])
    dof = len(d) - 2 - len(controls)
    t = r * np.sqrt(dof / (1 - r ** 2))
    p = float(2 * stats.t.sf(abs(t), dof))
    return {"x": x, "y": y, "controls": ", ".join(controls), "log": log, "n": len(d),
            "r": r, "p": p, "strength": strength(r)}


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


# --- Hypothesis tests and assumption checks ----------------------------------------------

def normality_test(values: pd.Series, log: bool = False, alpha: float = 0.05) -> dict:
    """Shapiro-Wilk test of normality (on log10 values if log=True). Low p = not normal."""
    v = values.dropna()
    if log:
        v = log10_positive(v).dropna()
    w, p = stats.shapiro(v)
    return {"test": "Shapiro-Wilk", "scale": "log10" if log else "raw", "n": len(v),
            "statistic": float(w), "p": float(p), "normal": bool(p >= alpha)}


def compare_groups(df: pd.DataFrame, value: str, group: str, order: list | None = None) -> dict:
    """Kruskal-Wallis test: do the groups' distributions differ? (no normality assumed)"""
    order = order or sorted(df[group].dropna().unique())
    samples = [df.loc[df[group] == g, value].dropna() for g in order]
    h, p = stats.kruskal(*samples)
    return {"test": "Kruskal-Wallis", "groups": len(order), "n": int(sum(len(s) for s in samples)),
            "statistic": float(h), "p": float(p),
            "medians": {str(g): float(s.median()) for g, s in zip(order, samples)}}


def paired_change(df: pd.DataFrame, entity: str, period: str, value: str, start, end) -> dict:
    """Wilcoxon signed-rank test on the change of `value` for entities seen in both periods.

    Tests the log ratio end/start, so a halving and a doubling count equally. Reports the
    median change in percent and the share of entities whose value fell.
    """
    wide = df.pivot_table(index=entity, columns=period, values=value, aggfunc="mean")
    pair = wide[[start, end]].dropna()
    pair = pair[(pair > 0).all(axis=1)]
    ratio = np.log(pair[end] / pair[start])
    w, p = stats.wilcoxon(ratio)
    return {"test": "Wilcoxon signed-rank", "n": len(pair), "statistic": float(w), "p": float(p),
            "median_change_pct": float((np.exp(ratio.median()) - 1) * 100),
            "share_falling": float((ratio < 0).mean())}


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
    """Assumption checks for an OLS result: unequal variance, residual normality, collinearity."""
    from statsmodels.stats.diagnostic import het_breuschpagan
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.stats.stattools import jarque_bera

    exog, names = result.model.exog, result.model.exog_names
    bp_p = het_breuschpagan(result.resid, exog)[1]
    jb_p = jarque_bera(result.resid)[1]
    vifs = {n: variance_inflation_factor(exog, i) for i, n in enumerate(names) if n != "Intercept"}
    worst = max(vifs, key=vifs.get)
    rows = [
        ("Equal variance of residuals", "Breusch-Pagan", bp_p, bp_p >= 0.05,
         "no heteroskedasticity" if bp_p >= 0.05 else "heteroskedastic: rely on robust SEs"),
        ("Residuals normally distributed", "Jarque-Bera", jb_p, jb_p >= 0.05,
         "normal" if jb_p >= 0.05 else "not normal: interpret p-values with care"),
        ("No multicollinearity", f"max VIF ({worst})", vifs[worst], vifs[worst] < 5,
         "VIF < 5" if vifs[worst] < 5 else "VIF >= 5: coefficients unstable"),
    ]
    return pd.DataFrame(rows, columns=["assumption", "test", "value", "ok", "meaning"])


def hypothesis_table(tests: list[dict], alpha: float = 0.05) -> pd.DataFrame:
    """Collect hypothesis tests and adjust for testing several at once (Holm method).

    Each dict needs: hypothesis, test, statistic, p. A hypothesis is "supported" when
    its Holm-adjusted p-value is below alpha.
    """
    from statsmodels.stats.multitest import multipletests

    df = pd.DataFrame(tests)
    reject, adjusted, *_ = multipletests(df["p"], alpha=alpha, method="holm")
    df["p_holm"] = adjusted
    df["result"] = np.where(reject, "Supported", "Not supported")
    return df
