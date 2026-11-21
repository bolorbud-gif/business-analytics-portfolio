"""Exploratory analysis: open the Assignment 4 database, check its quality, describe the data.

    from src.analysis.exploratory import open_database, check_database, load_country_panel
    con, path = open_database()          # real database, or the synthetic sample if absent
    check_database(con)                  # one row per check, with passed True/False
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from src.data_pipeline import PipelineError
from src.data_pipeline.load import connect
from src.data_pipeline.validate import validate_view
from src.data_pipeline.views import VIEWS

ROOT = Path(__file__).resolve().parents[2]
REAL_DB = ROOT / "data" / "processed" / "rare_earth.db"
SAMPLE_DB = ROOT / "data" / "processed" / "rare_earth_sample.db"
TABLES = ["countries", "products", "energy_sources", "trade_flows", "electricity_generation"]
SIZE_GROUPS = ["Small", "Medium", "Large"]  # terciles of total generation, smallest first


# --- Connecting -----------------------------------------------------------------------

def open_database(path=None):
    """Open the database with foreign keys ON. Returns (connection, path).

    Without a path, uses the real database if it has been built, otherwise the
    synthetic sample, so the notebooks also run for reviewers without the real data.
    """
    if path is None:
        path = REAL_DB if REAL_DB.exists() else SAMPLE_DB
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Build it first: uv run python scripts/run_pipeline.py "
            "(or add --sample for the synthetic data)"
        )
    return connect(path), path


# --- Data quality ---------------------------------------------------------------------

def check_database(con) -> pd.DataFrame:
    """Run data-quality checks on the database. One row per check: check, passed, detail."""
    rows = []

    def add(check, passed, detail):
        """Record one check result."""
        rows.append({"check": check, "passed": bool(passed), "detail": detail})

    fk_on = con.execute("PRAGMA foreign_keys").fetchone()[0]
    add("Foreign keys enforced on this connection", fk_on == 1, f"PRAGMA foreign_keys = {fk_on}")
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    add("SQLite file integrity", integrity == "ok", integrity)
    orphans = con.execute("PRAGMA foreign_key_check").fetchall()
    add("No orphan rows", not orphans, f"{len(orphans)} rows without a matching parent")

    for table in TABLES:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        add(f"Table {table} is not empty", n > 0, f"{n:,} rows")

    for name, (_, key) in VIEWS.items():
        df = pd.read_sql(f"SELECT * FROM {name}", con)
        duplicates = int(df.duplicated(key).sum())
        add(f"View {name}: one row per key", duplicates == 0,
            f"{len(df):,} rows, {duplicates} duplicate keys on ({', '.join(key)})")
        try:
            validate_view(name, df)
            add(f"View {name}: passes validation rules", True, "all Pandera checks pass")
        except PipelineError as exc:
            add(f"View {name}: passes validation rules", False, str(exc))

    trade = con.execute("SELECT COUNT(*) FROM trade_flows").fetchone()[0]
    reimports = con.execute(
        "SELECT COUNT(*) FROM trade_flows WHERE partner_id IN (SELECT reporter_id FROM trade_flows)"
    ).fetchone()[0]
    merged = con.execute("SELECT COUNT(*) FROM trade_wind_merged").fetchone()[0]
    add("trade_wind_merged keeps every trade row except re-imports", merged == trade - reimports,
        f"{trade} trade rows - {reimports} re-imports = {trade - reimports}; view has {merged}")
    return pd.DataFrame(rows)


def table_row_counts(con) -> pd.Series:
    """Number of rows in each stored table."""
    return pd.Series({t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES},
                     name="rows")


def coverage_by_year(con) -> pd.DataFrame:
    """Number of trade rows per year and direction: shows which years each direction covers."""
    df = pd.read_sql("SELECT year, trade_flow FROM trade_flows", con)
    return pd.crosstab(df["year"], df["trade_flow"]).rename_axis(columns=None)


# --- Loading analysis frames ------------------------------------------------------------

def load_trade(con) -> pd.DataFrame:
    """Every trade row with the partner's power mix (view partner_trade_energy)."""
    return pd.read_sql("SELECT * FROM partner_trade_energy", con)


