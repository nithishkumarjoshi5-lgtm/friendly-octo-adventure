"""Tests for src.data_cleaning."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import data_cleaning


# ---------------------------------------------------------------------------
# missing_value_summary
# ---------------------------------------------------------------------------


class TestMissingValueSummary:
    def test_columns_and_values(self, small_df) -> None:
        summary = data_cleaning.missing_value_summary(small_df)
        assert list(summary.columns) == ["column", "missing_count", "missing_pct"]
        row = summary.set_index("column").loc["value"]
        assert row["missing_count"] == 3
        assert row["missing_pct"] == 3.0
        assert (summary["missing_pct"] <= 100.0).all()
        assert summary.set_index("column").loc["category", "missing_count"] == 0

    def test_all_nan_column_is_full_missing(self) -> None:
        df = pd.DataFrame({"blank": [np.nan] * 5, "x": [1.0, 2.0, 3.0, 4.0, 5.0]})
        summary = data_cleaning.missing_value_summary(df).set_index("column")
        assert summary.loc["blank", "missing_count"] == 5
        assert summary.loc["blank", "missing_pct"] == 100.0

    def test_empty_df(self) -> None:
        summary = data_cleaning.missing_value_summary(pd.DataFrame())
        assert summary.empty
        assert list(summary.columns) == ["column", "missing_count", "missing_pct"]


# ---------------------------------------------------------------------------
# duplicate_summary / handle_duplicates
# ---------------------------------------------------------------------------


class TestDuplicateSummary:
    def test_counts(self) -> None:
        df = pd.DataFrame({"a": [1, 1, 1, 2]})
        assert data_cleaning.duplicate_summary(df) == {
            "total_rows": 4,
            "duplicate_rows": 2,
            "duplicate_pct": 50.0,
            "unique_rows": 2,
        }

    def test_no_duplicates(self, small_df) -> None:
        summary = data_cleaning.duplicate_summary(small_df)
        assert summary["duplicate_rows"] == 0
        assert summary["unique_rows"] == 100

    def test_empty_df(self) -> None:
        summary = data_cleaning.duplicate_summary(pd.DataFrame())
        assert summary["total_rows"] == 0
        assert summary["duplicate_pct"] == 0.0


class TestHandleDuplicates:
    def test_drop_removes_duplicates(self) -> None:
        df = pd.DataFrame({"a": [1, 1, 2, 2], "b": [1, 1, 3, 3]})
        out, log = data_cleaning.handle_duplicates(df, strategy="drop")
        assert len(out) == 2
        assert any("Dropped 2" in msg for msg in log)

    def test_keep_leaves_rows(self) -> None:
        df = pd.DataFrame({"a": [1, 1]})
        out, log = data_cleaning.handle_duplicates(df, strategy="keep")
        assert len(out) == 2
        assert log

    def test_drop_with_no_duplicates(self) -> None:
        df = pd.DataFrame({"a": [1, 2]})
        out, log = data_cleaning.handle_duplicates(df, strategy="drop")
        assert len(out) == 2
        assert "No duplicate" in log[0]

    @pytest.mark.parametrize("strategy", ["remove", "DROP", "", None])
    def test_invalid_strategy_raises(self, strategy) -> None:
        with pytest.raises(ValueError, match="Invalid strategy"):
            data_cleaning.handle_duplicates(pd.DataFrame({"a": [1]}), strategy=strategy)


# ---------------------------------------------------------------------------
# handle_missing
# ---------------------------------------------------------------------------


class TestHandleMissing:
    def test_keep_leaves_missing_untouched(self, small_df) -> None:
        out, log = data_cleaning.handle_missing(small_df, strategy="keep")
        assert out["value"].isna().sum() == 3
        assert log

    def test_drop_rows_removes_rows_with_nans(self, small_df) -> None:
        out, log = data_cleaning.handle_missing(small_df, strategy="drop_rows")
        assert len(out) == 97
        assert not out.isna().any().any()
        assert "Dropped 3" in log[0]

    def test_fill_mean_restores_completeness(self, small_df) -> None:
        expected = small_df["value"].mean()
        out, log = data_cleaning.handle_missing(
            small_df, strategy="fill_mean", columns=["value"]
        )
        assert out["value"].isna().sum() == 0
        assert out["value"].mean() == pytest.approx(expected)
        assert any("'value'" in msg for msg in log)

    def test_fill_median(self, small_df) -> None:
        expected = small_df["value"].median()
        out, _ = data_cleaning.handle_missing(
            small_df, strategy="fill_median", columns=["value"]
        )
        assert out["value"].isna().sum() == 0
        assert out["value"].median() == pytest.approx(expected)

    def test_fill_mode_fills_strings(self) -> None:
        df = pd.DataFrame({"city": ["Paris", None, "Paris", "Rome"]})
        out, log = data_cleaning.handle_missing(df, strategy="fill_mode")
        assert out["city"].isna().sum() == 0
        assert (out["city"] == "Paris").sum() == 3
        assert log

    def test_fill_ignores_non_numeric_columns(self, small_df) -> None:
        out, _ = data_cleaning.handle_missing(small_df, strategy="fill_mean")
        assert out["value"].isna().sum() == 0
        assert out["timestamp"].dtype.kind == "M"

    @pytest.mark.parametrize("strategy", ["drop", "mean", "interpolate", ""])
    def test_invalid_strategy_raises(self, strategy) -> None:
        with pytest.raises(ValueError, match="Invalid strategy"):
            data_cleaning.handle_missing(pd.DataFrame({"a": [1.0, np.nan]}), strategy=strategy)

    def test_all_nan_column_fill_mean_does_not_crash(self) -> None:
        df = pd.DataFrame({"blank": [np.nan, np.nan]})
        out, log = data_cleaning.handle_missing(df, strategy="fill_mean")
        assert len(out) == 2
        assert log

    def test_empty_df_each_strategy(self) -> None:
        for strategy in ("keep", "drop_rows", "fill_mean", "fill_median", "fill_mode"):
            out, log = data_cleaning.handle_missing(pd.DataFrame(), strategy=strategy)
            assert out.empty


# ---------------------------------------------------------------------------
# quality_warnings
# ---------------------------------------------------------------------------


class TestQualityWarnings:
    def test_flags_issues(self) -> None:
        df = pd.DataFrame(
            {"sparse": [np.nan] * 6 + [1.0, 1.0], "constant": [7] * 8}
        )
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        warnings = data_cleaning.quality_warnings(df)
        text = "\n".join(warnings)
        assert ">20% missing" in text
        assert "duplicate" in text
        assert "constant" in text
        assert "fully empty" not in text

    def test_clean_df_has_no_warnings(self) -> None:
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        assert data_cleaning.quality_warnings(df) == []

    def test_fully_empty_column_flagged(self) -> None:
        df = pd.DataFrame({"blank": [np.nan, np.nan], "x": [1.0, 2.0]})
        text = "\n".join(data_cleaning.quality_warnings(df))
        assert "'blank' is fully empty" in text

    def test_empty_df(self) -> None:
        assert data_cleaning.quality_warnings(pd.DataFrame()) == []
