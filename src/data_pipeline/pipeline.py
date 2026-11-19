"""End-to-end pipeline, importable from notebooks and tests.

    from src.data_pipeline.pipeline import run_pipeline
    report = run_pipeline("data/sample", {"trade": "data1.xlsx", "electricity": "data2.xlsx"},
                          "sqlite:///data/processed/rare_earth_sample.db")
"""

import logging
from pathlib import Path

from src.data_pipeline import PipelineError
from src.data_pipeline.extract import extract
from src.data_pipeline.load import create_schema, get_engine, load
from src.data_pipeline.quality import QualityReport
from src.data_pipeline.transform import (
    build_country_wind_imports, build_partner_trade_energy, build_trade_wind_merged,
    transform_electricity, transform_trade,
)
from src.data_pipeline.validate import validate_table

logger = logging.getLogger(__name__)

EXPORT_TABLES = ["country_wind_imports", "trade_wind_merged"]


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
    """Extract -> transform -> validate -> load. Builds the database or refreshes it.

    Always writes the quality report (if report_path is given), also when a stage
    fails, so the reason is recorded. Raises PipelineError on failure. If export_dir
    is given, the analysis tables in EXPORT_TABLES are also saved there as CSV.
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
        combined = validate_table("partner_trade_energy",
                                  build_partner_trade_energy(trade, electricity, report),
                                  report, **checks)
        if len(combined) != len(trade):
            raise PipelineError("partner_trade_energy row count differs from trade_flows")
        wind_imports = validate_table("country_wind_imports",
                                      build_country_wind_imports(trade, electricity, report),
                                      report, **checks)
        merged = validate_table("trade_wind_merged",
                                build_trade_wind_merged(trade, wind_imports, report),
                                report, **checks)

        logger.info("--- Stage: load")
        engine = get_engine(database_url, echo)
        create_schema(engine, rebuild=rebuild)
        load(engine, {"trade_flows": trade, "electricity_generation": electricity,
                      "partner_trade_energy": combined,
                      "country_wind_imports": wind_imports,
                      "trade_wind_merged": merged}, report)
        if export_dir:
            tables = {"country_wind_imports": wind_imports, "trade_wind_merged": merged}
            Path(export_dir).mkdir(parents=True, exist_ok=True)
            for name in EXPORT_TABLES:
                tables[name].to_csv(Path(export_dir) / f"{name}.csv", index=False)
            logger.info("Exported %s to %s as CSV", ", ".join(EXPORT_TABLES), export_dir)
        report.status = "SUCCESS"
        return report
    except Exception as exc:
        report.status = f"FAILED: {exc}"
        raise
    finally:
        if report_path:
            report.write(report_path)
            logger.info("Quality report written to %s", report_path)
