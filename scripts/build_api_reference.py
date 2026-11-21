"""Generate docs/api_reference.md from the docstrings in src/.

Usage (from the project root):
    uv run python scripts/build_api_reference.py

Run it after adding or changing a public function; tests/test_analysis.py checks that
every public function is listed.
"""

import importlib
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PACKAGES = {
    "src.analysis": ["exploratory", "statistical", "charts"],
    "src.modeling": ["train", "evaluate", "predict"],
    "src.dashboard": ["data", "components"],  # app.py is the Streamlit script itself
    "src.data_pipeline": ["pipeline", "extract", "transform", "validate", "load", "views", "quality"],
}


def public_members(module):
    """Functions and classes defined in this module whose names don't start with _."""
    for name, obj in inspect.getmembers(module):
        if name.startswith("_") or getattr(obj, "__module__", None) != module.__name__:
            continue
        if inspect.isfunction(obj) or inspect.isclass(obj):
            yield name, obj


def summary(obj) -> str:
    doc = inspect.getdoc(obj) or ""
    return " ".join(doc.split("\n\n")[0].split())


class _FromRoot:
    """A path default shown relative to the project root, so the reference holds no
    machine-specific absolute paths."""

    def __init__(self, path: Path):
        self.text = path.relative_to(ROOT).as_posix()

    def __repr__(self) -> str:
        return "ROOT" if self.text == "." else f"ROOT / '{self.text}'"


def signature(obj) -> str:
    """The signature, with path defaults inside the project written relative to its root."""
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        return "(...)"
    params = [p.replace(default=_FromRoot(p.default))
              if isinstance(p.default, Path) and p.default.is_relative_to(ROOT) else p
              for p in sig.parameters.values()]
    return str(sig.replace(parameters=params))


def build() -> str:
    lines = ["# API Reference", "",
             "Generated from the docstrings by `scripts/build_api_reference.py`; do not edit by hand.",
             "Every function below is importable, e.g. `from src.analysis import statistical as st`.", ""]
    for package, modules in PACKAGES.items():
        pkg = importlib.import_module(package)
        lines += [f"## `{package}`", "", summary(pkg), ""]
        for mod_name in modules:
            module = importlib.import_module(f"{package}.{mod_name}")
            lines += [f"### `{package}.{mod_name}`", "", summary(module), ""]
            for name, obj in public_members(module):
                kind = "class" if inspect.isclass(obj) else "def"
                lines.append(f"- **`{name}`** `{kind} {name}{signature(obj)}`")
                text = summary(obj)
                if text:
                    lines.append(f"  {text}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    path = ROOT / "docs" / "api_reference.md"
    path.write_text(build(), encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)}")
