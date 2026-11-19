"""Run the ETL pipeline end to end: extract -> transform -> validate -> load.

Usage (from the project root):
    uv run python scripts/run_pipeline.py

Logs go to the console and to logs/pipeline.log. Exits with code 1 on failure.
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
from src.data_pipeline.extract import extract  # noqa: E402
from src.data_pipeline.load import create_schema, get_engine, load  # noqa: E402
from src.data_pipeline.transform import transform  # noqa: E402
from src.data_pipeline.validate import validate  # noqa: E402

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


def run(app_config: dict, db_config: dict) -> dict[str, int]:
    """Run every stage in order and return the row count loaded per table."""
    pipeline = app_config["pipeline"]
    stages = [
        ("extract", lambda _: extract(Path(pipeline["raw_dir"]), pipeline["sources"])),
        ("transform", transform),
        ("validate", validate),
    ]
    data = None
    for name, stage in stages:
        logger.info("--- Stage: %s", name)
        data = stage(data)

    logger.info("--- Stage: load")
    engine = get_engine(db_config["database"]["url"], db_config["database"].get("echo", False))
    create_schema(engine)
    return load(engine, data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="config/app_config.yaml")
    parser.add_argument("--db-config", default="config/database.yaml")
    args = parser.parse_args()

    try:
        app_config = read_config(args.config)
        db_config = read_config(args.db_config)
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    log = app_config.get("logging", {})
    log_path = setup_logging(log.get("level", "INFO"), log.get("log_dir", "logs"),
                             log.get("log_file", "pipeline.log"))

    start = time.perf_counter()
    logger.info("Pipeline started (log file: %s)", log_path)
    try:
        counts = run(app_config, db_config)
    except PipelineError as exc:
        logger.error("Pipeline FAILED: %s", exc)
        return 1
    except Exception:
        logger.exception("Pipeline FAILED with an unexpected error")
        return 1

    logger.info("Pipeline finished in %.1fs. Rows loaded: %s",
                time.perf_counter() - start, counts)
    logger.info("Database: %s", db_config["database"]["url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
