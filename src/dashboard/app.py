"""Rare-earth demand and the wind build-out: the project dashboard (Assignments 3-6).

Launch from the project root:
    uv run streamlit run src/dashboard/app.py                     # committed real-data snapshot
    uv run python scripts/deploy.py run --sample                  # rebuilt synthetic snapshot

The one conclusion it must make clear: country size, not wind, drives demand for Chinese rare-earth
compounds, so demand should be sized from a country's power system, not its wind targets.

Page hierarchy (see docs/deployment.md):
    Start here:   The answer (primary page)
    The case:     1. Why: wind or size?  ->  2. What to do: recommendations
    More detail:  Market evidence · Predictive engine · Data and pipeline
    About:        Limitations and reproducibility

Each page puts its filters in the sidebar, and they apply to the page below them; a page states what
they don't change. Under every title a caption says which years the data cover and when the results
were built.

The app only reads a results snapshot (src.dashboard.data), cached with st.cache_data; it never
touches the database or loads a model: the engine's outputs are computed into the snapshot by
scripts/deploy.py from the saved Assignment 6 artifact. Analysis it does on the fly (refitting the
regressions on a filtered sample, the threshold explorer) calls the Assignment 5 and 6 functions
(src.analysis.statistical, src.modeling.evaluate) and is cached too.
"""

import functools
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from src.dashboard import components as ui
from src.dashboard import data
from src.modeling import evaluate as ev

st.set_page_config(page_title="Rare earths and wind power", page_icon="🌬️", layout="wide")


def snapshot_path() -> Path:
    """`--data PATH` after `--` on the command line, else $DASHBOARD_DATA, else the published snapshot."""
    args = sys.argv[1:]
    if "--data" in args and args.index("--data") + 1 < len(args):
        return Path(args[args.index("--data") + 1])
    return Path(os.environ.get("DASHBOARD_DATA", data.PUBLISHED))


@st.cache_data(show_spinner=False)
def load(path: str, stamp: float) -> dict:  # stamp: reload when the snapshot is rebuilt
    return data.load_snapshot(Path(path))


PATH = snapshot_path()
try:
    SNAP = load(str(PATH), (PATH / "meta.json").stat().st_mtime if (PATH / "meta.json").exists() else 0.0)
except data.SnapshotError as err:
    st.title("Rare earths and wind power")
    st.error(f"**The dashboard has no results to show.** {err}", icon="🚫")
    st.markdown("The app reads a snapshot of results, not the database. To build one from the committed "
                "synthetic sample (no restricted data needed, about 3 minutes), run this from the project root:")
    st.code("uv run python scripts/deploy.py run --sample", language="bash")
    st.markdown("With the real data, run `uv run python scripts/deploy.py build`. If the real database is "
                "missing, that command says how to build it from the source files (see `docs/setup.md`).")
    st.stop()
T, A, E, META = SNAP["tables"], SNAP["summary"]["analysis"], SNAP["summary"]["engine"], SNAP["meta"]


QUESTION = "Does wind power growth drive demand for Chinese rare-earth exports?"
NAV_ACTIVE = False  # set when st.navigation runs; page links need it (tests call pages directly)


def guarded(page):
    """Run a page so that a problem in the snapshot shows as a message on that page, while the
    other pages keep working, instead of taking the whole app down."""
    @functools.wraps(page)
    def run():
        try:
            page()
        except Exception as err:  # noqa: BLE001  Streamlit's own stop/rerun signals aren't Exceptions
            st.error(f"**This page couldn't be drawn from the snapshot** ({type(err).__name__}: {err}). "
                     "The other pages still work. Rebuilding the snapshot usually fixes this: "
                     "`uv run python scripts/deploy.py build --sample` (or `build`, with the real data).", icon="🚫")
            with st.expander("Technical details"):
                st.exception(err)
    return run


def next_step(key: str, label: str) -> None:
    """A link to the next page of the case (shown only when navigation is running)."""
    if NAV_ACTIVE:
        st.page_link(PAGES[key], label=label, icon="➡️")


def span(years) -> str:
    years = sorted(int(y) for y in years)
    return "none" if not years else str(years[0]) if years[0] == years[-1] else f"{years[0]}-{years[-1]}"


def freshness_text() -> str:
    """Which years the data cover and when the results were built (shown under every title)."""
    cov = T["coverage"]
    exports = cov.loc[cov["Export"] > 0, "year"] if "Export" in cov else []
    built, commit = str(META.get("created_utc", ""))[:10], str(META.get("git_commit") or "unknown")[:7]
    return (f"Data as of: China's trade records {span(cov['year'])} (its exports by buyer: {span(exports)}) · "
            f"Ember power data to {A['wind_trend']['last_year']} · results built {built} from the "
            f"{META.get('source')} data (commit {commit})")


def header(title: str) -> None:
    """Page top: synthetic-data warning if needed, the title and the data-freshness caption."""
    ui.source_banner(META)
    st.title(title)
    ui.freshness(freshness_text())


def no_filters(text: str) -> None:
    with st.sidebar:
        st.caption(text)


def provenance(*tables: str, engine: bool = False) -> str:
    """Where a page's numbers come from: snapshot tables, data fingerprint, commit (and the engine artifact)."""
    built, commit = str(META.get("created_utc", ""))[:10], str(META.get("git_commit") or "unknown")[:7]
    text = (f"{', '.join(f'`{t}`' for t in tables)} in the {META.get('source')} snapshot built {built} from "
            f"`{META.get('database')}` (data fingerprint {str(META.get('data_sha256', ''))[:12]}, commit {commit})")
    if engine:
        art = E.get("artifact", {})
        text += (f"; engine artifact trained {str(art.get('created_utc', ''))[:10]} "
                 f"(random_state {art.get('random_state')}, commit {str(art.get('git_commit') or 'unknown')[:7]})")
    return text + "."


