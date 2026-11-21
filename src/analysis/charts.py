"""Charts for the exploratory analysis (Matplotlib + Seaborn).

One style for every figure: light surface, recessive grid and axes, thin marks, at most
three categorical colors per chart (blue, orange, aqua: validated as distinguishable for
colour-blind readers in every pair), labelled axes, and a title that states the finding.
Figures are saved to docs/figures/ by save() as 300 dpi PNG plus vector SVG.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "docs" / "figures"

from src.analysis.palette import (AQUA, AXIS, BLUE, GRID, INK, INK_2, MUTED,  # noqa: F401
                                  NEUTRAL, ORANGE, RED, SERIES, SURFACE)
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
    # fixed sizes, so Seaborn's context scaling can't enlarge labels into each other
    "axes.labelsize": 10, "axes.titlesize": 10.5, "xtick.labelsize": 9.5,
    "ytick.labelsize": 9.5, "legend.fontsize": 9, "legend.title_fontsize": 9,
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
    """Put one axis on a log scale with compact tick labels (1k, 1M)."""
    axis = ax.yaxis if which == "y" else ax.xaxis
    (ax.set_yscale if which == "y" else ax.set_xscale)("log")
    axis.set_major_formatter(FuncFormatter(_compact))


def _titles(fig, title: str, subtitle: str | None = None) -> None:
    """Left-aligned bold title (the finding) and an optional subtitle (measure, sample, years)."""
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.01, 0.905, subtitle, ha="left", va="top", fontsize=9.5, color=INK_2)


def _source(fig, text: str) -> None:
    """Small muted source line in the bottom-left corner."""
    fig.text(0.01, 0.005, text, ha="left", va="bottom", fontsize=8, color=MUTED)


def save(fig, name: str, folder: Path = FIGURES) -> Path:
    """Save a figure as 300 dpi PNG and vector SVG in docs/figures/ (or `folder`).

    Returns the PNG path; the SVG sits next to it with the same name.
    """
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    # no date stamp and fixed element ids, so an unchanged chart gives an identical SVG
    with plt.rc_context({"svg.hashsalt": "rare-earth"}):
        fig.savefig(path.with_suffix(".svg"), bbox_inches="tight", metadata={"Date": None})
    return path


def show(fig, name: str | None = None, save_figure: bool = True, folder: Path = FIGURES) -> None:
    """Display a figure in a notebook, save it with save() if asked, then close it.

    Notebooks pass save_figure=False when running on the synthetic sample, so sample charts
    never overwrite the real ones in docs/figures/. Returns nothing, so a notebook cell that
    ends with show() prints no file path (which would differ from machine to machine).
    """
    if save_figure and name:
        save(fig, name, folder)
    try:
        from IPython.display import display
        display(fig)
    except ImportError:  # plain Python: nothing to display in
        pass
    plt.close(fig)


def market_share_bars(shares: pd.DataFrame, title: str, subtitle: str, source: str,
                      ylabel: str = "Buying country"):
    """Horizontal bars of each country's share (output of exploratory.market_shares)."""
    apply_style()
    s = shares["share"][::-1]
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(s) + 1.6))
    colors = [AXIS if str(i).startswith("All other") else BLUE for i in s.index]
    ax.barh(s.index, s.values * 100, height=0.62, color=colors)
    for y, v in enumerate(s.values * 100):
        ax.text(v + 0.6, y, f"{v:.1f}%", va="center", fontsize=9, color=INK_2)
    ax.set_xlabel("Share of China's exports by weight (%)")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, s.max() * 100 * 1.15)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.88))
    return fig


def change_bars(changes: pd.Series, title: str, subtitle: str, source: str,
                xlabel: str = "Measure"):
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
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", visible=False)
    lo, hi = min(changes.min(), 0), max(changes.max(), 0)
    ax.set_ylim(lo * 1.3 - 2, hi * 1.3 + 4)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.04, 1, 0.84))
    return fig


