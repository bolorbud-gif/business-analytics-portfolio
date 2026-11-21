"""Reusable pieces of the dashboard: number formatting, KPI tiles and interactive Altair charts.

Charts use the portfolio's palette (src.analysis.palette, shared with the report charts: blue,
orange, aqua, validated as distinguishable for colour-blind readers). Every chart is drawn with
show(), which requires a title, every axis is titled with its unit, and every chart has hover
tooltips. Log scales are used wherever the values span orders of magnitude, and are labelled as such.
"""

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from src.analysis.palette import BLUE, MUTED, ORANGE, SERIES

REPO = "https://github.com/bolorbud-gif/business-analytics-portfolio"


# --- Formatting ---------------------------------------------------------------------------------

def fmt_kg(kg) -> str:
    """Kilograms in a readable unit: 850 kg, 12.3 t, 4,965 t."""
    if kg is None or pd.isna(kg):
        return "none recorded"
    if abs(kg) < 1000:
        return f"{kg:,.0f} kg"
    tonnes = kg / 1000
    return f"{tonnes:,.1f} t" if tonnes < 100 else f"{tonnes:,.0f} t"


def fmt_pct(value, signed: bool = False, digits: int = 0) -> str:
    """A percentage: 83%, or +5.7% / -35% when signed."""
    return f"{value:+.{digits}f}%" if signed else f"{value:.{digits}f}%"


def fold(elasticity: float, factor: float = 10) -> str:
    """Business reading of an elasticity: 10x the driver goes with this many times the outcome."""
    times = factor ** elasticity
    return f"{times:.0f}x" if times >= 10 else f"{times:.1f}x"


# --- Layout helpers ---------------------------------------------------------------------------------

def source_banner(meta: dict) -> None:
    """Say which data the dashboard is showing; warn loudly if it is synthetic."""
    if meta.get("source") == "synthetic":
        st.warning("**Synthetic data.** This snapshot was rebuilt from the committed synthetic sample, "
                   "so every number is fake. The text describes the real results.", icon="⚠️")


def kpi_row(items: list[tuple], per_row: int | None = None) -> None:
    """KPI tiles: (label, value, explanation shown on hover[, comparison]). Up to four share a
    row; longer lists wrap three to a row, so labels aren't cut off.

    The optional comparison (for example the baseline) is shown under the value, in grey.
    """
    per_row = per_row or (len(items) if len(items) <= 4 else 3)
    for start in range(0, len(items), per_row):
        chunk = items[start:start + per_row]
        for col, item in zip(st.columns(per_row), chunk):
            label, value, help_text, *comparison = item
            col.metric(label, value, delta=comparison[0] if comparison else None, delta_color="off",
                       delta_arrow="off", help=help_text)


def freshness(text: str) -> None:
    """The data-freshness line under each page title: which years the data cover and when the
    results were built."""
    st.caption(f"🕒 {text}")


def show(chart: alt.Chart, title: str, subtitle: str | None = None) -> None:
    """Render an Altair chart at full width under its title (required: every chart says what it shows)."""
    if not title:
        raise ValueError("every chart needs a title")
    # limit=0: no width limit, or the theme cuts long titles off with an ellipsis
    heading = alt.TitleParams(title, subtitle=subtitle or "", anchor="start", fontSize=15, limit=0,
                              subtitleFontSize=12, subtitleColor=MUTED, offset=10)
    st.altair_chart(chart.properties(title=heading), width="stretch")


# --- Charts -----------------------------------------------------------------------------------------

def share_bars(buyers: pd.DataFrame, top: int) -> alt.Chart:
    """Ranked horizontal bars: each buyer's share of China's export volume."""
    d = buyers.nlargest(top, "share_pct").assign(tonnes=lambda x: x["quantity_kg"] / 1000)
    return alt.Chart(d).mark_bar(color=BLUE, cornerRadiusEnd=3).encode(
        x=alt.X("share_pct:Q", title="Share of China's export volume (%)"),
        y=alt.Y("partner:N", sort="-x", title="Buyer", axis=alt.Axis(labelOverlap=False, labelLimit=180)),
        tooltip=[alt.Tooltip("partner:N", title="Buyer"),
                 alt.Tooltip("share_pct:Q", title="Share (%)", format=".1f"),
                 alt.Tooltip("tonnes:Q", title="Tonnes", format=",.1f"),
                 alt.Tooltip("usd_per_kg:Q", title="USD per kg", format=",.2f")],
    ).properties(height=max(240, 90 + 28 * len(d)))