def sample_text() -> str:
    s = A["sample"]
    return (f"{s['rows']} country-years from {s['countries']} countries ({span(s['years'])}) with "
            "imports, wind capacity and total generation all recorded; 2023-2024 are the only years with China's exports")


def test_row(task: str, role: str) -> pd.Series:
    t = T["engine_test"]
    return t[(t["task"] == task) & (t["role"] == role)].iloc[0]


def interval(task: str, metric: str) -> pd.Series:
    t = T["engine_intervals"]
    return t[(t["task"] == task) & (t["metric"] == metric)].iloc[0]


# --- Cached analysis (Assignment 5 and 6 functions) -----------------------------------------------

@st.cache_data(show_spinner="Refitting the regressions on the selected country-years...")
def refit(view: pd.DataFrame) -> dict:
    """Models A and B and the size-adjusted residuals on a filtered sample, with the Assignment 5
    functions (imported here: statsmodels is only needed once a filter is changed)."""
    from src.analysis import statistical as stats
    a = stats.fit_log_ols(view, stats.IMPORTS, [stats.WIND])
    b = stats.fit_log_ols(view, stats.IMPORTS, [stats.WIND, stats.SIZE])
    resid = stats.size_adjusted_residuals(view, stats.WIND, stats.IMPORTS, [stats.SIZE])
    models = pd.concat({"A: wind only": stats.tidy_coefficients(a), "B: wind + size": stats.tidy_coefficients(b)},
                       names=["model"]).reset_index()
    return {"models": models, "r2_a": float(a.rsquared), "r2_b": float(b.rsquared),
            "wind_size_adjusted": resid["x_resid"].to_numpy(), "imports_size_adjusted": resid["y_resid"].to_numpy()}


@st.cache_data(show_spinner=False)
def best_threshold(train: pd.DataFrame, ratio: float) -> float:
    """The threshold with the lowest cost on training data (out-of-fold) at this cost ratio."""
    return float(ev.best_threshold(train["major_buyer"], train["p_major_buyer"],
                                   {"false_negative": ratio, "false_positive": 1}))


@st.cache_data(show_spinner=False)
def threshold_view(train: pd.DataFrame, test: pd.DataFrame, ratio: float, threshold: float) -> dict:
    """Metrics, ROC curves and the threshold table for one cost ratio and threshold."""
    costs = {"false_negative": ratio, "false_positive": 1}
    metrics = pd.DataFrame([ev.classification_metrics(d["major_buyer"], d["p_major_buyer"], threshold, costs)
                            for d in (train, test)], index=["Training (out-of-fold)", "Test countries"])
    return {"metrics": metrics[["precision", "recall", "F1", "cost", "flagged", "positives", "n"]].round(2),
            "point": ev.operating_point(test["major_buyer"], test["p_major_buyer"], threshold),
            "train_roc": ev.roc_points(train["major_buyer"], train["p_major_buyer"]),
            "test_roc": ev.roc_points(test["major_buyer"], test["p_major_buyer"]),
            "table": ev.threshold_table(train["major_buyer"], train["p_major_buyer"],
                                        thresholds=tuple(np.round(np.arange(0.05, 0.96, 0.05), 2)), costs=costs)}


# --- Pages ---------------------------------------------------------------------------------------

def answer_page():
    header(QUESTION)
    no_filters("This page uses the full sample, so it has no filters. The pages of the case below let you "
               "filter the evidence.")
    a, b, ci = A["model_a"], A["model_b"], A["model_b"]["wind_ci"]
    m = T["models"].set_index(["model", "term"])
    size = m.loc[("B: wind + size", "log_total_generation_twh")]
    conc, clf_m = A["concentration_latest"], test_row("classification", "model")
    with st.container(border=True):
        st.markdown("### No. Country size, not wind, drives demand for Chinese rare-earth compounds.")
        ui.kpi_row([
            ("Imports for 10x wind (same size)", ui.fold(b["wind"]),
             "Model B: how many times the imports go with 10 times the wind capacity, at the same total "
             "generation. 1x would mean no effect.", f"95% CI {ui.fold(ci[0])} to {ui.fold(ci[1])}: includes 1x"),
            ("Imports for 10x size (same wind)", ui.fold(b["size"]),
             "Model B: how many times the imports go with 10 times the total generation, at the same wind capacity.",
             f"95% CI {ui.fold(size['ci_low'])} to {ui.fold(size['ci_high'])}"),
            (f"Top-5 buyers' share ({int(conc['year'])})", f"{conc['top5_share']:.0%}",
             "Share of China's export volume bought by its five largest buyers.", f"of {int(conc['countries'])} buyers"),
            ("Major-buyer ranking (AUC)", f"{clf_m['AUC']:.2f}",
             "The predictive engine on countries it never saw: 1 ranks every major buyer first, 0.5 is guessing.",
             "baseline 0.50"),
        ])
        st.markdown(
            f"Countries with more wind do import more: 10x the wind capacity goes with **{ui.fold(a['wind'])}** the "
            f"imports. But that is mostly because they are bigger economies. **At the same size**, 10x the wind goes "
            f"with only **{ui.fold(b['wind'])}** the imports, and the 95% interval ({ui.fold(ci[0])} to "
            f"{ui.fold(ci[1])}) includes no effect, while 10x the size goes with **{ui.fold(b['size'])}** the imports.")
        st.markdown("**The decision it supports:** size a country's demand for rare-earth compounds, and rank "
                    "markets, by the scale of its power system, not by its wind targets. Treat wind's own effect "
                    "as unproven, not as zero.")
    st.subheader("The evidence in one chart")
    rows = pd.DataFrame([
        ("Wind, alone (Model A)", "Wind", m.loc[("A: wind only", "log_wind_capacity_gw")]),
        ("Wind, at the same size (Model B)", "Wind", m.loc[("B: wind + size", "log_wind_capacity_gw")]),
        ("Size, at the same wind (Model B)", "Size", size),
    ], columns=["label", "driver", "row"])
    rows = rows.assign(fold=[10 ** r["coef"] for r in rows["row"]], low=[10 ** r["ci_low"] for r in rows["row"]],
                       high=[10 ** r["ci_high"] for r in rows["row"]]).drop(columns="row")
    ui.show(ui.multiplier_chart(rows), "At the same size, wind's link to imports can't be told apart from none",
            f"Log-log OLS with year effects, {b['n']} country-years; 95% intervals clustered by country")
    st.caption("How many times the imports go with 10x the driver, with its 95% interval. An interval that "
               "crosses the dashed 1x line can't be told apart from no effect.")
    reg_m, reg_b = test_row("regression", "model"), test_row("regression", "baseline")
    st.subheader("What it means")
    st.markdown(
        "- **Forecast demand from size.** Total electricity generation is the best single guide to how much a "
        "country buys.\n"
        "- **Don't dismiss wind.** Its effect at the same size is uncertain, not shown to be zero; more years and "
        "magnet trade (HS 850511) are needed to settle it.\n"
        f"- **The predictive engine puts this to work.** From last year's power data alone it estimates a "
        f"country's imports, typically within a factor of {10 ** reg_m['MAE']:.0f} (a naive guess: "
        f"{10 ** reg_b['MAE']:.0f}), and ranks major buyers (AUC {clf_m['AUC']:.2f}), then turns that into an "
        "action for each country.")
    st.markdown("**Follow the case**")
    next_step("wind", "Step 1 · Why: wind or size? See the evidence")
    next_step("actions", "Step 2 · What to do: recommendations by country")
    ui.notes(sample=sample_text() + ".",
             uncertainty="95% confidence intervals from log-log OLS with year effects; standard errors clustered by "
                         "country, because each country appears in both years. The wind interval at the same size "
                         "crosses 1x.",
             provenance=provenance("models", "country_year", "concentration", "engine_test"),
             limitation="associations, not causes; two years of exports; rare-earth compounds (HS 284690) only. "
                        "See *Limitations and reproducibility*.")


