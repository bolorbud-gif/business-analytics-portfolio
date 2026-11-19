"""Data quality tracking: what came in, what was fixed, dropped, rejected and loaded."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

# How each kind of bad record is handled. Rendered into the quality report.
BAD_RECORD_POLICY = [
    ("Header/cell swap in reporter column (data1.xlsx)", "Transform",
     "Repaired: column renamed to `reporter`, header value restored in the row; logged"),
    ("Exact duplicate rows", "Validate",
     "First copy kept, other copies dropped; counted"),
    ("Row breaks a validation rule (bad value, wrong unit, range, key conflict)", "Validate (Pandera)",
     "Rejected: not loaded; saved with the reason to `data/interim/rejected_<table>.csv`"),
    ("Rejected share above `max_rejected_pct`", "Validate",
     "Run stops before loading; database left unchanged"),
    ("Missing file, missing column, database error", "Any stage",
     "Run stops; database left unchanged (load is one transaction)"),
    ("Trade partner with no electricity data that year", "Transform",
     "Kept; electricity columns left NULL; partners listed under Notes"),
]


@dataclass
class TableQuality:
    name: str
    source: str
    rows_in: int = 0
    rows_repaired: int = 0
    repairs: list[str] = field(default_factory=list)
    duplicates_dropped: int = 0
    rejected_by_reason: Counter = field(default_factory=Counter)
    rows_rejected: int = 0
    rows_valid: int = 0
    missing: dict[str, int] = field(default_factory=dict)
    rows_before_load: int | None = None
    rows_after_load: int | None = None
    checksum_before: str | None = None
    checksum_after: str | None = None


@dataclass
class QualityReport:
    raw_dir: str
    database: str
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    status: str = "RUNNING"
    tables: dict[str, TableQuality] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def table(self, name: str, source: str = "") -> TableQuality:
        if name not in self.tables:
            self.tables[name] = TableQuality(name, source)
        return self.tables[name]

    def to_markdown(self) -> str:
        lines = [
            "# Data Quality Report",
            "",
            "Generated automatically by `scripts/run_pipeline.py`. Do not edit by hand.",
            "",
            f"- **Run started:** {self.started_at}",
            f"- **Status:** {self.status}",
            f"- **Raw data:** `{self.raw_dir}`",
            f"- **Database:** `{self.database}`",
            "",
            "## Summary",
            "",
            "| Table | Source | Rows in | Repaired | Duplicates dropped | Rejected | Loaded |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
        for t in self.tables.values():
            loaded = "" if t.rows_after_load is None else t.rows_after_load
            lines.append(f"| `{t.name}` | {t.source} | {t.rows_in} | {t.rows_repaired} | "
                         f"{t.duplicates_dropped} | {t.rows_rejected} | {loaded} |")

        lines += ["", "## Action taken on bad records", "",
                  "| Problem | Detected in | Action |", "|---|---|---|"]
        lines += [f"| {p} | {s} | {a} |" for p, s, a in BAD_RECORD_POLICY]

        lines += ["", "## Repairs and rejected records", ""]
        any_issue = False
        for t in self.tables.values():
            for r in t.repairs:
                lines.append(f"- `{t.name}` repaired: {r}")
                any_issue = True
            if t.duplicates_dropped:
                lines.append(f"- `{t.name}`: {t.duplicates_dropped} exact duplicate row(s) dropped")
                any_issue = True
            for reason, n in sorted(t.rejected_by_reason.items()):
                lines.append(f"- `{t.name}` rejected {n} row(s): {reason}")
                any_issue = True
        if not any_issue:
            lines.append("- None: every row passed validation unchanged.")

        lines += ["", "## Missingness (loaded data)", "",
                  "Columns not listed have no missing values.", ""]
        for t in self.tables.values():
            total = t.rows_valid or 1
            missing = {c: n for c, n in t.missing.items() if n}
            lines.append(f"**`{t.name}`** ({t.rows_valid} rows)")
            lines.append("")
            if missing:
                lines += ["| Column | Missing | % |", "|---|---:|---:|"]
                lines += [f"| {c} | {n} | {n / total:.2%} |" for c, n in missing.items()]
            else:
                lines.append("No missing values.")
            lines.append("")

        lines += [
            "## Re-runnability check",
            "",
            "Each run replaces table contents in one transaction. Row counts and a content",
            "checksum are taken before and after loading; on a repeat run with the same",
            "input, both must be identical.",
            "",
            "| Table | Rows before | Rows after | Checksum before | Checksum after | Result |",
            "|---|---:|---:|---|---|---|",
        ]
        for t in self.tables.values():
            if t.rows_after_load is None:
                continue
            lines.append(f"| `{t.name}` | {t.rows_before_load} | {t.rows_after_load} | "
                         f"`{t.checksum_before or '-'}` | `{t.checksum_after}` | {rerun_result(t)} |")

        if self.notes:
            lines += ["", "## Notes", ""] + [f"- {n}" for n in self.notes]
        return "\n".join(lines) + "\n"

    def write(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")


def rerun_result(t: TableQuality) -> str:
    if not t.rows_before_load:
        return "First load"
    if t.checksum_before == t.checksum_after:
        return "Unchanged (no duplicates)"
    if t.rows_before_load == t.rows_after_load:
        return "Same row count, values changed"
    return f"Row count changed by {t.rows_after_load - t.rows_before_load:+d}"


def missing_counts(df: pd.DataFrame) -> dict[str, int]:
    return {c: int(n) for c, n in df.isna().sum().items()}
