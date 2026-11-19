"""End-to-end pipeline, importable from notebooks and tests.

    from src.data_pipeline.pipeline import run_pipeline
    report = run_pipeline("data/sample", {"trade": "data1.xlsx", "electricity": "data2.xlsx"},
                          "sqlite:///data/processed/rare_earth_sample.db")
"""

import logging
from pathlib import Path

import pandas as pd

from src.data_pipeline import PipelineError
from src.data_pipeline.extract import extract
from src.data_pipeline.load import create_schema, get_engine, load
from src.data_pipeline.quality import QualityReport
from src.data_pipeline.transform import normalize, transform_electricity, transform_trade
from src.data_pipeline.validate import validate_table

logger = logging.getLogger(__name__)

EXPORT_TABLES = ["country_wind_imports", "trade_wind_merged", "trade_wind_wide"]
EXCEL_TABLES = {"trade_wind_wide": "trade_wind"}  # table -> sheet name, also saved as .xlsx


def run_pipeline(
    raw_dir,
    sources: dict[str, str],
    database_url: str,
    report_path=None,
    rejected_dir="data/interim",
    max_rejected_pct: float = 5.0,
    rebuild: bool = False,
    echo: bool = False,
    export_dir=None,
) -> QualityReport:
    """Extract -> transform -> validate -> normalize -> load. Builds or refreshes the database.

    Always writes the quality report (if report_path is given), also when a stage
    fails, so the reason is recorded. Raises PipelineError on failure. If export_dir
    is given, the analysis views in EXPORT_TABLES are also saved there as CSV, and
    those in EXCEL_TABLES as a one-sheet Excel file.
    """
    report = QualityReport(raw_dir=str(raw_dir), database=database_url)
    checks = {"rejected_dir": Path(rejected_dir), "max_rejected_pct": max_rejected_pct}
    try:
        logger.info("--- Stage: extract")
        raw = extract(Path(raw_dir), sources)

        logger.info("--- Stage: transform + validate")
        trade = validate_table("trade_flows", transform_trade(raw["trade"], report),
                               report, **checks)
        electricity = validate_table("electricity_generation",
                                     transform_electricity(raw["electricity"], report),
                                     report, **checks)

        logger.info("--- Stage: normalize")
        tables = normalize(trade, electricity, report)

        logger.info("--- Stage: load")
        engine = get_engine(database_url, echo)
        create_schema(engine, rebuild=rebuild)
        views = load(engine, tables, report)
        describe_views(views, trade, report)

        if export_dir:
            export(views, Path(export_dir))
            logger.info("Exported %s to %s (CSV; %s also as Excel)", ", ".join(EXPORT_TABLES),
                        export_dir, ", ".join(EXCEL_TABLES))
        report.status = "SUCCESS"
        return report
    except Exception as exc:
        report.status = f"FAILED: {exc}"
        raise
    finally:
        if report_path:
            report.write(report_path)
            logger.info("Quality report written to %s", report_path)


def export(views: dict[str, pd.DataFrame], export_dir: Path) -> None:
    """Save the analysis views as CSV (and Excel). Runs after the database is saved."""
    export_dir.mkdir(parents=True, exist_ok=True)
    files = [(views[n].to_csv, export_dir / f"{n}.csv", {}) for n in EXPORT_TABLES]
    files += [(views[n].to_excel, export_dir / f"{n}.xlsx", {"sheet_name": sheet})
              for n, sheet in EXCEL_TABLES.items()]
    for write, path, kwargs in files:
        try:
            write(path, index=False, **kwargs)
        except PermissionError as exc:
            raise PipelineError(
                f"Could not overwrite {path}: it is probably open in Excel. Close it and run "
                f"again (the database itself was updated successfully)."
            ) from exc


def describe_views(views: dict[str, pd.DataFrame], trade: pd.DataFrame,
                   report: QualityReport) -> None:
    """Add plain-language notes about gaps in the analysis views to the report."""
    pte = views["partner_trade_energy"]
    unmatched = sorted(pte.loc[pte["total_generation_twh"].isna(), "partner"].unique())
    if unmatched:
        report.notes.append(
            f"partner_trade_energy: {int(pte['total_generation_twh'].isna().sum())} row(s) have "
            f"NULL electricity fields: no electricity data for {len(unmatched)} partner(s) in "
            f"those years: {', '.join(unmatched)}."
        )
    cwi = views["country_wind_imports"]
    has_kg = cwi["imports_from_china_kg"].notna()
    years = sorted(int(y) for y in cwi.loc[has_kg, "year"].unique())
    report.notes.append(
        f"country_wind_imports: imports from China recorded for {int(has_kg.sum())} of "
        f"{len(cwi)} country-years (years {years}); import growth computed for "
        f"{int(cwi['import_growth_pct'].notna().sum())}. Other years have no Export rows in "
        f"data1.xlsx, so they are NULL, not zero."
    )
    merged = views["trade_wind_merged"]
    left_out = len(trade) - len(merged)
    if left_out:
        kept = set(zip(merged["partner"], merged["year"]))
        partners = sorted({p for p, y in zip(trade["partner"], trade["year"]) if (p, y) not in kept})
        report.notes.append(
            f"trade_wind_merged: {left_out} data1.xlsx row(s) not matched to "
            f"country_wind_imports and left out (partner {', '.join(partners)}: the reporter "
            f"trading with itself is re-imports)."
        )
    wide = views["trade_wind_wide"]
    exp, imp = wide["imports_from_china_kg"].notna(), wide["exports_to_china_kg"].notna()
    report.notes.append(
        f"trade_wind_wide: {int((exp & imp).sum())} country-year(s) have both directions, "
        f"{int((exp & ~imp).sum())} only imports from China, {int((~exp & imp).sum())} only "
        f"exports to China."
    )