def data_page():
    header("Data and pipeline (Assignment 4)")
    d, groups = T["country_year"], A["size_groups"]
    coverage = T["coverage"]
    all_years = sorted(set(coverage["year"]) | set(d["year"]))
    with st.sidebar:
        st.header("Filters")
        years = st.multiselect("Years", all_years, default=all_years)
        sizes = st.multiselect("Country size (total generation)", groups, default=groups)
        st.caption("Years filter the trade coverage and the analysis sample; size filters the sample. The "
                   "database tables and quality checks always describe the whole database.")
    st.markdown(
        "Two public sources, combined in a SQLite database normalised to third normal form:\n"
        "- **Trade:** China's trade in rare-earth compounds (HS 284690) by partner, from the World Bank's WITS.\n"
        "- **Power:** yearly generation, capacity and emissions by country and source, from Ember.\n\n"
        "The raw files are not in the repository (third-party terms); this app reads a snapshot of results "
        "derived from them (see *Limitations and reproducibility*).")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Trade rows by year and direction")
        cov = coverage[coverage["year"].isin(years)]
        if cov.empty:
            ui.empty("No years selected. Choose at least one year in the sidebar.")
        else:
            st.dataframe(cov, hide_index=True, width="stretch",
                         column_config={"year": st.column_config.NumberColumn("Year", format="%d")})
        st.caption("Each year has only one direction: China's exports (the partners' imports) exist "
                   "for 2023-2024 only, so imports can be compared across two years.")
    with c2:
        st.subheader("Database tables")
        st.dataframe(T["row_counts"], hide_index=True, width="stretch")
        st.metric("Quality checks passed", f"{A['checks_passed']} of {A['checks_total']}")
    with st.expander("All quality checks"):
        st.dataframe(T["quality_checks"], hide_index=True, width="stretch")
    st.subheader("The analysis sample")
    s = A["sample"]
    st.markdown(f"**{s['rows']} country-years** from **{s['countries']} countries** with imports, wind "
                f"capacity and total generation all recorded, split into size terciles by total generation.")
    view = d[d["year"].isin(years) & d["size_group"].isin(sizes)].drop(
        columns=["wind_size_adjusted", "imports_size_adjusted"])
    if view.empty:
        ui.empty(f"No rows match these filters: the sample covers {span(d['year'])} only. Choose at least one "
                 "of those years and one size group in the sidebar.")
    else:
        st.caption(f"{len(view)} of {len(d)} country-years shown.")
        sample_table(view)
    ui.notes(sample=sample_text() + f"; {A['checks_passed']} of {A['checks_total']} quality checks pass.",
             uncertainty="none from sampling: these are the recorded values. Trade quantities are as reported by "
                         "China's customs (via WITS).",
             provenance=provenance("country_year", "coverage", "row_counts", "quality_checks"),
             limitation="countries without Ember power data (for example Peru) are outside the sample; each year "
                        "has only one trade direction.")


def sample_table(view: pd.DataFrame) -> None:
    st.dataframe(view, hide_index=True, width="stretch", column_config={
        "year": st.column_config.NumberColumn("Year", format="%d"),
        "imports_from_china_kg": st.column_config.NumberColumn("Imports from China (kg)", format="%,.0f"),
        "wind_capacity_gw": st.column_config.NumberColumn("Wind capacity (GW)", format="%.2f"),
        "wind_generation_twh": st.column_config.NumberColumn("Wind generation (TWh)", format="%.2f"),
        "total_generation_twh": st.column_config.NumberColumn("Total generation (TWh)", format="%.1f"),
        "wind_share_pct": st.column_config.NumberColumn("Wind share (%)", format="%.1f")})
    st.download_button("Download these rows (CSV)", view.to_csv(index=False), "analysis_sample.csv", "text/csv")


