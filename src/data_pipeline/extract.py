"""Extract stage: read the raw Excel files from data/raw/."""

import logging
from pathlib import Path

import pandas as pd

from src.data_pipeline import PipelineError

logger = logging.getLogger(__name__)


def read_excel(path: Path) -> pd.DataFrame:
    """Read the first sheet of an Excel file, with a clear error if it is missing."""
    path = Path(path)
    if not path.exists():
        raise PipelineError(f"Raw data file not found: {path}")
    try:
        df = pd.read_excel(path, sheet_name=0)
    except Exception as exc:  # corrupt file, wrong format, file open in Excel, ...
        raise PipelineError(f"Could not read {path}: {exc}") from exc
    if df.empty:
        raise PipelineError(f"Raw data file is empty: {path}")
    logger.info("Extracted %s rows x %s columns from %s", len(df), df.shape[1], path.name)
    return df


def extract(raw_dir: Path, sources: dict[str, str]) -> dict[str, pd.DataFrame]:
    """Read every configured source file. Returns {source name: raw DataFrame}."""
    raw_dir = Path(raw_dir)
    return {name: read_excel(raw_dir / filename) for name, filename in sources.items()}