def line_trend(df: pd.DataFrame, x: str, series: list[str], labels: list[str], ylabel: str,
               title: str, subtitle: str, source: str, xlabel: str = "Year"):
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
    ax.set_xlabel(xlabel)
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
    a.legend(title="Country size (total electricity generation)", title_fontsize=9,
             fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=3)
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


def relationship_scatter(df: pd.DataFrame, x: str, y: str, xlabel: str, ylabel: str, title: str,
                         subtitle: str, source: str, note: str | None = None,
                         xscale: str = "linear", yscale: str = "linear", linthresh: float = 0.1,
                         ref_x: float | None = None, ref_y: float | None = None,
                         note_loc: str = "upper left"):
    """Scatter of one relationship, to show what a reported correlation looks like.

    xscale/yscale: "linear", "log" or "symlog" (log-like but allows zero and negative
    values, linear within +-linthresh). A log axis spanning about a decade or less gets
    extra ticks (0.5, 1, 2, or 0.7, 1, 1.5, 2 for a narrower range). ref_x/ref_y draw reference lines, e.g. no change.
    note is printed in the top corner given by note_loc ("upper left" or "upper right"),
    e.g. the correlation and its p-value; pick the corner with no points under it.
    """
    apply_style()
    d = df[[x, y]].dropna()
    fig, ax = plt.subplots(figsize=(7.5, 5))
    if ref_x is not None:
        ax.axvline(ref_x, color=AXIS, linewidth=1)
    if ref_y is not None:
        ax.axhline(ref_y, color=AXIS, linewidth=1)
    ax.scatter(d[x], d[y], s=48, color=BLUE, edgecolor=SURFACE, linewidth=1, alpha=0.9, zorder=3)
    for axis, col, scale, setter in [(ax.xaxis, x, xscale, ax.set_xscale),
                                     (ax.yaxis, y, yscale, ax.set_yscale)]:
        if scale == "symlog":
            setter("symlog", linthresh=linthresh)
        elif scale == "log":
            setter("log")
            positive = d.loc[d[col] > 0, col]
            decades = np.log10(positive.max() / positive.min()) if len(positive) else np.inf
            if decades < 1.2:  # narrow range: label 2 and 5 too (under ~0.6 decades, 1.5, 3, 7 as well)
                subs = (1.0, 2.0, 5.0) if decades >= 0.6 else (1.0, 1.5, 2.0, 3.0, 5.0, 7.0)
                axis.set_major_locator(LogLocator(base=10, subs=subs))
            axis.set_minor_formatter(NullFormatter())  # no "2 x 10^0" labels between ticks
        if scale != "linear":
            axis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g}"))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if note:
        right = note_loc == "upper right"
        ax.text(0.98 if right else 0.02, 0.97, note, transform=ax.transAxes,
                ha="right" if right else "left", va="top", fontsize=9.5, color=INK_2)
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
                title: str, subtitle: str, source: str, tick_labels: list[str] | None = None,
                xlabel: str = ""):
    """Every observation per group on a log scale, with the median marked."""
    apply_style()
    d = df[df[value] > 0]
    fig, ax = plt.subplots(figsize=(7, 4))
    np.random.seed(0)  # Seaborn's jitter is random: fix it so the figure is reproducible
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
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.xaxis.grid(False)
    ax.yaxis.grid(True)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.86))
    return fig