def market_page():
    header("Market evidence (Assignment 5)")
    buyers, price = T["buyers"], A["price_decomposition"]
    start, end = int(price.get("start", data.START)), int(price.get("end", data.END))
    with st.sidebar:
        st.header("Filters")
        year = st.selectbox("Year", sorted(buyers["year"].unique(), reverse=True),
                            help="Who buys: the shares and concentration for this year")
        top = st.slider("Largest buyers shown", 5, 30, 10, help="In both bar charts")
        st.caption(f"Prices always compare {start} with {end}, the two years with export data; the wind "
                   "build-out covers every year.")
    tab1, tab2, tab3 = st.tabs(["Who buys", "Prices", "Wind build-out"])
    with tab1:
        conc_table = T["concentration"].set_index("year")
        year_buyers = buyers[buyers["year"] == year]
        if year not in conc_table.index or year_buyers.empty:
            ui.empty(f"No buyers are recorded for {year} in this snapshot. Choose another year in the sidebar.")
        else:
            conc = conc_table.loc[year]
            ui.kpi_row([("Largest buyer's share", f"{conc['top1_share']:.0%}", "Share of China's export volume"),
                        ("Top-5 share", f"{conc['top5_share']:.0%}", "Five largest buyers together"),
                        ("HHI", f"{conc['hhi']:,.0f}", "Herfindahl-Hirschman index (0-10,000): above 1,800 is "
                                                       "highly concentrated; here it measures concentration of demand"),
                        ("Buyers", f"{conc['countries']:,.0f}", "Countries buying from China that year")])
            ui.show(ui.share_bars(year_buyers, top), f"Who buys China's rare-earth compounds, {year}",
                    f"The {min(top, len(year_buyers))} largest of {len(year_buyers)} buyers, by share of export volume (kg)")
            st.caption("A handful of buyers take most of China's exports, so an export restriction or price "
                       "change would hit them first.")
    with tab2:
        yearly = T["trade_yearly"]
        exports = yearly[yearly["trade_flow"] == "Export"]
        change = A["export_change_pct"]
        ui.kpi_row([
            ("Volume", ui.fmt_pct(change["quantity_kg"], True, 1), f"China's export kg, {start} to {end}"),
            ("Value", ui.fmt_pct(change["value_kusd"], True, 1), "Export value in USD"),
            ("Average price", ui.fmt_pct(price["average_change_pct"], True), "USD per kg over all exports"),
            ("Price at fixed volumes", ui.fmt_pct(price["price_effect_pct"], True),
             "Each buyer's start-year volume held fixed: the pure price change"),
            ("Mix effect", ui.fmt_pct(price["mix_effect_pct"], True), "Change due to who bought, not what they paid"),
        ])
        st.dataframe(exports.drop(columns=["trade_flow"]), hide_index=True, width="stretch", column_config={
            "year": st.column_config.NumberColumn("Year", format="%d"),
            "partners": st.column_config.NumberColumn("Buyers"),
            "quantity_kg": st.column_config.NumberColumn("Exports (kg)", format="%,.0f"),
            "value_kusd": st.column_config.NumberColumn("Value (thousand USD)", format="%,.0f"),
            "unit_value_usd_per_kg": st.column_config.NumberColumn("USD per kg", format="%.2f")})
        changes = T["price_changes"]
        sel = changes.nlargest(top, "kg_start")
        if sel.empty:
            ui.empty(f"No buyer bought in both {start} and {end} in this snapshot.")
        else:
            ui.show(ui.price_change_bars(sel), f"Price per kg paid by the {len(sel)} largest buyers, {end} against {start}",
                    f"Largest by {start} volume; prices fell for buyers holding {price['volume_share_price_fell']:.0%} "
                    "of all the volume")
    with tab3:
        trend, info = T["wind_trend"], A["wind_trend"]
        first, last = trend.iloc[0], trend.iloc[-1]
        total_growth = (last[info["series"]].sum() / first[info["series"]].sum() - 1) * 100
        focus_growth = (last[info["series"][0]] / first[info["series"][0]] - 1) * 100
        ui.kpi_row([(f"Wind capacity, {info['first_year']}-{info['last_year']}", ui.fmt_pct(total_growth, True),
                     f"All {info['countries']} countries with data for every year"),
                    (f"{info['labels'][0]} alone", ui.fmt_pct(focus_growth, True), "Its own installed capacity")])
        ui.show(ui.trend_lines(trend, info["series"], info["labels"], "Installed wind capacity (GW)"),
                f"Installed wind capacity, {info['first_year']}-{info['last_year']}",
                f"The {info['countries']} countries with Ember data in every year")
    ui.notes(sample=f"China's export records for {start}-{end} ({price['buyers']} buyers in both years "
                    f"for the price index); wind capacity for the {A['wind_trend']['countries']} countries with "
                    "Ember data in every year.",
             uncertainty="the fixed-volume price index and the shares are computed on all of China's recorded "
                         "exports, not estimated from a sample; the typical (median) buyer's price change is "
                         "uncertain (H4).",
             provenance=provenance("buyers", "concentration", "trade_yearly", "price_changes", "wind_trend"),
             limitation="HS 284690 mixes grades, so a lower price per kg can mean a cheaper grade, not a discount.")


AXES = {"wind_capacity_gw": "Wind capacity (GW)", "wind_generation_twh": "Wind generation (TWh)",
        "total_generation_twh": "Total generation (TWh)", "wind_share_pct": "Wind share of generation (%)"}
