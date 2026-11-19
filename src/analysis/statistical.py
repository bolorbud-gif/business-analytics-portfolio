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
    return pd.DataFrame([correlation(df, x, y, method) for x, y in pairs])


def correlation_matrix(df: pd.DataFrame, columns: list[str], method: str = "spearman") -> pd.DataFrame:
    return df[columns].corr(method=method)


def residualize(df: pd.DataFrame, column: str, controls: list[str]) -> pd.Series:
    """What is left of `column` after a linear fit on the controls (with intercept)."""
    X = np.column_stack([np.ones(len(df))] + [df[c] for c in controls])
    beta, *_ = np.linalg.lstsq(X, df[column], rcond=None)
    return df[column] - X @ beta


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
