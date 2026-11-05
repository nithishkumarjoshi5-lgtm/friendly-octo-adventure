"""Tests for src.general_analytics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import general_analytics


# ---------------------------------------------------------------------------
# numeric_summary
# ---------------------------------------------------------------------------


class TestNumericSummary:
    def test_columns_present_and_stats_sane(self, small_df) -> None:
        summary = general_analytics.numeric_summary(small_df)
        assert list(summary.columns) == [
            "count",
            "mean",
            "median",
            "mode",
            "min",
            "max",
            "std",
            "missing",
        ]
        assert "value" in summary.index
        row = summary.loc["value"]
        assert row["count"] == 97
        assert row["missing"] == 3
        assert row["mean"] == pytest.approx(small_df["value"].mean())
        assert row["median"] == pytest.approx(small_df["value"].median())
        assert row["min"] <= row["median"] <= row["max"]
        assert row["std"] > 0

    def test_excludes_non_numeric_columns(self, small_df) -> None:
        summary = general_analytics.numeric_summary(small_df)
        assert "category" not in summary.index
        assert "timestamp" not in summary.index

    def test_all_nan_column(self) -> None:
        df = pd.DataFrame({"blank": [np.nan] * 4})
        summary = general_analytics.numeric_summary(df)
        row = summary.loc["blank"]
        assert row["count"] == 0
        assert row["missing"] == 4
        assert pd.isna(row["mean"])
        assert pd.isna(row["std"])

    def test_empty_df(self) -> None:
        assert general_analytics.numeric_summary(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# categorical_frequencies
# ---------------------------------------------------------------------------


class TestCategoricalFrequencies:
    def test_structure_and_percentages(self, small_df) -> None:
        freq = general_analytics.categorical_frequencies(small_df)
        assert set(freq) == {"category"}
        table = freq["category"]
        assert list(table.columns) == ["value", "count", "percent"]
        assert table["count"].sum() == 100
        assert table["percent"].sum() == pytest.approx(100.0)
        assert set(table["value"]) == {"alpha", "beta", "gamma"}

    def test_other_bucket_when_over_max_categories(self) -> None:
        df = pd.DataFrame({"sku": [f"s{i}" for i in range(25)]})
        table = general_analytics.categorical_frequencies(df, max_categories=10)["sku"]
        assert len(table) == 11  # 10 most frequent + OTHER
        assert table.iloc[-1]["value"] == "OTHER"
        assert table["count"].sum() == 25
        assert table.iloc[-1]["count"] == 15

    def test_no_other_bucket_when_within_limit(self) -> None:
        df = pd.DataFrame({"sku": [f"s{i}" for i in range(5)]})
        table = general_analytics.categorical_frequencies(df, max_categories=10)["sku"]
        assert len(table) == 5
        assert "OTHER" not in set(table["value"])

    def test_all_nan_series(self) -> None:
        df = pd.DataFrame({"c": pd.Series([None, None], dtype=object)})
        table = general_analytics.categorical_frequencies(df)["c"]
        assert table.empty
        assert list(table.columns) == ["value", "count", "percent"]

    def test_ignores_numeric_columns(self, small_df) -> None:
        assert "value" not in general_analytics.categorical_frequencies(small_df)

    def test_empty_df(self) -> None:
        assert general_analytics.categorical_frequencies(pd.DataFrame()) == {}


# ---------------------------------------------------------------------------
# correlation_matrix
# ---------------------------------------------------------------------------


class TestCorrelationMatrix:
    def test_shape_and_diagonal(self) -> None:
        rng = np.random.default_rng(42)
        df = pd.DataFrame(
            {name: rng.normal(size=50) for name in ("a", "b", "c")}
        )
        corr = general_analytics.correlation_matrix(df)
        assert corr.shape == (3, 3)
        assert np.allclose(np.diag(corr), 1.0)
        assert ((corr >= -1.0) & (corr <= 1.0)).all().all()

    def test_known_correlation(self) -> None:
        rng = np.random.default_rng(0)
        a = rng.normal(size=200)
        df = pd.DataFrame({"a": a, "b": a * 2.0})
        corr = general_analytics.correlation_matrix(df)
        assert corr.loc["a", "b"] == pytest.approx(1.0)

    def test_fewer_than_two_numeric_columns(self, small_df) -> None:
        df = small_df.drop(columns=["value"])
        assert general_analytics.correlation_matrix(df).empty

    def test_empty_df(self) -> None:
        assert general_analytics.correlation_matrix(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# outlier_summary
# ---------------------------------------------------------------------------


class TestOutlierSummary:
    def test_bounds_and_counts(self) -> None:
        df = pd.DataFrame({"v": [1.0] * 99 + [1000.0]})
        summary = general_analytics.outlier_summary(df)
        row = summary.loc["v"]
        assert row["n_outliers"] == 1
        assert row["lower_bound"] == row["upper_bound"] == 1.0
        assert row["outlier_pct"] == pytest.approx(1.0)

    def test_no_outliers_in_clean_data(self, small_df) -> None:
        summary = general_analytics.outlier_summary(small_df)
        assert "value" in summary.index
        assert (summary["lower_bound"] < summary["upper_bound"]).all()

    def test_all_nan_column(self) -> None:
        summary = general_analytics.outlier_summary(pd.DataFrame({"v": [np.nan] * 5}))
        row = summary.loc["v"]
        assert row["n_outliers"] == 0
        assert row["outlier_pct"] == 0.0
        assert pd.isna(row["lower_bound"])
        assert pd.isna(row["upper_bound"])

    def test_invalid_method_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported method"):
            general_analytics.outlier_summary(pd.DataFrame({"v": [1.0]}), method="zscore")

    def test_empty_df(self) -> None:
        assert general_analytics.outlier_summary(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# detect_identifier_columns
# ---------------------------------------------------------------------------


class TestDetectIdentifierColumns:
    def test_invoice_column_detected(self) -> None:
        df = pd.DataFrame(
            {
                "InvoiceNo": [f"INV{i:04d}" for i in range(50)],
                "value": list(range(50)),
                "category": ["a", "b", "c"] * 16 + ["a", "b"],
            }
        )
        assert general_analytics.detect_identifier_columns(df) == ["InvoiceNo"]

    def test_unique_non_numeric_column_detected(self) -> None:
        df = pd.DataFrame({"token": [f"t{i}" for i in range(20)]})
        assert general_analytics.detect_identifier_columns(df) == ["token"]

    def test_numeric_unique_column_not_detected(self) -> None:
        df = pd.DataFrame({"seq": list(range(100))})
        assert general_analytics.detect_identifier_columns(df) == []

    def test_low_cardinality_column_not_detected(self) -> None:
        df = pd.DataFrame({"OrderID": ["A", "A", "B"]})
        assert general_analytics.detect_identifier_columns(df) == []

    def test_all_nan_column_skipped(self) -> None:
        df = pd.DataFrame({"InvoiceNo": [np.nan, np.nan], "x": [1.0, 2.0]})
        assert general_analytics.detect_identifier_columns(df) == []

    def test_empty_df(self) -> None:
        assert general_analytics.detect_identifier_columns(pd.DataFrame()) == []