def price_change_bars(changes: pd.DataFrame) -> alt.Chart:
    """Each buyer's price per kg, end over start, on a log scale centred on 1 (no change), so a
    halving and a doubling are the same length. Falls and rises in two colours."""
    d = changes.assign(direction=np.where(changes["price_change_pct"] < 0, "Price fell", "Price rose"),
                       ratio=changes["price_end"] / changes["price_start"],
                       tonnes=changes["kg_start"] / 1000)
    return alt.Chart(d).mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X("ratio:Q", title="Price per kg, end / start (log scale; 1 = no change)",
                scale=alt.Scale(type="log"), axis=alt.Axis(format="~g")),
        x2=alt.datum(1),
        y=alt.Y("partner:N", sort="x", title="Buyer", axis=alt.Axis(labelOverlap=False, labelLimit=180)),
        color=alt.Color("direction:N", scale=alt.Scale(domain=["Price fell", "Price rose"],
                                                       range=[BLUE, ORANGE]),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("partner:N", title="Buyer"),
                 alt.Tooltip("price_start:Q", title="USD/kg, start", format=",.2f"),
                 alt.Tooltip("price_end:Q", title="USD/kg, end", format=",.2f"),
                 alt.Tooltip("price_change_pct:Q", title="Change (%)", format="+.0f"),
                 alt.Tooltip("tonnes:Q", title="Tonnes at start", format=",.1f")],
    ).properties(height=max(240, 120 + 28 * len(d)))