def pair_plot(df: pd.DataFrame, columns: list[str], labels: list[str], hue: str,
              hue_order: list[str], title: str, subtitle: str, source: str,
              height: float = 2.1):
    """Seaborn pair plot of log10 values: every pairwise relationship at once, coloured by group.

    Rows with a zero or negative value in any column are left out (log10 is undefined).
    height is the size of each panel in inches.
    """
    apply_style()
    d = df[columns].apply(lambda s: np.log10(s.where(s > 0))).rename(columns=dict(zip(columns, labels)))
    d[hue] = df[hue].astype(str)
    n = len(hue_order)
    grid = sns.pairplot(d.dropna(), hue=hue, hue_order=hue_order, palette=SERIES[:n],
                        corner=True, height=height, diag_kind="kde",
                        plot_kws={"s": 28, "edgecolor": SURFACE, "linewidth": 0.6, "alpha": 0.85},
                        diag_kws={"fill": True, "alpha": 0.3, "linewidth": 1.5})
    grid.figure.set_facecolor(SURFACE)
    for ax in grid.axes.flat:
        if ax is not None:
            ax.grid(True, color=GRID, linewidth=0.5)
    sns.move_legend(grid, "upper right", bbox_to_anchor=(0.92, 0.82), title="Country size",
                    frameon=False)
    inches = grid.figure.get_figheight()  # keep the title block the same height at any size
    grid.figure.subplots_adjust(top=1 - 0.85 / inches, bottom=0.1, left=0.09)
    grid.figure.suptitle(title, x=0.01, y=1 - 0.13 / inches, ha="left", fontsize=13,
                         fontweight="bold", color=INK)
    grid.figure.text(0.01, 1 - 0.47 / inches, subtitle, ha="left", va="top", fontsize=9.5,
                     color=INK_2)
    _source(grid.figure, source)
    return grid.figure


def coefficient_plot(models: dict[str, pd.DataFrame], terms: dict[str, str], title: str,
                     subtitle: str, source: str, xlabel: str = "Elasticity (95% CI)",
                     ylabel: str = "Predictor"):
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
                       zorder=3, label=name)
            ax.annotate(f"{row['coef']:.2f}", (row["ci_high"], y), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=9, color=INK_2)
    ax.axvline(0, color=AXIS, linewidth=1.2)
    ax.set_yticks(range(len(terms)), labels[::-1])
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", visible=False)
    handles, names = ax.get_legend_handles_labels()
    seen = dict(zip(names, handles))
    ax.legend(seen.values(), seen.keys(), loc="upper right")
    ax.set_ylim(-0.6, len(terms) - 0.4)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.04, 1, 0.84))
    return fig


# --- Analytics engine (Assignment 6) ----------------------------------------------------------

def cv_comparison(panels: dict, title: str, subtitle: str, source: str, chosen: dict | None = None):
    """Cross-validated score of each model, mean +- one standard deviation across folds.

    panels: {panel title: (summary table from modeling.evaluate.summarize_cv, metric, x label)},
    one panel per task, stacked. The first row of each table is the baseline (gray); chosen:
    {panel title: model name} marks the selected model (orange); other models are blue.
    """
    from matplotlib.lines import Line2D
    apply_style()
    sizes = [len(t) for t, _, _ in panels.values()]
    fig, axes = plt.subplots(len(panels), 1, figsize=(8.5, 0.55 * sum(sizes) + 1.6 * len(panels) + 1.2),
                             gridspec_kw={"height_ratios": sizes})
    for ax, (panel, (table, metric, xlabel)) in zip(np.atleast_1d(axes), panels.items()):
        t = table.reset_index(drop=True)
        k = len(t)
        for i, row in t.iterrows():
            y = k - 1 - i
            color = (MUTED if i == 0 else ORANGE if chosen and chosen.get(panel) == row["model"]
                     else BLUE)
            mean, sd = row[metric], row[f"{metric}_sd"]
            ax.plot([mean - sd, mean + sd], [y, y], color=color, linewidth=2)
            ax.scatter(mean, y, s=64, color=color, edgecolor=SURFACE, linewidth=1.5, zorder=3)
            ax.annotate(f"{mean:.2f}", (mean + sd, y), xytext=(6, 0), textcoords="offset points",
                        va="center", fontsize=9, color=INK_2)
        ax.set_yticks(range(k), list(t["model"])[::-1])
        ax.set_ylim(-0.6, k - 0.4)
        ax.set_title(panel, loc="left", fontsize=10.5, color=INK)
        ax.set_xlabel(xlabel)
        ax.grid(axis="y", visible=False)
        lo, hi = ax.get_xlim()
        ax.set_xlim(lo, hi + (hi - lo) * 0.08)  # room for the value labels
    legend = [Line2D([], [], color=c, marker="o", linewidth=2, label=lab)
              for c, lab in [(MUTED, "Baseline (dummy)"), (BLUE, "Candidate"), (ORANGE, "Chosen")]]
    inches = fig.get_figheight()  # title block a fixed height in inches, whatever the figure size
    fig.suptitle(title, x=0.01, y=1 - 0.13 / inches, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.text(0.01, 1 - 0.47 / inches, subtitle, ha="left", va="top", fontsize=9.5, color=INK_2)
    fig.legend(handles=legend, loc="upper left", ncol=3, bbox_to_anchor=(0.005, 1 - 0.72 / inches))
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.25 / inches, 1, 1 - 1.15 / inches))
    fig.subplots_adjust(top=1 - 1.3 / inches)  # tight_layout leaves room for the suptitle twice
    return fig


