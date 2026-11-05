"""Tests for src.data_validation."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

from src import data_validation


# ---------------------------------------------------------------------------
# validate_csv_upload
# ---------------------------------------------------------------------------


class TestValidateCsvUpload:
    def test_valid_path(self, tmp_csv) -> None:
        ok, reason = data_validation.validate_csv_upload(str(tmp_csv))
        assert ok is True
        assert reason == ""

    def test_missing_path(self, tmp_path) -> None:
        ok, reason = data_validation.validate_csv_upload(str(tmp_path / "nope.csv"))
        assert ok is False
        assert "not found" in reason.lower()

    def test_none_rejected(self) -> None:
        ok, reason = data_validation.validate_csv_upload(None)
        assert ok is False
        assert reason

    def test_empty_file_rejected(self, tmp_path) -> None:
        path = tmp_path / "empty.csv"
        path.write_bytes(b"")
        ok, reason = data_validation.validate_csv_upload(str(path))
        assert ok is False
        assert "empty" in reason.lower()

    def test_binary_content_rejected(self) -> None:
        ok, reason = data_validation.validate_csv_upload(io.BytesIO(b"a\x00b\x01c"))
        assert ok is False
        assert "text" in reason.lower()

    def test_valid_file_like(self) -> None:
        ok, reason = data_validation.validate_csv_upload(io.BytesIO(b"a,b\n1,2\n"))
        assert ok is True
        assert reason == ""

    def test_unsupported_object_rejected(self) -> None:
        ok, reason = data_validation.validate_csv_upload(12345)
        assert ok is False
        assert reason


# ---------------------------------------------------------------------------
# validate_dataframe
# ---------------------------------------------------------------------------


class TestValidateDataFrame:
    REQUIRED_KEYS = {
        "rows",
        "cols",
        "memory_mb",
        "completeness_pct",
        "numeric_cols",
        "categorical_cols",
        "datetime_cols",
    }

    def test_profile_keys_and_values(self, small_df) -> None:
        profile = data_validation.validate_dataframe(small_df)
        assert self.REQUIRED_KEYS == set(profile)
        assert profile["rows"] == 100
        assert profile["cols"] == 3
        assert profile["memory_mb"] > 0
        # 300 cells, 3 NaNs -> 99.0% complete
        assert profile["completeness_pct"] == 99.0
        assert profile["numeric_cols"] == ["value"]
        assert profile["categorical_cols"] == ["category"]
        assert profile["datetime_cols"] == ["timestamp"]

    def test_empty_df(self) -> None:
        profile = data_validation.validate_dataframe(pd.DataFrame())
        assert profile["rows"] == 0
        assert profile["cols"] == 0
        assert profile["completeness_pct"] == 0.0
        assert profile["numeric_cols"] == []


# ---------------------------------------------------------------------------
# normalize_electricity_columns
# ---------------------------------------------------------------------------


class TestNormalizeElectricityColumns:
    @pytest.mark.parametrize(
        ("raw", "normalized"),
        [
            ("Sub metering 1", "sub_metering_1"),
            ("Global_Active_Power", "global_active_power"),
            ("  Date  ", "date"),
            ("Time", "time"),
            ("global_reactive_power", "global_reactive_power"),
            ("sub-metering-2", "sub_metering_2"),
        ],
    )
    def test_mapping(self, raw, normalized) -> None:
        df = pd.DataFrame({raw: [1]})
        out = data_validation.normalize_electricity_columns(df)
        assert list(out.columns) == [normalized]

    def test_does_not_mutate_input(self) -> None:
        df = pd.DataFrame({"Sub metering 1": [1]})
        data_validation.normalize_electricity_columns(df)
        assert list(df.columns) == ["Sub metering 1"]

    def test_values_preserved(self) -> None:
        df = pd.DataFrame({"Sub metering 1": [10, 20]})
        out = data_validation.normalize_electricity_columns(df)
        assert out["sub_metering_1"].tolist() == [10, 20]


# ---------------------------------------------------------------------------
# is_electricity_dataset
# ---------------------------------------------------------------------------


class TestIsElectricityDataset:
    def test_true_on_normalized_electricity_columns(self, electricity_df) -> None:
        assert data_validation.is_electricity_dataset(electricity_df) is True

    def test_true_on_raw_style_columns(self) -> None:
        df = pd.DataFrame(
            {"Date": ["01/01/2008"], "Time": ["00:00:00"], "Global_active_power": [1.0]}
        )
        assert data_validation.is_electricity_dataset(df) is True

    def test_false_on_retail_like_columns(self) -> None:
        df = pd.DataFrame(
            {
                "InvoiceNo": ["A1"],
                "StockCode": ["S1"],
                "Description": ["widget"],
                "Quantity": [1],
                "InvoiceDate": ["2024-01-01"],
                "UnitPrice": [2.0],
                "CustomerID": ["C1"],
                "Country": ["France"],
            }
        )
        assert data_validation.is_electricity_dataset(df) is False

    def test_false_without_date_or_time(self) -> None:
        df = pd.DataFrame({"global_active_power": [1.0, 2.0]})
        assert data_validation.is_electricity_dataset(df) is False

    def test_false_on_empty(self) -> None:
        assert data_validation.is_electricity_dataset(pd.DataFrame()) is False