MIN_ROWS, MIN_COUNTRIES = 12, 6  # below this, the regressions aren't refitted


def wind_page():
    header("Step 1 · Why: wind or size? (Assignment 5)")
    d, groups = T["country_year"], A["size_groups"]
    all_years = sorted(d["year"].unique())
    with st.sidebar:
        st.header("Filters")
        years = st.multiselect("Years", all_years, default=all_years)
        sizes = st.multiselect("Country size (total generation)", groups, default=groups)
        x = st.selectbox("Compare imports with", list(AXES), format_func=AXES.get)
        adjust = st.toggle("Remove country size", help="Plot what is left of wind and imports after a linear fit "
                                                      "on total generation (log10), i.e. at the same country size")
        st.caption("Filters apply to the chart and the regressions (refitted on the rows you keep). The "
                   "hypothesis tests always use their pre-specified full samples.")
    st.markdown("**Takeaway:** large countries have more wind *and* buy more rare earths. Hold size fixed "
                "and the wind link mostly disappears.")
    view = d[d["year"].isin(years) & d["size_group"].isin(sizes)]
    filtered = len(view) < len(d)
    fit = None
    if filtered and len(view) >= MIN_ROWS and view["country"].nunique() >= MIN_COUNTRIES:
        fit = refit(view)
        view = view.assign(wind_size_adjusted=fit["wind_size_adjusted"],
                           imports_size_adjusted=fit["imports_size_adjusted"])
    scope = f"{len(view)} of {len(d)} country-years" if filtered else f"all {len(d)} country-years"
    if view.empty:
        ui.empty("No country-years match these filters. Choose at least one year and one size group in the sidebar.")
    elif adjust and filtered and fit is None:
        ui.empty(f"Too few country-years ({len(view)}) to remove size reliably: keep at least {MIN_ROWS} from "
                 f"{MIN_COUNTRIES} countries.")
    elif adjust:
        r = float(np.corrcoef(view["wind_size_adjusted"], view["imports_size_adjusted"])[0, 1])
        ui.show(ui.residual_scatter(view, groups), "Imports against wind capacity, with country size removed from both",
                f"{scope}; log10 residuals after a fit on total generation")
        st.caption(f"Partial correlation, size removed: r = {r:.2f}. Big and small countries now overlap: "
                   "once size is accounted for, wind adds little.")
    else:
        ok = view[(view[x] > 0) & (view["imports_from_china_kg"] > 0)]
        if len(ok) < 3:
            ui.empty(f"Too few country-years with a positive {AXES[x].lower()} to plot on a log scale.")
        else:
            ui.show(ui.log_scatter(view, x, "imports_from_china_kg", AXES[x], "Imports from China (kg)", groups),
                    f"Imports from China against {AXES[x].split(' (')[0].lower()}, by country-year",
                    f"{scope}; dashed line: power-law fit")
            rho = ok[x].rank().corr(ok["imports_from_china_kg"].rank())
            st.caption(f"Spearman rank correlation: {rho:.2f} ({len(ok)} country-years). The dashed line is the "
                       "power-law fit; colours show that the large countries sit at the top right.")
    st.subheader("Hypothesis tests (full samples)")
    h = T["hypotheses"]
    st.dataframe(h[["hypothesis", "magnitude", "effect_measure", "effect_size", "effect", "test", "n",
                    "p_holm", "result"]], hide_index=True, width="stretch",
                 column_config={"effect_size": st.column_config.NumberColumn("effect size", format="%.2f"),
                                "p_holm": st.column_config.NumberColumn("Holm p", format="%.3f")})
    st.caption("Each test leads with its business magnitude and effect size; p-values are Holm-corrected "
               "for testing five hypotheses. 'Not supported' isn't 'no effect': H2's interval still allows "
               "an effect large enough to matter, and the price fall (H4) was real for the largest buyers.")
    with st.expander("The same hypotheses as regressions, with residual checks"):
        st.dataframe(T["regression_check"][["hypothesis", "magnitude", "test", "p_holm", "residual_shapiro_p",
                                            "result", "main_test_result"]], hide_index=True, width="stretch")
        st.caption("H4's regression is the paired t-test, and its residuals aren't normal (low Shapiro p), so "
                   "the sign test stays the right test.")
    st.subheader("How much does wind add once size is known?")
    if filtered and fit is None:
        ui.empty(f"The regressions need at least {MIN_ROWS} country-years from {MIN_COUNTRIES} countries; these "
                 f"filters keep {len(view)}. Widen them in the sidebar.")
    else:
        m = fit["models"] if fit else T["models"]
        r2_a, r2_b = (fit["r2_a"], fit["r2_b"]) if fit else (A["model_a"]["r2"], A["model_b"]["r2"])
        m = m[m["term"].str.startswith("log_")].assign(
            row=lambda x: x["model"] + " · " + x["term"].map({"log_wind_capacity_gw": "wind",
                                                              "log_total_generation_twh": "size"}))
        ui.show(ui.interval_dots(m, "row", "coef", "ci_low", "ci_high",
                                 "Elasticity: % more imports for 1% more of the driver (95% CI)", "Model · driver",
                                 zero=True),
                "Elasticity of imports, with and without country size in the model",
                f"Log-log OLS with year effects on {scope}; 0 = no link")
        wind = m[m["term"] == "log_wind_capacity_gw"].set_index("model")["coef"]
        shrinks = abs(wind["B: wind + size"]) < abs(wind["A: wind only"])
        st.caption(f"Model A (wind only) R² = {r2_a:.2f}; Model B (wind + size) R² = {r2_b:.2f}. Adding size "
                   f"{'shrinks the wind elasticity towards zero' if shrinks else 'does not shrink the wind elasticity here'} "
                   f"({wind['A: wind only']:.2f} to {wind['B: wind + size']:.2f}).")
    with st.expander("Robustness: missing years and zero imports"):
        rob = T["robustness"].assign(term=lambda x: x["term"].str.replace("log_", ""))
        st.dataframe(rob, hide_index=True, width="stretch")
        st.caption("Full sample. The conclusion holds without the partners that bought in only one year, and in a "
                   "Poisson (PPML) model that counts their missing years as zero.")
    ui.notes(sample=sample_text() + f" ({scope} with these filters); H3 uses the 49 countries with import growth "
                    "in 2024, H4 the 52 buyers seen in both years.",
             uncertainty="each test reports an effect size and a Holm-corrected p-value; intervals are 95%, "
                         "clustered by country. Assumptions were checked (Shapiro-Wilk, Levene, regression "
                         "diagnostics) and a test that doesn't need a failed assumption was used.",
             provenance=provenance("country_year", "hypotheses", "regression_check", "models", "robustness")
             + (" Regressions refitted here on the filtered rows with src.analysis.statistical." if fit else ""),
             limitation="two years, so growth (H3) rests on one year; associations, not causes.")
    next_step("actions", "Step 2 · What to do: recommendations by country")


