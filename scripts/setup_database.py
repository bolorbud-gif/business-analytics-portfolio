"""Create the database and its tables without loading data.

Usage (from the project root):
    uv run python scripts/setup_database.py

Optional: run_pipeline.py also creates the tables, so this is only needed to
inspect or reset the empty schema.
"""

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.data_pipeline import PipelineError, read_config  # noqa: E402
from src.data_pipeline.load import create_schema, get_engine  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    try:
        db = read_config("config/database.yaml")["database"]
        create_schema(get_engine(db["url"], db.get("echo", False)))
    except PipelineError as exc:
        logging.error("%s", exc)
        return 1
    logging.info("Database ready at %s", db["url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
