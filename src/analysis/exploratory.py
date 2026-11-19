"""Exploratory analysis: open the Assignment 4 database, check its quality, describe the data.

    from src.analysis.exploratory import open_database, check_database, load_country_panel
    con, path = open_database()          # real database, or the synthetic sample if absent
    check_database(con)                  # one row per check, with passed True/False
"""

from pathlib import Path

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


def analysis_sample(panel: pd.DataFrame) -> pd.DataFrame:
    """Country-years usable for the multivariate analysis: imports, wind capacity and
    total generation all recorded and positive (so logs exist). Adds a size tercile."""
    d = panel[(panel["imports_from_china_kg"] > 0) & (panel["wind_capacity_gw"] > 0)
              & (panel["total_generation_twh"] > 0)].copy()
    d["size_group"] = pd.qcut(d["total_generation_twh"], 3, labels=["Small", "Medium", "Large"])
    return d.reset_index(drop=True)


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
