"""Build or refresh the database: extract -> transform -> validate -> load.

Usage (from the project root):
    uv run python scripts/run_pipeline.py            # real data in data/raw/
    uv run python scripts/run_pipeline.py --sample   # synthetic data in data/sample/
    uv run python scripts/run_pipeline.py --rebuild  # drop and recreate tables first

Logs go to the console and logs/pipeline.log; the quality report to docs/.
Exits with code 0 on success and 1 on failure.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # config paths are relative to the project root

from src.data_pipeline import PipelineError, read_config  # noqa: E402
from src.data_pipeline.pipeline import run_pipeline  # noqa: E402

logger = logging.getLogger("pipeline")


def setup_logging(level: str, log_dir: str, log_file: str) -> Path:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(log_dir) / log_file
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )
    return log_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", action="store_true",
                        help="use the committed synthetic sample instead of data/raw/")
    parser.add_argument("--rebuild", action="store_true",
                        help="drop and recreate all tables before loading")
    parser.add_argument("--config", default="config/app_config.yaml")
    parser.add_argument("--db-config", default="config/database.yaml")
    args = parser.parse_args()

    try:
        app = read_config(args.config)
        db = read_config(args.db_config)["database"]
    except (PipelineError, KeyError) as exc:
        print(f"ERROR: bad configuration: {exc}", file=sys.stderr)
        return 1

    log = app.get("logging", {})
    log_path = setup_logging(log.get("level", "INFO"), log.get("log_dir", "logs"),
                             log.get("log_file", "pipeline.log"))

    settings = dict(app["pipeline"])
    database_url = db["url"]
    if args.sample:
        settings.update(app["sample"])
        database_url = app["sample"]["database_url"]

    start = time.perf_counter()
    logger.info("Pipeline started (%s data, log file: %s)",
                "SAMPLE" if args.sample else "real", log_path)
    try:
        report = run_pipeline(
            raw_dir=settings["raw_dir"],
            sources=settings["sources"],
            database_url=database_url,
            report_path=settings["report"],
            rejected_dir=settings["rejected_dir"],
            max_rejected_pct=settings["max_rejected_pct"],
            rebuild=args.rebuild,
            echo=db.get("echo", False),
            export_csv=settings.get("export_csv"),
        )
    except PipelineError as exc:
        logger.error("Pipeline FAILED: %s", exc)
        return 1
    except Exception:
        logger.exception("Pipeline FAILED with an unexpected error")
        return 1

    loaded = {name: t.rows_after_load for name, t in report.tables.items()}
    logger.info("Pipeline finished in %.1fs. Rows loaded: %s", time.perf_counter() - start, loaded)
    logger.info("Database: %s | Quality report: %s", database_url, settings["report"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
