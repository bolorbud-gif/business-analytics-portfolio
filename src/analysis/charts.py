"""Charts for the exploratory analysis (Matplotlib + Seaborn).

One style for every figure: light surface, recessive grid and axes, thin marks, at most
three categorical colors per chart (blue, orange, aqua: validated as distinguishable for
colour-blind readers in every pair), and a title that states the finding. Figures for
the docs are saved to docs/figures/ with save().
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "docs" / "figures"

SURFACE, INK, INK_2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, NEUTRAL = "#e1e0d9", "#c3c2b7", "#f0efec"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
SERIES = [BLUE, ORANGE, AQUA]  # fixed order; never more than three series in one chart
DIVERGING = LinearSegmentedColormap.from_list("blue_gray_red", [RED, NEUTRAL, BLUE])


RC = {
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "font.size": 10, "text.color": INK, "axes.labelcolor": INK_2,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2, "lines.linewidth": 2, "legend.frameon": False,
    "axes.axisbelow": True,
}


def apply_style() -> None:
    """Seaborn theme with the project's colours and recessive grid (applies to Matplotlib too)."""
    sns.set_theme(style="white", palette=SERIES, rc=RC)


def _compact(value, _pos=None) -> str:
    """Axis label like 1k, 10M instead of 10^3, 10^7."""
    for div, suffix in [(1e9, "B"), (1e6, "M"), (1e3, "k")]:
        if abs(value) >= div:
            return f"{value / div:g}{suffix}"
    return f"{value:g}"


def _log_axis(ax, which: str = "y") -> None:
    axis = ax.yaxis if which == "y" else ax.xaxis
    (ax.set_yscale if which == "y" else ax.set_xscale)("log")
    axis.set_major_formatter(FuncFormatter(_compact))


def _titles(fig, title: str, subtitle: str | None = None) -> None:
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.01, 0.905, subtitle, ha="left", va="top", fontsize=9.5, color=INK_2)


def _source(fig, text: str) -> None:
    fig.text(0.01, 0.005, text, ha="left", va="bottom", fontsize=8, color=MUTED)


def save(fig, name: str, folder: Path = FIGURES) -> Path:
    """Save a figure as PNG (150 dpi) in docs/figures/ or another folder; returns the path."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    return path


def market_share_bars(shares: pd.DataFrame, title: str, subtitle: str, source: str):
    """Horizontal bars of each country's share (output of exploratory.market_shares)."""
    apply_style()
    s = shares["share"][::-1]
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(s) + 1.6))
    colors = [AXIS if str(i).startswith("All other") else BLUE for i in s.index]
    ax.barh(s.index, s.values * 100, height=0.62, color=colors)
    for y, v in enumerate(s.values * 100):
        ax.text(v + 0.6, y, f"{v:.1f}%", va="center", fontsize=9, color=INK_2)
    ax.set_xlabel("Share of China's exports by weight (%)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, s.max() * 100 * 1.15)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.88))
    return fig


def change_bars(changes: pd.Series, title: str, subtitle: str, source: str):
    """Percent changes as bars: blue up, red down, from a zero baseline."""
    apply_style()
    fig, ax = plt.subplots(figsize=(7, 3.6))
    colors = [BLUE if v >= 0 else RED for v in changes.values]
    ax.bar(changes.index, changes.values, width=0.55, color=colors)
    ax.axhline(0, color=AXIS, linewidth=1)
    for x, v in enumerate(changes.values):
        ax.text(x, v + (1.2 if v >= 0 else -1.2), f"{v:+.1f}%", ha="center",
                va="bottom" if v >= 0 else "top", fontsize=10, color=INK, fontweight="bold")
    ax.set_ylabel("Change (%)")
    ax.grid(axis="x", visible=False)
    lo, hi = min(changes.min(), 0), max(changes.max(), 0)
    ax.set_ylim(lo * 1.3 - 2, hi * 1.3 + 4)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.04, 1, 0.84))
    return fig


def line_trend(df: pd.DataFrame, x: str, series: list[str], labels: list[str], ylabel: str,
               title: str, subtitle: str, source: str):
    """Up to three lines on one axis, each labelled at its end and in the legend."""
    apply_style()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    last = df.iloc[-1]
    ends = sorted(((last[c], c, lab) for c, lab in zip(series, labels)), key=lambda t: t[0])
    gap = (df[series].max().max()) * 0.06
    placed = []
    for value, col, label in ends:
        y = max(value, placed[-1] + gap) if placed else value
        placed.append(y)
        ax.annotate(f"{label}: {last[col]:,.0f}", (last[x], value), xytext=(last[x] + 0.12, y),
                    textcoords="data", va="center", fontsize=9, color=INK_2)
    for col, label, color in zip(series, labels, SERIES):
        ax.plot(df[x], df[col], color=color, marker="o", markersize=6, label=label)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, None)
    ax.set_xticks(df[x])
    ax.set_xlim(df[x].min() - 0.3, df[x].max() + 1.6)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left")
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.86))
    return fig