def engine_page():
    header("Predictive engine (Assignment 6)")
    train, test = T["train_scores"], T["test_predictions"]
    with st.sidebar:
        st.header("Threshold explorer")
        ratio = st.select_slider("A missed major buyer costs this many false alarms",
                                 options=[0.25, 0.5, 1, 2, 3, 5, 10], value=E["costs"]["false_negative"])
        best = best_threshold(train, ratio)
        threshold = st.slider("Threshold", 0.05, 0.95, best, 0.05,
                              help=f"Best for this cost ratio on training data: {best:.2f}")
        st.caption("These change the classification tab. The test scores at the top stay at the engine's own "
                   f"threshold ({E['threshold']:.2f}).")
    st.markdown(
        f"Two supervised tasks on the same rows, using only **last year's power data** (published before the "
        f"trade figures): **how much** a country imports (regression on log10 kg) and **whether it is a major "
        f"buyer** ({E['major_buyer_kg']:,} kg or more a year; classification). "
        f"{E['test_countries']} countries ({E['test_rows']} rows) were held out as a test set and used once; "
        f"models were chosen by nested cross-validation grouped by country, always against a dummy baseline.")
    cv = T["engine_cv"]
    c1, c2 = st.columns(2)
    for col, task, metric, title, chart_title, better in [
            (c1, "regression", "MAE", "MAE (log10 kg), mean ± 1 SD", "How much? Error by model", "lower"),
            (c2, "classification", "AUC", "ROC AUC (0.5 to 1), mean ± 1 SD", "Major buyer? Ranking by model",
             "higher")]:
        t = cv[cv["task"] == task].assign(low=lambda x: x[metric] - x[f"{metric}_sd"],
                                          high=lambda x: x[metric] + x[f"{metric}_sd"])
        with col:
            ui.show(ui.interval_dots(t, "model", metric, "low", "high", title, "Model",
                                     highlight=E["models"][task], baseline=t["model"].iloc[0]),
                    chart_title, f"Nested cross-validation grouped by country; {better} is better")
    st.subheader("Held-out test countries")
    reg_m, reg_b = test_row("regression", "model"), test_row("regression", "baseline")
    clf_m, clf_b = test_row("classification", "model"), test_row("classification", "baseline")
    mae, auc, cost = interval("regression", "MAE"), interval("classification", "AUC"), interval("classification", "cost")
    ui.kpi_row([
        ("MAE (log10 kg)", f"{reg_m['MAE']:.2f}", f"Baseline {reg_b['MAE']:.2f}; 95% CI {mae['ci_low']:.2f}-{mae['ci_high']:.2f}"),
        ("R²", f"{reg_m['R2']:.2f}", f"Baseline {reg_b['R2']:.2f}"),
        ("ROC AUC", f"{clf_m['AUC']:.2f}", f"Baseline 0.50; 95% CI {auc['ci_low']:.2f}-{auc['ci_high']:.2f}"),
        ("Cost per country", f"{clf_m['cost']:.2f}", f"Flag-everyone baseline {clf_b['cost']:.2f}; "
                                                     f"95% CI {cost['ci_low']:.2f}-{cost['ci_high']:.2f}"),
        ("Recall / precision", f"{clf_m['recall']:.0%} / {clf_m['precision']:.0%}",
         f"At threshold {E['threshold']:.2f}"),
    ])
    tab1, tab2 = st.tabs(["How much? (regression)", "Major buyer? (classification)"])
    with tab1:
        ui.show(ui.predicted_vs_actual(test), "Predicted against actual imports, held-out test countries",
                f"{E['models']['regression']}; dotted lines: 10x too high or too low")
        st.caption(f"{E['models']['regression']}: a typical estimate is off by a factor of "
                   f"{10 ** reg_m['MAE']:.0f}, against {10 ** reg_b['MAE']:.0f} for the baseline. Good enough to "
                   "place a market in its order of magnitude, not to forecast a contract.")
    with tab2:
        view = threshold_view(train, test, ratio, threshold)
        st.markdown(f"**{E['models']['classification']}.** The threshold turns a probability into a call. "
                    "It is chosen on training data (out-of-fold) to minimise the business cost of errors; "
                    "change the cost ratio in the sidebar to see how the choice moves.")
        st.dataframe(view["metrics"], width="stretch")
        point, tr_roc, te_roc = view["point"], view["train_roc"], view["test_roc"]
        c3, c4 = st.columns(2)
        with c3:
            ui.show(ui.roc_chart({"Training, out of fold": (tr_roc["fpr"], tr_roc["tpr"], tr_roc["AUC"]),
                                  "Test countries": (te_roc["fpr"], te_roc["tpr"], te_roc["AUC"])},
                                 (point["fpr"], point["tpr"], f"threshold {threshold:.2f} (test)")),
                    "ROC curve: major buyers caught against false alarms", f"Black dot: threshold {threshold:.2f}")
        with c4:
            ui.show(ui.threshold_lines(view["table"], threshold), "Precision, recall and F1 by threshold",
                    f"Training data, out of fold; dashed line: {threshold:.2f}")
        st.caption(f"The engine uses {E['threshold']:.2f}, chosen at a "
                   f"{E['costs']['false_negative']}:{E['costs']['false_positive']} cost ratio. "
                   "The test row is shown for information; choosing the threshold on it would be leakage.")
    ui.notes(sample=f"{E['rows']} country-years: {E['train_rows']} for training ({E['train_countries']} countries) "
                    f"and {E['test_rows']} held out ({E['test_countries']} countries), split by country.",
             uncertainty="cross-validation scores are means with their standard deviation over 5 folds; test "
                         "scores carry 95% bootstrap intervals that resample whole countries.",
             provenance=provenance("engine_cv", "engine_test", "engine_intervals", "test_predictions",
                                   "train_scores", engine=True),
             limitation=f"only {E['test_rows']} test rows, so test scores are uncertain; the 10-tonne line and the "
                        "cost ratio are business judgements (config/model_params.yaml).")


