"""Tests for src.export_reports."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

from src import export_reports


# ---------------------------------------------------------------------------
# export_dataframe_csv
# ---------------------------------------------------------------------------


class TestExportDataframeCsv:
    def test_round_trip(self) -> None:
        df = pd.DataFrame(
            {"a": [1, 2, 3], "b": ["x", "y", "z"], "c": [1.5, 2.5, np.nan]}
        )
        out = export_reports.export_dataframe_csv(df)
        assert isinstance(out, bytes)
        assert out
        back = pd.read_csv(io.BytesIO(out))
        pd.testing.assert_frame_equal(back, df)

    def test_no_index_column(self) -> None:
        df = pd.DataFrame({"a": [1, 2]}, index=["r1", "r2"])
        out = export_reports.export_dataframe_csv(df)
        assert not out.decode("utf-8").startswith(",")

    def test_empty_df(self) -> None:
        out = export_reports.export_dataframe_csv(pd.DataFrame())
        assert isinstance(out, bytes)

    def test_none_df_tolerated(self) -> None:
        assert export_reports.export_dataframe_csv(None) == b""


# ---------------------------------------------------------------------------
# export_stats_report
# ---------------------------------------------------------------------------


class TestExportStatsReport:
    def test_renders_dict_series_and_scalar_sections(self) -> None:
        stats = {
            "power": {"avg_kw": 2.5, "max_kw": 5.0},
            "summary": pd.DataFrame({"v": [1, 2, 3]}),
            "note": "hello",
        }
        text = export_reports.export_stats_report(stats).decode("utf-8")
        assert "# power" in text
        assert "avg_kw: 2.5" in text
        assert "# summary" in text
        assert "# note" in text and "hello" in text

    def test_series_section(self) -> None:
        stats = {"counts": pd.Series([1, 2], name="counts")}
        out = export_reports.export_stats_report(stats)
        assert b"# counts" in out
        assert out

    def test_empty_dict_tolerated(self) -> None:
        assert export_reports.export_stats_report({}) == b""

    def test_none_tolerated(self) -> None:
        assert export_reports.export_stats_report(None) == b""


# ---------------------------------------------------------------------------
# export_quality_report
# ---------------------------------------------------------------------------


class TestExportQualityReport:
    def test_full_quality_payload(self) -> None:
        quality = {
            "rows": 100,
            "cols": 3,
            "completeness_pct": 99.0,
            "missing": pd.DataFrame(
                {"column": ["value"], "missing_count": [3], "missing_pct": [3.0]}
            ),
            "duplicates": {"duplicate_rows": 2, "duplicate_pct": 2.0},
            "warnings": ["2 duplicate rows found"],
        }
        text = export_reports.export_quality_report(quality).decode("utf-8")
        assert "# Data Quality Report" in text
        assert "Rows: 100" in text
        assert "Columns: 3" in text
        assert "Completeness: 99.0%" in text
        assert "## Missing Values" in text
        assert "## Duplicates" in text
        assert "## Warnings" in text
        assert "- 2 duplicate rows found" in text

    def test_partial_payload_renders_header(self) -> None:
        out = export_reports.export_quality_report({"rows": 5})
        assert out.startswith(b"# Data Quality Report")
        assert b"Rows: 5" in out

    def test_empty_dict_tolerated(self) -> None:
        out = export_reports.export_quality_report({})
        assert isinstance(out, bytes)
        assert out  # header line is always rendered


# ---------------------------------------------------------------------------
# export_consolidated_report
# ---------------------------------------------------------------------------


class TestExportConsolidatedReport:
    def test_full_context(self) -> None:
        ctx = {
            "title": "Demo Report",
            "overview": {"rows": 10, "cols": 2},
            "stats": {"numeric": pd.DataFrame({"a": [1.0, 2.0]})},
            "quality": {"rows": 10, "warnings": ["dupes found"]},
            "electricity": {"avg_kw": 2.0, "max_kw": 4.0},
        }
        out = export_reports.export_consolidated_report(ctx)
        text = out.decode("utf-8")
        assert out.startswith(b"# Demo Report")
        assert "## Dataset Overview" in text
        assert "## Statistics" in text
        assert "## Data Quality" in text
        assert "## Electricity Findings" in text
        assert "_Generated:" in text

    def test_minimal_context_uses_default_title(self) -> None:
        out = export_reports.export_consolidated_report({})
        assert out.startswith(b"# Consolidated Report")

    def test_none_context_tolerated(self) -> None:
        out = export_reports.export_consolidated_report(None)
        assert isinstance(out, bytes)
        assert out

    def test_markdown_renders_dataframes_without_crashing(self) -> None:
        ctx = {
            "stats": {"numeric": pd.DataFrame({"a": [1.0], "b": [2.0]})},
            "quality": {"missing": pd.DataFrame({"column": ["a"], "missing_pct": [1.0]})},
        }
        out = export_reports.export_consolidated_report(ctx)
        assert b"## Statistics" in out
        assert b"a" in out