def trend_lines(trend: pd.DataFrame, series: list[str], labels: list[str], title: str) -> alt.Chart:
    """Up to three lines over time, with points, a legend and tooltips."""
    names = dict(zip(series, labels))
    d = trend.melt("year", series, var_name="series", value_name="value").assign(
        series=lambda x: x["series"].map(names))
    return alt.Chart(d).mark_line(point=alt.OverlayMarkDef(size=60), strokeWidth=2).encode(
        x=alt.X("year:O", title="Year", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("value:Q", title=title),
        color=alt.Color("series:N", scale=alt.Scale(domain=labels, range=SERIES[:len(labels)]),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("series:N", title="Series"), alt.Tooltip("year:O", title="Year"),
                 alt.Tooltip("value:Q", title=title, format=",.1f")],
    ).properties(height=400)


def _size_color(groups: list[str]) -> alt.Color:
    """Colour by size group (smallest first), in the palette's fixed order."""
    return alt.Color("size_group:N", title="Country size", sort=groups,
                     scale=alt.Scale(domain=groups, range=SERIES[:len(groups)]), legend=alt.Legend(orient="top"))


def log_scatter(d: pd.DataFrame, x: str, y: str, xtitle: str, ytitle: str, groups: list[str],
                trend: bool = True) -> alt.Chart:
    """Country-years on log-log axes, coloured by size group, with a power-law trend line
    (a straight line on log axes: its slope is the elasticity). No wheel zoom: it would
    capture page scrolling."""
    d = d[(d[x] > 0) & (d[y] > 0)]
    base = alt.Chart(d).encode(
        x=alt.X(f"{x}:Q", title=f"{xtitle}, log scale", scale=alt.Scale(type="log")),
        y=alt.Y(f"{y}:Q", title=f"{ytitle}, log scale", scale=alt.Scale(type="log"), axis=alt.Axis(format="~s")))
    points = base.mark_circle(size=70, opacity=0.85, stroke="white", strokeWidth=0.8).encode(
        color=_size_color(groups),
        tooltip=[alt.Tooltip("country:N", title="Country"), alt.Tooltip("year:O", title="Year"),
                 alt.Tooltip(f"{x}:Q", title=xtitle, format=",.2f"),
                 alt.Tooltip(f"{y}:Q", title=ytitle, format=",.0f"),
                 alt.Tooltip("size_group:N", title="Size group")])
    layers = [points]
    if trend:
        layers.append(base.transform_regression(x, y, method="pow").mark_line(color=MUTED, strokeDash=[5, 4]))
    return alt.layer(*layers).properties(height=420)


def residual_scatter(d: pd.DataFrame, groups: list[str]) -> alt.Chart:
    """Wind against imports with country size removed from both (log10 residuals)."""
    base = alt.Chart(d).encode(
        x=alt.X("wind_size_adjusted:Q", title="Wind capacity, size removed (log10 residual)"),
        y=alt.Y("imports_size_adjusted:Q", title="Imports from China, size removed (log10 residual)"))
    points = base.mark_circle(size=70, opacity=0.85, stroke="white", strokeWidth=0.8).encode(
        color=_size_color(groups),
        tooltip=[alt.Tooltip("country:N", title="Country"), alt.Tooltip("year:O", title="Year"),
                 alt.Tooltip("wind_size_adjusted:Q", title="Wind, size removed", format="+.2f"),
                 alt.Tooltip("imports_size_adjusted:Q", title="Imports, size removed", format="+.2f")])
    line = base.transform_regression("wind_size_adjusted", "imports_size_adjusted").mark_line(
        color=MUTED, strokeDash=[5, 4])
    return alt.layer(points, line).properties(height=420)


def interval_dots(d: pd.DataFrame, label: str, value: str, low: str, high: str, title: str, ytitle: str,
                  highlight: str | None = None, baseline: str | None = None, zero: bool = False) -> alt.Chart:
    """Estimates with intervals (one row each): baseline grey, highlighted row orange, others blue.
    The colour legend is shown only when there is a baseline or a highlighted row."""
    d = d.assign(kind=np.select([d[label] == baseline, d[label] == highlight], ["Baseline", "Chosen"],
                                "Candidate"))
    domain = ["Baseline", "Candidate", "Chosen"]
    base = alt.Chart(d).encode(y=alt.Y(f"{label}:N", title=ytitle, sort=None,
                                       axis=alt.Axis(labelOverlap=False, labelLimit=240)))
    legend = alt.Legend(title=None, orient="top") if (highlight or baseline) else None
    rule = base.mark_rule(strokeWidth=2).encode(
        x=alt.X(f"{low}:Q", title=title), x2=f"{high}:Q",
        color=alt.Color("kind:N", scale=alt.Scale(domain=domain, range=[MUTED, BLUE, ORANGE]), legend=legend))
    dots = base.mark_circle(size=110, opacity=1).encode(
        x=f"{value}:Q", color=alt.Color("kind:N", scale=alt.Scale(domain=domain, range=[MUTED, BLUE, ORANGE])),
        tooltip=[alt.Tooltip(f"{label}:N", title="Row"), alt.Tooltip(f"{value}:Q", title="Estimate", format=".3f"),
                 alt.Tooltip(f"{low}:Q", title="Low", format=".3f"), alt.Tooltip(f"{high}:Q", title="High", format=".3f")])
    layers = [rule, dots]
    if zero:
        layers.insert(0, alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=MUTED).encode(x="x:Q"))
    # Streamlit fits the whole chart (title, legend and axis included) into the height
    return alt.layer(*layers).properties(height=150 + 44 * len(d))


