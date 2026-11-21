"""Build, check and launch the dashboard (Assignment 7).

Usage (from the project root, after `uv sync`):

    uv run python scripts/deploy.py run               # dashboard on the committed real-data snapshot
    uv run python scripts/deploy.py run --sample      # rebuild everything from the synthetic data, then launch
    uv run python scripts/deploy.py build --sample    # only rebuild the synthetic snapshot
    uv run python scripts/deploy.py build             # with the real data: rebuild data/published
    uv run python scripts/deploy.py check             # with the real data: retrain and rebuild in a temporary
                                                      # folder, compare with data/published (exit 1 if they differ)

The dashboard reads a snapshot of results (src/dashboard/data.py) built from the Assignment 4 database
and the Assignment 6 engine artifact (models/*.joblib), so these commands are the whole reproduction
path: data -> database -> engine artifact -> snapshot -> app. A missing (or outdated) engine artifact
is trained first, which takes about 2 minutes; --retrain forces it.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dashboard import data  # noqa: E402

APP = ROOT / "src" / "dashboard" / "app.py"


def real_database() -> Path:
    """The real database, or a clear message on how to build it."""
    from src.analysis import exploratory as ex
    if not ex.REAL_DB.exists():
        sys.exit("The real database isn't built. Put data1.xlsx and data2.xlsx in data/raw/ "
                 "(see docs/setup.md), then run: uv run python scripts/run_pipeline.py")
    return ex.REAL_DB


def engine_artifact(con, sample: bool, retrain: bool, path: Path, source: str) -> dict:
    """The Assignment 6 engine bundle: loaded if it exists and is current, trained otherwise."""
    if not retrain and path.exists():
        try:
            return data.load_engine_artifact(path)
        except data.SnapshotError as err:
            print(f"{err}\nRetraining it.")
    print(f"Training the engine on {'synthetic data' if sample else source} "
          f"(nested cross-validation, about 2 minutes)...")
    data.train_engine_artifact(con, real=not sample, path=path, source=source)
    return data.load_engine_artifact(path)


def build(sample: bool, out: Path | None = None, retrain: bool = False, engine_path: Path | None = None) -> Path:
    """Rebuild a snapshot: from the synthetic sample (rebuilding its database first) or the real data."""
    from src.analysis import exploratory as ex
    if sample:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "run_pipeline.py"), "--sample"], cwd=ROOT,
                       check=True)
        db, real, out = ex.SAMPLE_DB, False, out or data.SAMPLE_SNAPSHOT
        engine_path = engine_path or data.SAMPLE_ENGINE
    else:
        db, real, out = real_database(), True, out or data.PUBLISHED
        engine_path = engine_path or data.ENGINE
    con, _ = ex.open_database(db)
    try:
        bundle = engine_artifact(con, sample, retrain, engine_path, db.name)
        print(f"Building the dashboard snapshot from {db.name} and {engine_path.name}...")
        snapshot = data.build_snapshot(con, bundle, real=real, source=db.name)
    finally:
        con.close()
    path = data.save_snapshot(snapshot, out)
    print(f"Snapshot written to {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return path


def check() -> int:
    """Retrain the engine and rebuild the snapshot from the real data, in a temporary folder, and
    compare with the committed snapshot: the full reproduction path, end to end."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh = build(sample=False, out=Path(tmp) / "snapshot", retrain=True,
                      engine_path=Path(tmp) / "engine.joblib")
        problems = data.compare_snapshots(data.PUBLISHED, fresh)
    if problems:
        print(f"The committed snapshot differs from a fresh build ({len(problems)} differences):")
        for p in problems:
            print("  -", p)
        return 1
    print("OK: the committed snapshot matches a fresh build from the real data.")
    return 0


def run(sample: bool, rebuild: bool, port: int, path: Path | None) -> int:
    """Launch the dashboard on a snapshot (building the synthetic one first if needed)."""
    if sample:
        path = data.SAMPLE_SNAPSHOT
        if rebuild or not (path / "meta.json").exists():
            build(sample=True)
    path = path or data.PUBLISHED
    print(f"Dashboard on {data.relative_to_root(path)} at http://localhost:{port} (Ctrl+C to stop)")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(APP), "--server.port", str(port),
                            "--browser.gatherUsageStats", "false", "--", "--data", str(path)], cwd=ROOT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="rebuild a snapshot")
    b.add_argument("--sample", action="store_true", help="from the synthetic sample (no restricted data needed)")
    b.add_argument("--retrain", action="store_true", help="retrain the engine even if its artifact exists")
    sub.add_parser("check", help="rebuild from the real data and compare with data/published")
    r = sub.add_parser("run", help="launch the dashboard")
    r.add_argument("--sample", action="store_true", help="use the synthetic snapshot (built if missing)")
    r.add_argument("--rebuild", action="store_true", help="with --sample: rebuild it even if it exists")
    r.add_argument("--data", type=Path, default=None, help="any snapshot folder")
    r.add_argument("--port", type=int, default=8501)
    args = parser.parse_args(argv)
    if args.command == "build":
        build(args.sample, retrain=args.retrain)
        return 0
    if args.command == "check":
        return check()
    return run(args.sample, args.rebuild, args.port, args.data)


if __name__ == "__main__":
    raise SystemExit(main())