ACTION_ORDER = ["Approach", "Grow", "Verify", "Keep", "Low priority"]


def actions_page():
    header("Step 2 · What to do: recommendations")
    acts, rules = T["actions"], E["actions_rules"]
    with st.sidebar:
        st.header("Filters")
        chosen = st.multiselect("Actions in the table", ACTION_ORDER, default=["Approach", "Grow", "Verify"])
        search = st.text_input("Find a country", help="Filters the counts, the table and the forecast")
        top = st.slider("Countries in the forecast chart", 5, 30, 12)

    def matching(frame: pd.DataFrame) -> pd.DataFrame:
        return frame[frame["country"].str.contains(search, case=False, na=False, regex=False)] if search else frame

    st.markdown("**Takeaway:** the engine expects each country's imports from its power sector; the gap between "
                "that and what it actually buys says where to act.")
    st.markdown(
        f"Each country's {E['years']['actions']} imports compared with what its power sector predicts, turned "
        "into an action for a rare-earth supplier's market-development team:\n"
        "- **Approach:** no recorded imports, but a major-buyer profile: a possible new market.\n"
        f"- **Grow:** a major-buyer profile, but buying under {E['major_buyer_kg']:,} kg or under "
        f"{rules['far_below']:.0%} of the expected amount: under-served.\n"
        f"- **Verify:** buying over {rules['far_above']:.0f}x what its power sector explains (industry or "
        "re-exports): plan on its purchase history, not the model.\n"
        "- **Keep:** an established major buyer in line with expectations. **Low priority:** a small market.")
    found = matching(acts)
    counts = found["action"].value_counts()
    ui.kpi_row([(a, f"{counts.get(a, 0)}", acts.loc[acts['action'] == a, 'reason'].iloc[0]
                 if (acts["action"] == a).any() else "") for a in ACTION_ORDER])
    view = found[found["action"].isin(chosen)]
    if view.empty:
        ui.empty("No countries match. Choose at least one action in the sidebar, or change the search.")
    else:
        st.caption(f"{len(view)} of {len(acts)} countries shown.")
        actions_table(view)
    st.caption("The saved engine was refitted on all the data, so these comparisons are in-sample: read them "
               "as who departs from the pattern, not as test scores.")
    st.subheader(f"{E['years']['forecast']} forecast")
    power_year = E["years"]["forecast"] - E["feature_lag_years"]
    st.markdown(f"No {E['years']['forecast']} trade data exist yet, so this is a pure forecast from "
                f"{power_year} power data.")
    forecast = matching(T["forecast"])
    if T["forecast"].empty:
        ui.empty(f"No countries have {power_year} power data in this snapshot.")
    elif forecast.empty:
        ui.empty(f"No forecast for a country matching \"{search}\". Change the search in the sidebar.")
    else:
        shown = min(top, len(forecast))
        which = (f"{shown} {'country' if shown == 1 else 'countries'} matching \"{search}\"" if search
                 else f"the {shown} largest buyers")
        ui.show(ui.forecast_bars(forecast, top), f"Expected {E['years']['forecast']} imports: {which}",
                f"From {power_year} power data; blue: the engine calls it a major buyer "
                f"({E['major_buyer_kg']:,} kg or more)")
    ui.notes(sample=f"the {len(acts)} countries with power data in {E['years']['actions']} (buyers and non-buyers).",
             uncertainty="expectations are point estimates from a model typically off by a factor of "
                         f"{10 ** test_row('regression', 'model')['MAE']:.0f} on unseen countries (see *Predictive "
                         "engine*); treat actions as prompts for a closer look.",
             provenance=provenance("actions", "forecast", engine=True),
             limitation="in-sample (the saved engine was refitted on all the data); the action cut-offs "
                        f"({rules['far_below']:.0%}, {rules['far_above']:.0f}x, {E['major_buyer_kg']:,} kg) are judgement calls.")
    next_step("limits", "Before acting: limitations and reproducibility")


def actions_table(view: pd.DataFrame) -> None:
    st.dataframe(view.drop(columns=["year"]), hide_index=True, width="stretch", column_config={
        "imports_from_china_kg": st.column_config.NumberColumn("Actual kg", format="%,.0f"),
        "predicted_kg": st.column_config.NumberColumn("Expected kg", format="%,.0f"),
        "ratio_actual_to_expected": st.column_config.NumberColumn("Actual / expected", format="%.2f"),
        "p_major_buyer": st.column_config.ProgressColumn("P(major buyer)", min_value=0, max_value=1, format="%.2f"),
        "major_buyer_call": st.column_config.CheckboxColumn("Major-buyer call")})