def predicted_vs_actual(d: pd.DataFrame) -> alt.Chart:
    """Test countries: predicted against actual imports on log axes, with the perfect-prediction
    line and lines where a prediction is 10 times too high or too low."""
    d = d.assign(actual_kg=10 ** d["actual_log10"], predicted_kg=10 ** d["predicted_log10"],
                 off_by=10 ** (d["predicted_log10"] - d["actual_log10"]).abs())
    lo = float(min(d["actual_kg"].min(), d["predicted_kg"].min()) / 3)
    hi = float(max(d["actual_kg"].max(), d["predicted_kg"].max()) * 3)
    grid = np.geomspace(lo, hi, 50)
    guide = pd.concat([pd.DataFrame({"x": grid, "y": grid * f, "line": name})
                       for f, name in [(1, "Perfect prediction"), (10, "10x off"), (0.1, "10x off ")]])
    guide = guide[(guide["y"] >= lo) & (guide["y"] <= hi)]
    scale = alt.Scale(type="log", domain=[lo, hi])
    lines = alt.Chart(guide).mark_line(color=MUTED).encode(
        x=alt.X("x:Q", scale=scale, title="Actual imports from China (kg, log scale)"),
        y=alt.Y("y:Q", scale=scale, title="Predicted imports (kg, log scale)"),
        detail="line:N", strokeDash=alt.condition(alt.datum.line == "Perfect prediction",
                                                  alt.value([1, 0]), alt.value([3, 3])))
    points = alt.Chart(d).mark_circle(size=80, color=BLUE, stroke="white", strokeWidth=0.8).encode(
        x=alt.X("actual_kg:Q", scale=scale), y=alt.Y("predicted_kg:Q", scale=scale),
        tooltip=[alt.Tooltip("country:N", title="Country"), alt.Tooltip("year:O", title="Year"),
                 alt.Tooltip("actual_kg:Q", title="Actual kg", format=",.0f"),
                 alt.Tooltip("predicted_kg:Q", title="Predicted kg", format=",.0f"),
                 alt.Tooltip("off_by:Q", title="Off by (x)", format=",.1f")])
    return alt.layer(lines, points).properties(height=420)


def roc_chart(curves: dict, point: tuple | None = None) -> alt.Chart:
    """ROC curves {name: (fpr, tpr, auc)} against the guessing diagonal, with an optional
    operating point (fpr, tpr, label)."""
    rows = [pd.DataFrame({"fpr": f, "tpr": t, "curve": f"{name} (AUC {a:.2f})"})
            for name, (f, t, a) in curves.items()]
    d = pd.concat(rows)
    names = list(d["curve"].unique())
    lines = alt.Chart(d).mark_line(strokeWidth=2, interpolate="step-after").encode(
        x=alt.X("fpr:Q", title="False-positive rate (smaller buyers flagged)", scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("tpr:Q", title="True-positive rate (major buyers caught)", scale=alt.Scale(domain=[0, 1])),
        color=alt.Color("curve:N", scale=alt.Scale(domain=names, range=[BLUE, ORANGE][:len(names)]),
                        legend=alt.Legend(title=None, orient="bottom", direction="vertical", labelLimit=320)),
        tooltip=[alt.Tooltip("curve:N"), alt.Tooltip("fpr:Q", format=".2f"), alt.Tooltip("tpr:Q", format=".2f")])
    diagonal = alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(
        color=MUTED, strokeDash=[4, 4]).encode(x="x:Q", y="y:Q")
    layers = [diagonal, lines]
    if point:
        layers.append(alt.Chart(pd.DataFrame([{"fpr": point[0], "tpr": point[1], "label": point[2]}]))
                      .mark_point(size=160, filled=True, color="black").encode(
                          x="fpr:Q", y="tpr:Q", tooltip=[alt.Tooltip("label:N", title="Operating point")]))
    return alt.layer(*layers).properties(height=380)


def threshold_lines(table: pd.DataFrame, threshold: float) -> alt.Chart:
    """Precision, recall and F1 across thresholds, with a rule at the threshold in use."""
    d = table.melt("threshold", ["precision", "recall", "F1"], var_name="metric", value_name="value")
    lines = alt.Chart(d).mark_line(strokeWidth=2, point=True).encode(
        x=alt.X("threshold:Q", title="Probability threshold"),
        y=alt.Y("value:Q", title="Score (0 to 1)", scale=alt.Scale(domain=[0, 1])),
        color=alt.Color("metric:N", scale=alt.Scale(domain=["precision", "recall", "F1"],
                                                    range=SERIES),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("metric:N"), alt.Tooltip("threshold:Q", format=".2f"),
                 alt.Tooltip("value:Q", format=".2f")])
    rule = alt.Chart(pd.DataFrame({"t": [threshold]})).mark_rule(color="black", strokeDash=[4, 3]).encode(x="t:Q")
    return alt.layer(lines, rule).properties(height=380)


def forecast_bars(d: pd.DataFrame, top: int) -> alt.Chart:
    """The largest expected buyers, coloured by whether the engine calls them major buyers."""
    d = d.nlargest(top, "predicted_kg").assign(
        tonnes=lambda x: x["predicted_kg"] / 1000,
        call=lambda x: np.where(x["major_buyer_call"], "Major-buyer call", "Smaller buyer"))
    # A log scale has no zero, so bars start from a round number below the smallest value, at least a
    # decade below the largest (otherwise one or two bars would look like almost nothing)
    base = float(10 ** np.floor(np.log10(d["tonnes"].min())))
    if d["tonnes"].max() * 1.5 / base < 10:
        base /= 10
    return alt.Chart(d).mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X("tonnes:Q", title="Expected imports from China (tonnes, log scale)",
                scale=alt.Scale(type="log", domain=[base, float(d["tonnes"].max()) * 1.5]),
                axis=alt.Axis(format="~s")),
        x2=alt.datum(base),
        y=alt.Y("country:N", sort="-x", title="Country", axis=alt.Axis(labelOverlap=False, labelLimit=180)),
        color=alt.Color("call:N", scale=alt.Scale(domain=["Major-buyer call", "Smaller buyer"], range=[BLUE, MUTED]),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("country:N", title="Country"),
                 alt.Tooltip("tonnes:Q", title="Expected tonnes", format=",.1f"),
                 alt.Tooltip("p_major_buyer:Q", title="P(major buyer)", format=".2f")],
    ).properties(height=max(240, 120 + 28 * len(d)))


