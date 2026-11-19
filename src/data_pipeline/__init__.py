"""ETL pipeline: extract raw Excel files, transform, validate, load into SQL."""


class PipelineError(Exception):
    """Raised when a pipeline stage fails with a problem the user must fix."""


def read_config(path) -> dict:
    """Read a YAML config file, with a clear error if it is missing or malformed."""
    from pathlib import Path

    import yaml

    path = Path(path)
    if not path.exists():
        raise PipelineError(f"Config file not found: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PipelineError(f"Invalid YAML in {path}: {exc}") from exc