def confounding_scatter(raw: pd.DataFrame, x: str, y: str, group: str, group_order: list[str],
                        partial: pd.DataFrame, raw_title: str, partial_title: str,
                        title: str, subtitle: str, source: str, xlabel: str, ylabel: str):
    """Two panels: the raw log-log relationship coloured by a size group, then the same
    relationship after removing size (residuals)."""
    apply_style()
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.6))
    for name, color in zip(group_order, SERIES):
        d = raw[raw[group] == name]
        a.scatter(d[x], d[y], s=48, color=color, edgecolor=SURFACE, linewidth=1, label=name,
                  alpha=0.9, zorder=3)
    _log_axis(a, "x")
    _log_axis(a, "y")
    a.set_xlabel(xlabel)
    a.set_ylabel(ylabel)
    a.set_title(raw_title, loc="left", fontsize=10.5, color=INK)
    a.legend(title="Country size (total electricity generation)", title_fontsize=8.5,
             fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3)
    b.scatter(partial["x_resid"], partial["y_resid"], s=48, color=BLUE, edgecolor=SURFACE,
              linewidth=1, alpha=0.9, zorder=3)
    b.axhline(0, color=AXIS, linewidth=1)
    b.axvline(0, color=AXIS, linewidth=1)
    slope, intercept = np.polyfit(partial["x_resid"], partial["y_resid"], 1)
    xs = np.linspace(partial["x_resid"].min(), partial["x_resid"].max(), 20)
    b.plot(xs, intercept + slope * xs, color=INK_2, linewidth=1.5, linestyle="--")
    b.set_xlabel("Wind capacity, relative to country size (log10 residual)")
    b.set_ylabel("Imports, relative to country size (log10 residual)")
    b.set_title(partial_title, loc="left", fontsize=10.5, color=INK)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.86))
    return fig


def correlation_heatmap(matrix: pd.DataFrame, labels: list[str], title: str, subtitle: str,
                        source: str):
    """Correlation matrix (lower triangle) on a blue (positive) / gray (zero) / red scale."""
    apply_style()
    n = len(matrix)
    m = pd.DataFrame(matrix.values, index=labels, columns=labels)
    mask = ~np.tril(np.ones((n, n), dtype=bool), k=-1)  # each pair once, no diagonal of 1s
    text = m.map(lambda v: f"{v + 0.0:.2f}".replace("-0.00", "0.00"))
    fig, ax = plt.subplots(figsize=(1.0 * n + 3.2, 0.75 * n + 2.2))
    sns.heatmap(m.iloc[1:, :-1], mask=mask[1:, :-1], annot=text.iloc[1:, :-1], fmt="",
                cmap=DIVERGING, vmin=-1, vmax=1, linewidths=2, linecolor=SURFACE,
                annot_kws={"fontsize": 9.5, "color": INK},
                cbar_kws={"label": "Spearman correlation", "fraction": 0.04, "pad": 0.02}, ax=ax)
    ax.grid(False)
    ax.tick_params(length=0)
    ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha="right")
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.9))
    return fig


def log_histogram(values: pd.Series, xlabel: str, title: str, subtitle: str, source: str,
                  bins: int = 20):
    """Histogram with log-spaced bins, for right-skewed positive values."""
    apply_style()
    v = values[values > 0].dropna()
    fig, ax = plt.subplots(figsize=(8, 3.8))
    sns.histplot(v, bins=bins, log_scale=True, color=BLUE, edgecolor=SURFACE, linewidth=1.5,
                 alpha=1, ax=ax)
    ax.xaxis.set_major_formatter(FuncFormatter(_compact))
    ax.axvline(v.median(), color=INK_2, linewidth=1.2, linestyle="--")
    ax.annotate(f"median {v.median():,.0f}", (v.median(), ax.get_ylim()[1] * 0.92),
                xytext=(6, 0), textcoords="offset points", fontsize=9, color=INK_2)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Countries")
    ax.xaxis.grid(False)
    ax.yaxis.grid(True)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.86))
    return fig