# --- Notes, empty states and the primary page's chart ------------------------------------------------

def empty(message: str) -> None:
    """Graceful empty state: say why nothing is shown and what to change."""
    st.info(message, icon="🔎")


def notes(sample: str, uncertainty: str, provenance: str, limitation: str) -> None:
    """The 'About these numbers' block at the foot of every page: the sample behind the page, how
    uncertain its numbers are, where they come from and what they can't show."""
    with st.container(border=True):
        st.markdown("**About these numbers**")
        st.markdown(f"- **Sample:** {sample}\n- **Uncertainty:** {uncertainty}\n"
                    f"- **Provenance:** {provenance}\n- **Limitations:** {limitation}")


def multiplier_chart(rows: pd.DataFrame) -> alt.Chart:
    """'10x the driver goes with k x the imports', with 95% intervals, on a log scale with a line
    at 1x (no effect). rows: label, driver (Wind or Size), fold, low, high."""
    order = list(rows["label"])
    base = alt.Chart(rows).encode(y=alt.Y("label:N", sort=order, title="Driver",
                                          axis=alt.Axis(labelOverlap=False, labelLimit=260, labelFontSize=13)))
    scale = alt.Scale(type="log", domain=[float(rows["low"].min()) / 1.5, float(rows["high"].max()) * 1.5])
    color = alt.Color("driver:N", scale=alt.Scale(domain=["Wind", "Size"], range=[BLUE, ORANGE]),
                      legend=alt.Legend(title=None, orient="top"))
    rule = base.mark_rule(strokeWidth=3).encode(
        x=alt.X("low:Q", scale=scale, title="Imports for 10x the driver (times, log scale; 95% interval)",
                axis=alt.Axis(format="~g")), x2="high:Q", color=color)
    dots = base.mark_circle(size=180, opacity=1).encode(
        x=alt.X("fold:Q", scale=scale), color=color,
        tooltip=[alt.Tooltip("label:N", title="Driver"), alt.Tooltip("fold:Q", title="Imports (times)", format=".1f"),
                 alt.Tooltip("low:Q", title="95% low", format=".2f"), alt.Tooltip("high:Q", title="95% high", format=".1f")])
    text = base.transform_calculate(value_label="format(datum.fold, '.1f') + 'x'").mark_text(
        align="left", dx=10, dy=-14, fontSize=13).encode(x=alt.X("fold:Q", scale=scale), text="value_label:N")
    one = alt.Chart(pd.DataFrame({"x": [1.0]})).mark_rule(color=MUTED, strokeDash=[4, 4]).encode(x=alt.X("x:Q", scale=scale))
    # Streamlit fits the whole chart (title, legend and axis included) into the height
    return alt.layer(one, rule, dots, text).properties(height=150 + 56 * len(rows))