def predicted_vs_actual(actual, predicted, labels, title: str, subtitle: str, source: str,
                        note: str | None = None, n_labels: int = 3,
                        xlabel: str = "Actual imports from China (kg, log scale)",
                        ylabel: str = "Predicted imports (kg, log scale)"):
    """Predicted against actual values on log axes, with the perfect-prediction line and
    dotted lines where a prediction is 10 times too high or too low. The n_labels largest
    misses are labelled (labels: one name per point)."""
    apply_style()
    a, p = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    labels = list(labels)
    fig, ax = plt.subplots(figsize=(7.5, 5.8))
    lo, hi = min(a.min(), p.min()) / 3, max(a.max(), p.max()) * 3
    line = np.array([lo, hi])
    ax.plot(line, line, color=INK_2, linewidth=1.2, label="Perfect prediction")
    ax.plot(line, line * 10, color=MUTED, linewidth=1, linestyle=":", label="10x too high or too low")
    ax.plot(line, line / 10, color=MUTED, linewidth=1, linestyle=":")
    ax.scatter(a, p, s=48, color=BLUE, edgecolor=SURFACE, linewidth=1, zorder=3,
               label="Test country-year")
    for i in np.argsort(-np.abs(np.log10(p / a)))[:n_labels]:
        # Overestimates sit above the line: label them on the left, in the open, unless the
        # point is so close to the left edge that the label would run into the axis.
        near_left = np.log10(a[i] / lo) < 0.2 * np.log10(hi / lo)
        left = p[i] > a[i] and not near_left
        ax.annotate(labels[i], (a[i], p[i]), xytext=(-7 if left else 7, 3), textcoords="offset points",
                    ha="right" if left else "left", fontsize=9, color=INK_2)
    _log_axis(ax, "x")
    _log_axis(ax, "y")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend(loc="upper left")
    if note:
        ax.text(0.98, 0.03, note, transform=ax.transAxes, ha="right", va="bottom", fontsize=9.5,
                color=INK_2)
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.86))
    return fig


def roc_chart(curves: dict, title: str, subtitle: str, source: str, marker: tuple | None = None):
    """ROC curves (true-positive rate against false-positive rate), each labelled with its
    AUC, against the diagonal of a model that guesses (AUC 0.5).

    curves: {name: modeling.evaluate.roc_points output}, at most three; marker: optional
    (false-positive rate, true-positive rate, label) for the threshold in use.
    """
    apply_style()
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot([0, 1], [0, 1], color=MUTED, linestyle="--", linewidth=1, label="Guessing (AUC 0.50)")
    for (name, c), color in zip(curves.items(), SERIES):
        ax.plot(c["fpr"], c["tpr"], color=color, label=f"{name} (AUC {c['AUC']:.2f})")
    if marker:
        fpr, tpr, label = marker
        ax.scatter(fpr, tpr, s=64, color=INK, edgecolor=SURFACE, linewidth=1.5, zorder=4)
        ax.annotate(label, (fpr, tpr), xytext=(10, -28), textcoords="offset points", fontsize=9,
                    color=INK_2, bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.5})
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("False-positive rate (share of smaller buyers flagged)")
    ax.set_ylabel("True-positive rate (recall: share of major buyers flagged)")
    ax.legend(loc="lower right")
    _titles(fig, title, subtitle)
    _source(fig, source)
    fig.tight_layout(rect=(0, 0.03, 1, 0.86))
    return fig
