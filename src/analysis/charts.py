"""Charts for the exploratory analysis.

One style for every figure: light surface, recessive grid and axes, thin marks, at most
three categorical colors per chart (blue, orange, aqua: validated as distinguishable for
colour-blind readers in every pair), and a title that states the finding. Figures for
the docs are saved to docs/figures/ with save().
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "docs" / "figures"

SURFACE, INK, INK_2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, NEUTRAL = "#e1e0d9", "#c3c2b7", "#f0efec"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
SERIES = [BLUE, ORANGE, AQUA]  # fixed order; never more than three series in one chart
DIVERGING = LinearSegmentedColormap.from_list("blue_gray_red", [RED, NEUTRAL, BLUE])


def apply_style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
        "font.size": 10, "text.color": INK, "axes.labelcolor": INK_2,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2, "lines.linewidth": 2, "legend.frameon": False,
        "axes.axisbelow": True,
    })


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
    """Correlation matrix on a blue (positive) / gray (zero) / red (negative) scale."""
    apply_style()
    n = len(matrix)
    fig, ax = plt.subplots(figsize=(1.0 * n + 3.2, 0.75 * n + 2.2))
    ax.grid(False)
    lower = np.tril(np.ones((n, n), dtype=bool), k=-1)  # each pair once, no diagonal of 1s
    shown = np.where(lower, matrix.values, np.nan)
    im = ax.imshow(shown, cmap=DIVERGING, vmin=-1, vmax=1)
    for i in range(n):
        for j in range(n):
            if lower[i, j]:
                ax.text(j, i, f"{matrix.values[i, j] + 0.0:.2f}".replace("-0.00", "0.00"), ha="center", va="center",
                        fontsize=9.5, color=INK)
    ax.set_xticks(range(n - 1), labels[:-1], rotation=35, ha="right")
    ax.set_yticks(range(1, n), labels[1:])
    ax.set_xlim(-0.5, n - 1.5)
    ax.set_ylim(n - 0.5, 0.5)
    for spine in ax.spines.values():
        spine.set_visible(False)
    cbar = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label("Spearman correlation", color=INK_2)
    cbar.outline.set_visible(False)
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
    edges = np.logspace(np.log10(v.min()), np.log10(v.max()), bins + 1)
    ax.hist(v, bins=edges, color=BLUE, edgecolor=SURFACE, linewidth=1.5)
    _log_axis(ax, "x")
    ax.axvline(v.median(), color=INK_2, linewidth=1.2, linestyle="--")
    ax.annotate(f"median {v.median():,.0f}", (v.median(), ax.get_ylim()[1] * 0.92),
                xytext=(6, 0), textcoords="offset points", fontsize=9, color=INK_2)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Countries")
    ax.grid(axis="x", visible=False)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.86))
    return fig


def group_strip(df: pd.DataFrame, value: str, group: str, order: list[str], ylabel: str,
                title: str, subtitle: str, source: str, tick_labels: list[str] | None = None):
    """Every observation per group on a log scale, with the median marked."""
    apply_style()
    fig, ax = plt.subplots(figsize=(7, 4))
    rng = np.random.default_rng(0)
    for i, (name, color) in enumerate(zip(order, SERIES)):
        v = df.loc[df[group] == name, value].dropna()
        v = v[v > 0]
        ax.scatter(i + rng.uniform(-0.18, 0.18, len(v)), v, s=36, color=color,
                   edgecolor=SURFACE, linewidth=0.8, alpha=0.85, zorder=3)
        ax.hlines(v.median(), i - 0.3, i + 0.3, color=INK, linewidth=2, zorder=4)
        ax.annotate(f"median ${v.median():,.0f}/kg", (i + 0.32, v.median()), va="center",
                    fontsize=9, color=INK_2)
    _log_axis(ax, "y")
    ax.set_xticks(range(len(order)), tick_labels or order)
    ax.set_xlim(-0.6, len(order) - 0.1 + 0.6)
    ax.set_ylabel(ylabel)
    ax.grid(axis="x", visible=False)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.86))
    return fig