def load_country_panel(con) -> pd.DataFrame:
    """One row per partner country and year: imports from China, growth, wind, and size.

    Adds the country's total and renewable generation (size and energy mix), and wind's
    and renewables' share of generation.
    """
    df = pd.read_sql("""
        SELECT w.*, tot.generation_twh AS total_generation_twh,
               ren.generation_twh AS renewables_twh
        FROM country_wind_imports w
        LEFT JOIN electricity_generation_detail tot
               ON tot.country = w.country AND tot.year = w.year AND tot.source = 'Total generation'
        LEFT JOIN electricity_generation_detail ren
               ON ren.country = w.country AND ren.year = w.year AND ren.source = 'Renewables'
    """, con)
    total = df["total_generation_twh"].where(df["total_generation_twh"] > 0)
    df["wind_share_pct"] = df["wind_generation_twh"] / total * 100
    df["renewables_share_pct"] = df["renewables_twh"] / total * 100
    return df


def load_wind(con) -> pd.DataFrame:
    """Wind generation and capacity per country and year."""
    return pd.read_sql("""
        SELECT country, year, generation_twh AS wind_generation_twh, capacity_gw AS wind_capacity_gw
        FROM electricity_generation_detail WHERE source = 'Wind'
    """, con)


def missing_by_year(df: pd.DataFrame, columns: list[str], year: str = "year") -> pd.DataFrame:
    """Percentage of missing values in each column, per year."""
    return (df[columns].isna().groupby(df[year]).mean() * 100).round(1)


def wind_trend(wind: pd.DataFrame, focus: str = "China") -> tuple[pd.DataFrame, dict]:
    """Total wind capacity per year: the `focus` country vs all other countries combined.

    Only countries with data for every year are used, so the totals are comparable across
    years. If `focus` isn't in the data, a single "All" series is returned instead.
    Returns (table with one column per series, info dict with series, labels, countries
    and focus_ahead: whether `focus` exceeds the others in the last year, or None).
    """
    years = wind.groupby("country")["year"].nunique()
    complete = wind[wind["country"].isin(years[years == years.max()].index)]
    n = complete["country"].nunique()
    if complete["country"].eq(focus).any():
        groups = complete["country"].eq(focus).map({True: focus, False: "Other"})
        series, labels = [focus, "Other"], [focus, f"Other {n - 1} countries"]
    else:
        groups, series, labels = "All", ["All"], [f"All {n} countries"]
    trend = (complete.assign(group=groups)
             .pivot_table(index="year", columns="group", values="wind_capacity_gw", aggfunc="sum")
             .reset_index())
    trend.columns.name = None
    last = trend.iloc[-1]
    focus_ahead = bool(last[focus] > last["Other"]) if focus in trend else None
    return trend, {"series": series, "labels": labels, "countries": n, "focus_ahead": focus_ahead}


def analysis_sample(panel: pd.DataFrame, include_non_buyers: bool = False) -> pd.DataFrame:
    """Country-years usable for the multivariate analysis: imports, wind capacity and
    total generation all recorded and positive (so logs exist). Adds a size tercile.

    include_non_buyers=True also keeps the country-years with no recorded imports, as 0 kg,
    in the years that have import data, for models that can use zeros (fit_ppml). A
    missing year most likely means China recorded no shipment, but the data can't confirm
    that it is a true zero.
    """
    imports = panel["imports_from_china_kg"]
    if include_non_buyers:
        trade_years = panel.loc[imports.notna(), "year"].unique()
        panel = panel.assign(imports_from_china_kg=imports.fillna(0).where(
            panel["year"].isin(trade_years)))
        buys = panel["imports_from_china_kg"] >= 0
    else:
        buys = imports > 0
    d = panel[buys & (panel["wind_capacity_gw"] > 0) & (panel["total_generation_twh"] > 0)].copy()
    d["size_group"] = pd.qcut(d["total_generation_twh"], 3, labels=SIZE_GROUPS)
    return d.reset_index(drop=True)


def balanced_panel(df: pd.DataFrame, entity: str = "country", period: str = "year") -> pd.DataFrame:
    """Only the entities observed in every period that df covers (a balanced panel).

    Re-running a model on it checks that entities seen in only some periods don't drive
    the result.
    """
    seen = df.groupby(entity)[period].transform("nunique")
    return df[seen == df[period].nunique()].reset_index(drop=True)