def limits_page():
    header("Limitations and reproducibility")
    no_filters("This page has no filters.")
    st.subheader("Limitations")
    st.markdown(
        "- **Short window.** China's exports exist for 2023-2024 only, so growth is measured for one year and "
        "time-series models (ARIMA, country fixed effects) aren't possible yet.\n"
        "- **One product code.** Rare-earth compounds (HS 284690) only. Much of the wind industry's demand "
        "arrives as finished permanent magnets (HS 850511), which aren't in the data.\n"
        "- **Associations, not causes.** Large power systems go with large imports; that doesn't mean "
        "building power capacity creates rare-earth demand.\n"
        f"- **Small test set.** {E['test_rows']} test rows, so test scores are uncertain (the intervals on the engine "
        "page); cross-validation with its standard deviations is the steadier guide.\n"
        "- **Judgement calls.** The 10-tonne major-buyer line, the cost ratio, the action cut-offs and the "
        "materiality thresholds are business assumptions, kept in `config/model_params.yaml`.\n"
        "- **Grades.** A lower price per kg can mean a cheaper grade, not a discount.\n"
        "- **In-sample actions.** Recommendations come from a model refitted on all the data.")
    st.subheader("Reproduce what this dashboard shows")
    st.markdown(
        "From a clean clone (see `docs/deployment.md`):\n"
        "```bash\n"
        "uv sync                                         # exact versions from uv.lock\n"
        "uv run python scripts/deploy.py run             # this dashboard, on the committed snapshot\n"
        "uv run python scripts/deploy.py run --sample    # rebuild everything from the synthetic data, then launch\n"
        "uv run python scripts/deploy.py check           # with the real data: rebuild and compare with the snapshot\n"
        "```")
    st.subheader("Provenance of what you see")
    art = E.get("artifact", {})
    meta = {"Data": META.get("source"), "Database": META.get("database"), "Snapshot built (UTC)": META.get("created_utc"),
            "Snapshot git commit": META.get("git_commit"), "Uncommitted changes at build": META.get("uncommitted_changes"),
            "Data fingerprint (SHA-256)": META.get("data_sha256"),
            "Engine artifact trained (UTC)": art.get("created_utc"), "Engine git commit": art.get("git_commit"),
            "Engine training-data fingerprint": art.get("data_sha256"), "random_state": art.get("random_state"),
            "Snapshot folder": data.relative_to_root(PATH)}
    st.dataframe(pd.DataFrame(meta.items(), columns=["", "value"]).astype(str), hide_index=True,
                 width="stretch")
    st.subheader("How the project fits together")
    st.dataframe(pd.DataFrame([
        ("3", "Proposal", "The question, hypotheses H1-H5 and the plan", "docs/proposal.pdf"),
        ("4", "Data pipeline", f"WITS trade + Ember power data into a 3NF SQLite database; "
                              f"{A['checks_passed']}/{A['checks_total']} quality checks pass", "docs/quality_report.md"),
        ("5", "Statistical analysis", "Concentration, prices, wind vs imports; five hypothesis tests with "
                                      "assumption checks, effect sizes and Holm correction",
         "docs/statistical_analysis_report.md"),
        ("6", "Analytics engine", "Predicts imports and major buyers from last year's power data; "
                                  "baseline, nested CV, leakage checks, cost-based threshold",
         "notebooks/03_modeling_experiments.ipynb"),
        ("7", "Dashboard", "This app: a results snapshot rebuilt and checked by scripts/deploy.py",
         "docs/deployment.md"),
    ], columns=["Assignment", "Stage", "What it does", "Details"]).assign(
        Details=lambda d: ui.REPO + "/blob/main/" + d["Details"]),
        hide_index=True, width="stretch",
        column_config={"Details": st.column_config.LinkColumn("Details", display_text="Open on GitHub")})


def sidebar_info():
    """The app-wide block under the page's filters: what the dashboard is and how fresh its data are."""
    st.divider()
    st.markdown("**Rare-earth demand and the wind build-out**  \nBUS 751 portfolio · Assignments 3-6")
    label = "Real data snapshot" if META.get("source") == "real" else "SYNTHETIC data"
    st.caption(f"Showing: **{label}**. {freshness_text()}.")
    st.markdown(f"[Repository]({ui.REPO})")


# --- Navigation ------------------------------------------------------------------------------------

PAGES = {
    "answer": st.Page(guarded(answer_page), title="The answer", icon="✅", default=True),
    "wind": st.Page(guarded(wind_page), title="1 · Why: wind or size?", icon="🌬️", url_path="wind"),
    "actions": st.Page(guarded(actions_page), title="2 · What to do", icon="🎯", url_path="actions"),
    "market": st.Page(guarded(market_page), title="Market evidence", icon="📊", url_path="market"),
    "engine": st.Page(guarded(engine_page), title="Predictive engine", icon="🤖", url_path="engine"),
    "data": st.Page(guarded(data_page), title="Data and pipeline", icon="🗄️", url_path="data"),
    "limits": st.Page(guarded(limits_page), title="Limitations and reproducibility", icon="🔁", url_path="limits"),
}
SECTIONS = {"Start here": ["answer"], "The case": ["wind", "actions"],
            "More detail": ["market", "engine", "data"], "About": ["limits"]}

if __name__ == "__main__":  # always true under `streamlit run`; tests import the page functions instead
    NAV_ACTIVE = True
    st.navigation({section: [PAGES[k] for k in keys] for section, keys in SECTIONS.items()}).run()
    with st.sidebar:  # after the page, so it sits under the page's filters
        guarded(sidebar_info)()
