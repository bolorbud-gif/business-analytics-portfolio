"""Create the database tables without loading data, or export the schema as SQL.

Usage (from the project root):
    uv run python scripts/setup_database.py              # create empty tables
    uv run python scripts/setup_database.py --rebuild    # drop and recreate them
    uv run python scripts/setup_database.py --ddl docs/schema.sql   # write CREATE TABLE SQL

run_pipeline.py also creates the tables, so this is only needed to inspect or
reset the empty schema.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from sqlalchemy.dialects import sqlite  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from src.data_pipeline import PipelineError, read_config  # noqa: E402
from src.data_pipeline.load import create_schema, get_engine, metadata  # noqa: E402
from src.data_pipeline.views import view_ddl  # noqa: E402


def write_ddl(path: Path) -> None:
    statements = []
    for table in metadata.sorted_tables:
        sql = str(CreateTable(table).compile(dialect=sqlite.dialect())).strip()
        statements.append("\n".join(line.rstrip() for line in sql.splitlines()) + ";")
        for index in sorted(table.indexes, key=lambda i: i.name):
            statements.append(str(CreateIndex(index).compile(dialect=sqlite.dialect())) + ";")
    statements += ["-- View: computed from the tables above, stores nothing\n" + v
                   for v in view_ddl()]
    header = ("-- Database schema (SQLite), generated from src/data_pipeline/load.py\n"
              "-- and src/data_pipeline/views.py\n"
              "-- Regenerate: uv run python scripts/setup_database.py --ddl docs/schema.sql\n\n")
    path.write_text(header + "\n\n".join(statements) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rebuild", action="store_true", help="drop and recreate all tables")
    parser.add_argument("--ddl", type=Path, help="write the CREATE TABLE/INDEX/VIEW SQL to this file")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if args.ddl:
        write_ddl(args.ddl)
        logging.info("Schema SQL written to %s", args.ddl)
        return 0
    try:
        db = read_config("config/database.yaml")["database"]
        create_schema(get_engine(db["url"], db.get("echo", False)), rebuild=args.rebuild)
    except PipelineError as exc:
        logging.error("%s", exc)
        return 1
    logging.info("Database ready at %s", db["url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