def import_year_pattern(panel: pd.DataFrame, start: int, end: int,
                        value: str = "imports_from_china_kg", entity: str = "partner") -> pd.DataFrame:
    """Which partners bought from China in both years, in only one, or in neither.

    One row per partner: its imports in each year (NaN = none recorded), the pattern, a
    buyer_type ("Every year", "Skipped a year", "Never") and its typical (median) recorded
    imports, to compare partners that skip years with partners that buy every year.
    """
    d = panel[panel["year"].isin([start, end])]
    wide = d.set_index([entity, "year"])[value].unstack("year").reindex(columns=[start, end])
    bought = wide > 0
    pattern = np.select([bought.all(axis=1), bought[start], bought[end]],
                        ["Both years", f"{start} only", f"{end} only"], "Neither")
    out = pd.DataFrame({f"kg_{start}": wide[start], f"kg_{end}": wide[end], "pattern": pattern},
                       index=wide.index)
    out["buyer_type"] = np.select([out["pattern"] == "Both years", out["pattern"] == "Neither"],
                                  ["Every year", "Never"], "Skipped a year")
    out["typical_kg"] = wide.where(bought).median(axis=1)
    return out.sort_values("typical_kg", ascending=False)


# --- Describing ---------------------------------------------------------------------------

def describe_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Univariate summary: count, missing, centre, spread and skew for each column."""
    rows = []
    for col in columns:
        s = df[col]
        v = s.dropna()
        rows.append({
            "column": col, "n": len(v), "missing": int(s.isna().sum()),
            "missing_pct": round(s.isna().mean() * 100, 1),
            "mean": v.mean(), "median": v.median(), "std": v.std(),
            "min": v.min(), "max": v.max(),
            "skew": stats.skew(v) if len(v) > 2 else float("nan"),
        })
    return pd.DataFrame(rows).set_index("column")


def buyer_volumes(trade: pd.DataFrame, year: int, trade_flow: str = "Export") -> pd.Series:
    """Total kg per partner for one year and direction (Export = what each country bought)."""
    rows = trade[(trade["trade_flow"] == trade_flow) & (trade["year"] == year)]
    return rows.groupby("partner")["quantity_kg"].sum()


def buyers_by_year(trade: pd.DataFrame, trade_flow: str = "Export") -> pd.DataFrame:
    """Every partner in every year: kg, value, price (USD per kg) and share of that year's
    volume, largest buyer first within each year."""
    rows = trade[trade["trade_flow"] == trade_flow]
    out = rows.groupby(["year", "partner"], as_index=False)[["quantity_kg", "trade_value_kusd"]].sum()
    out["usd_per_kg"] = out["trade_value_kusd"] * 1000 / out["quantity_kg"]
    out["share_pct"] = out["quantity_kg"] / out.groupby("year")["quantity_kg"].transform("sum") * 100
    return out.sort_values(["year", "quantity_kg"], ascending=[True, False], ignore_index=True)


def market_shares(df: pd.DataFrame, by: str, value: str, top: int = 10) -> pd.DataFrame:
    """Each group's share of the total, largest first; groups after `top` folded into one row."""
    totals = df.groupby(by)[value].sum().sort_values(ascending=False)
    shares = (totals / totals.sum()).rename("share").to_frame()
    shares[value] = totals
    if len(shares) > top:
        rest = shares.iloc[top:]
        other = pd.DataFrame({"share": [rest["share"].sum()], value: [rest[value].sum()]},
                             index=[f"All other ({len(rest)})"])
        shares = pd.concat([shares.iloc[:top], other])
    return shares


def concentration(values: pd.Series) -> dict:
    """Market concentration of a set of values (e.g. kg bought per country).

    HHI = sum of squared percentage shares (0-10,000). Under the 2023 US merger
    guidelines, above 1,800 is highly concentrated and 1,000-1,800 moderately.
    """
    v = values.dropna()
    v = v[v > 0].sort_values(ascending=False)
    share = v / v.sum()
    hhi = float((share * 100).pow(2).sum())
    level = ("highly concentrated" if hhi > 1800 else "moderately concentrated" if hhi >= 1000
             else "unconcentrated")
    return {
        "countries": len(v),
        "top1_share": float(share.iloc[0]),
        "top5_share": float(share.head(5).sum()),
        "top10_share": float(share.head(10).sum()),
        "hhi": round(hhi),
        "level": level,
    }


