"""In-memory report exporters.

Contract: every public function returns ``bytes`` (UTF-8 text payloads) and
never writes to disk. All functions tolerate missing or empty inputs without
raising.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def export_dataframe_csv(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to CSV bytes (no index)."""
    if df is None:
        return b""
    return df.to_csv(index=False).encode("utf-8")


def _render_text_value(value) -> str:
    if isinstance(value, pd.DataFrame):
        return value.to_string() if not value.empty else "(empty)"
    if isinstance(value, pd.Series):
        return value.to_string() if len(value) else "(empty)"
    if isinstance(value, dict):
        return "\n".join(f"{k}: {v}" for k, v in value.items()) or "(empty)"
    if isinstance(value, (list, tuple)):
        return "\n".join(f"- {item}" for item in value) or "(empty)"
    return str(value)


def export_stats_report(stats: dict) -> bytes:
    """Render a plain-text report with ``# <name>`` sections and blank-line separation."""
    sections = [
        f"# {name}\n{_render_text_value(value)}"
        for name, value in (stats or {}).items()
    ]
    return "\n\n".join(sections).encode("utf-8")


def export_quality_report(quality: dict) -> bytes:
    """Render a readable data-quality text report; tolerates missing keys."""
    quality = quality or {}
    lines = ["# Data Quality Report", ""]

    if "rows" in quality:
        lines.append(f"Rows: {quality['rows']}")
    if "cols" in quality:
        lines.append(f"Columns: {quality['cols']}")
    if "completeness_pct" in quality:
        lines.append(f"Completeness: {quality['completeness_pct']}%")

    missing = quality.get("missing")
    if isinstance(missing, pd.DataFrame) and not missing.empty:
        lines.extend(["", "## Missing Values", "", missing.to_string()])

    duplicates = quality.get("duplicates")
    if isinstance(duplicates, dict) and duplicates:
        lines.extend(["", "## Duplicates", ""])
        lines.extend(f"{key}: {value}" for key, value in duplicates.items())

    warnings = quality.get("warnings")
    if isinstance(warnings, (list, tuple)) and warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)

    return "\n".join(lines).encode("utf-8")


def _markdown_table(value) -> str:
    if isinstance(value, (pd.DataFrame, pd.Series)):
        try:
            return value.to_markdown()
        except Exception:
            return value.to_string()
    return str(value)


def _markdown_block(value, indent: bool = False) -> list[str]:
    """Render an arbitrary value as Markdown lines."""
    if isinstance(value, pd.DataFrame):
        return [_markdown_table(value), ""] if not value.empty else []
    if isinstance(value, pd.Series):
        return [_markdown_table(value), ""] if len(value) else []
    if isinstance(value, dict):
        if not value:
            return []
        lines = []
        for key, item in value.items():
            if isinstance(item, (pd.DataFrame, pd.Series, dict, list, tuple)):
                lines.append(f"**{key}:**")
                lines.append("")
                lines.extend(_markdown_block(item))
            else:
                lines.append(f"- **{key}**: {item}")
        lines.append("")
        return lines
    if isinstance(value, (list, tuple)):
        if not value:
            return []
        return [f"- {item}" for item in value] + [""]
    return [str(value), ""]


def export_consolidated_report(ctx: dict) -> bytes:
    """Render a Markdown consolidated report; never raises on missing entries."""
    ctx = ctx or {}
    lines = [f"# {ctx.get('title') or 'Consolidated Report'}", ""]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.extend([f"_Generated: {timestamp}_", ""])

    overview = ctx.get("overview")
    if isinstance(overview, dict) and overview:
        lines.extend(["## Dataset Overview", ""])
        lines.extend(f"- **{key}**: {value}" for key, value in overview.items())
        lines.append("")

    stats = ctx.get("stats")
    if isinstance(stats, dict) and stats:
        lines.extend(["## Statistics", ""])
        for name, value in stats.items():
            lines.extend([f"### {name}", "", _markdown_table(value), ""])

    quality = ctx.get("quality")
    if isinstance(quality, dict) and quality:
        lines.extend(["## Data Quality", ""])
        lines.extend(_markdown_block(quality))

    electricity = ctx.get("electricity")
    if electricity is not None and (not isinstance(electricity, (dict, list, tuple, str)) or electricity):
        lines.extend(["## Electricity Findings", ""])
        lines.extend(_markdown_block(electricity))

    return "\n".join(lines).encode("utf-8")