def group_strip(df: pd.DataFrame, value: str, group: str, order: list[str], ylabel: str,
                title: str, subtitle: str, source: str, tick_labels: list[str] | None = None):
    """Every observation per group on a log scale, with the median marked."""
    apply_style()
    d = df[df[value] > 0]
    fig, ax = plt.subplots(figsize=(7, 4))
    sns.stripplot(data=d, x=group, y=value, hue=group, order=order, hue_order=order,
                  palette=SERIES[:len(order)], size=6, jitter=0.18, edgecolor=SURFACE,
                  linewidth=0.8, alpha=0.85, legend=False, ax=ax)
    for i, name in enumerate(order):
        med = d.loc[d[group] == name, value].median()
        ax.hlines(med, i - 0.3, i + 0.3, color=INK, linewidth=2, zorder=4)
        ax.annotate(f"median ${med:,.0f}/kg", (i + 0.32, med), va="center", fontsize=9,
                    color=INK_2)
    _log_axis(ax, "y")
    ax.set_xticks(range(len(order)), tick_labels or order)
    ax.set_xlim(-0.6, len(order) - 0.1 + 0.6)
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.xaxis.grid(False)
    ax.yaxis.grid(True)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.86))
    return fig


def pair_plot(df: pd.DataFrame, columns: list[str], labels: list[str], hue: str,
              hue_order: list[str], title: str, subtitle: str, source: str):
    """Seaborn pair plot of log10 values: every pairwise relationship at once, coloured by group."""
    apply_style()
    d = df[columns].apply(lambda s: np.log10(s.where(s > 0))).rename(columns=dict(zip(columns, labels)))
    d[hue] = df[hue].astype(str)
    grid = sns.pairplot(d.dropna(), hue=hue, hue_order=hue_order, palette=SERIES[:len(hue_order)],
                        corner=True, height=2.1, diag_kind="kde",
                        plot_kws={"s": 28, "edgecolor": SURFACE, "linewidth": 0.6, "alpha": 0.85},
                        diag_kws={"fill": True, "alpha": 0.3, "linewidth": 1.5})
    grid.figure.set_facecolor(SURFACE)
    for ax in grid.axes.flat:
        if ax is not None:
            ax.grid(True, color=GRID, linewidth=0.5)
    sns.move_legend(grid, "upper right", bbox_to_anchor=(0.92, 0.82), title="Country size",
                    frameon=False)
    grid.figure.subplots_adjust(top=0.86, bottom=0.1, left=0.09)
    grid.figure.suptitle(title, x=0.01, y=0.985, ha="left", fontsize=13, fontweight="bold",
                         color=INK)
    grid.figure.text(0.01, 0.945, subtitle, ha="left", va="top", fontsize=9.5, color=INK_2)
    _source(grid.figure, source)
    return grid.figure


def coefficient_plot(models: dict[str, pd.DataFrame], terms: dict[str, str], title: str,
                     subtitle: str, source: str, xlabel: str = "Elasticity (95% CI)"):
    """Estimates with 95% intervals for selected terms, one colour per model.

    models: {model name: output of statistical.tidy_coefficients}; terms: {term: label}.
    """
    apply_style()
    fig, ax = plt.subplots(figsize=(8, 1.0 * len(terms) + 1.9))
    labels = list(terms.values())
    offsets = np.linspace(-0.12, 0.12, len(models)) if len(models) > 1 else [0]
    for (name, tidy), color, off in zip(models.items(), SERIES, offsets):
        for i, term in enumerate(terms):
            if term not in tidy.index:
                continue
            row = tidy.loc[term]
            y = len(terms) - 1 - i - off
            ax.plot([row["ci_low"], row["ci_high"]], [y, y], color=color, linewidth=2)
            ax.scatter(row["coef"], y, s=64, color=color, edgecolor=SURFACE, linewidth=1.5,
                       zorder=3, label=name if i == 0 or term == list(terms)[0] else None)
            ax.annotate(f"{row['coef']:.2f}", (row["ci_high"], y), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=9, color=INK_2)
    ax.axvline(0, color=AXIS, linewidth=1.2)
    ax.set_yticks(range(len(terms)), labels[::-1])
    ax.set_xlabel(xlabel)
    ax.grid(axis="y", visible=False)
    handles, names = ax.get_legend_handles_labels()
    seen = dict(zip(names, handles))
    ax.legend(seen.values(), seen.keys(), loc="upper right")
    ax.set_ylim(-0.6, len(terms) - 0.4)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.04, 1, 0.84))
    return fig