def yearly_trade(trade: pd.DataFrame) -> pd.DataFrame:
    """Totals per year and direction, with the average unit value (total value / total kg)."""
    out = trade.groupby(["year", "trade_flow"]).agg(
        partners=("partner", "nunique"),
        quantity_kg=("quantity_kg", "sum"),
        value_kusd=("trade_value_kusd", "sum"),
    )
    out["unit_value_usd_per_kg"] = out["value_kusd"] * 1000 / out["quantity_kg"]
    return out.reset_index()


def period_change(yearly: pd.DataFrame, trade_flow: str, start: int, end: int) -> pd.Series:
    """Percent change in quantity, value and unit value between two years for one direction."""
    rows = yearly[yearly["trade_flow"] == trade_flow].set_index("year")
    if start not in rows.index or end not in rows.index:
        raise ValueError(f"{trade_flow} has no data for {start} and/or {end}")
    cols = ["quantity_kg", "value_kusd", "unit_value_usd_per_kg"]
    return ((rows.loc[end, cols] / rows.loc[start, cols] - 1) * 100).astype(float)


def buyer_price_changes(trade: pd.DataFrame, start: int, end: int,
                        trade_flow: str = "Export") -> pd.DataFrame:
    """Each partner's volume and price (USD per kg) in both years, for partners present in both.

    Sorted by start-year volume; volume_share_start is the partner's share of that volume.
    """
    rows = trade[(trade["trade_flow"] == trade_flow) & trade["year"].isin([start, end])]
    sums = rows.groupby(["partner", "year"])[["quantity_kg", "trade_value_kusd"]].sum().unstack("year")
    q, v = sums["quantity_kg"], sums["trade_value_kusd"] * 1000
    keep = (q[start] > 0) & (q[end] > 0)
    out = pd.DataFrame({"kg_start": q[start], "kg_end": q[end],
                        "price_start": v[start] / q[start], "price_end": v[end] / q[end]})[keep]
    out["price_change_pct"] = (out["price_end"] / out["price_start"] - 1) * 100
    out["volume_share_start"] = out["kg_start"] / out["kg_start"].sum()
    return out.sort_values("kg_start", ascending=False)


def price_mix_decomposition(trade: pd.DataFrame, start: int, end: int,
                            trade_flow: str = "Export", exclude: list[str] | None = None) -> dict:
    """Split the change in the average price per kg into a price effect and a mix effect.

    The average price can fall because buyers pay less (price) or because volume shifts
    towards buyers who pay less (mix). The price effect is a fixed-basket (Laspeyres)
    index: what the start year's volumes would cost at end-year prices, for partners
    present in both years. The mix effect is the rest:
    (1 + average change) = (1 + price effect) x (1 + mix effect).
    exclude: partners to leave out, to see how much one large buyer drives the result.
    """
    if exclude:
        trade = trade[~trade["partner"].isin(exclude)]
    rows = trade[trade["trade_flow"] == trade_flow]
    totals = rows.groupby("year")[["quantity_kg", "trade_value_kusd"]].sum()
    average = totals["trade_value_kusd"] / totals["quantity_kg"]
    average_change = average[end] / average[start] - 1
    b = buyer_price_changes(trade, start, end, trade_flow)
    w = b["volume_share_start"]
    price_change = (w * b["price_end"]).sum() / (w * b["price_start"]).sum() - 1
    return {"average_change_pct": float(average_change * 100),
            "price_effect_pct": float(price_change * 100),
            "mix_effect_pct": float(((1 + average_change) / (1 + price_change) - 1) * 100),
            "buyers": len(b),
            "volume_covered": float(b["kg_start"].sum() / totals.loc[start, "quantity_kg"]),
            "volume_share_price_fell": float(w[b["price_end"] < b["price_start"]].sum())}


def growth_vs_wind(panel: pd.DataFrame, year: int) -> pd.DataFrame:
    """Country rows for one year with both import growth and wind generation change recorded.

    Adds import_ratio = this year's imports / last year's (1 + growth/100), which can be
    drawn on a log axis: the explosive growth from tiny bases otherwise flattens the chart.
    Ranks, and so the Spearman correlation, are the same as for the growth rate itself.
    """
    cols = ["country", "year", "import_growth_pct", "wind_generation_change_twh"]
    d = panel.loc[panel["year"] == year, cols].dropna()
    return d.assign(import_ratio=1 + d["import_growth_pct"] / 100)
