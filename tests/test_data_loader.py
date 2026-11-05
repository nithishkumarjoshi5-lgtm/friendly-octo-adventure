"""Tests for src.data_loader."""

from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd
import pytest

from src import data_loader


# ---------------------------------------------------------------------------
# load_csv
# ---------------------------------------------------------------------------


class TestLoadCsv:
    def test_load_csv_from_path(self, tmp_csv, small_df: pd.DataFrame) -> None:
        loaded = data_loader.load_csv(tmp_csv)
        assert loaded.shape == small_df.shape
        assert list(loaded.columns) == list(small_df.columns)
        np.testing.assert_allclose(
            loaded["value"].to_numpy(float),
            small_df["value"].to_numpy(float),
            equal_nan=True,
        )

    def test_load_csv_from_file_like(self, tmp_csv) -> None:
        loaded = data_loader.load_csv(io.BytesIO(tmp_csv.read_bytes()))
        assert len(loaded) == 100

    def test_load_csv_nrows(self, tmp_csv) -> None:
        loaded = data_loader.load_csv(tmp_csv, nrows=10)
        assert len(loaded) == 10


# ---------------------------------------------------------------------------
# parse_datetime_columns
# ---------------------------------------------------------------------------


def _datetime_source_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": ["01/01/2008", "02/01/2008", "03/01/2008"],
            "Time": ["00:00:00", "12:30:59", "23:59:59"],
            "value": [1.0, 2.0, 3.0],
        }
    )


class TestParseDatetimeColumns:
    def test_creates_datetime_from_date_and_time(self) -> None:
        out = data_loader.parse_datetime_columns(_datetime_source_df())
        assert "datetime" in out.columns
        assert out["datetime"].notna().all()
        assert out.loc[1, "datetime"] == pd.Timestamp("2008-01-02 12:30:59")

    def test_unparseable_rows_become_nat(self) -> None:
        df = _datetime_source_df()
        df.loc[1, "Date"] = "99/99/2008"
        out = data_loader.parse_datetime_columns(df)
        assert pd.isna(out.loc[1, "datetime"])
        assert out.loc[[0, 2], "datetime"].notna().all()

    def test_without_date_time_columns_returns_input(self, small_df) -> None:
        out = data_loader.parse_datetime_columns(small_df)
        assert "datetime" not in out.columns

    def test_empty_df_is_graceful(self) -> None:
        out = data_loader.parse_datetime_columns(pd.DataFrame())
        assert out.empty


# ---------------------------------------------------------------------------
# get_file_metadata
# ---------------------------------------------------------------------------


class TestGetFileMetadata:
    REQUIRED_KEYS = {"filename", "size_bytes", "size_human", "extension"}

    def test_required_keys_present(self, tmp_csv) -> None:
        meta = data_loader.get_file_metadata(tmp_csv, tmp_csv.name)
        assert self.REQUIRED_KEYS <= set(meta)

    def test_size_matches_filesystem(self, tmp_csv) -> None:
        meta = data_loader.get_file_metadata(str(tmp_csv), tmp_csv.name)
        assert meta["size_bytes"] == tmp_csv.stat().st_size
        assert meta["size_bytes"] > 0

    @pytest.mark.parametrize(
        ("payload", "filename"),
        [(b"12345", "x.csv"), (bytearray(b"abc"), "y.CSV")],
    )
    def test_bytes_source(self, payload, filename) -> None:
        meta = data_loader.get_file_metadata(payload, filename)
        assert meta["size_bytes"] == len(payload)

    def test_size_human_format(self, tmp_csv) -> None:
        meta = data_loader.get_file_metadata(tmp_csv, tmp_csv.name)
        assert re.fullmatch(r"\d+(\.\d+)? (B|KB|MB|GB|TB)", meta["size_human"])

    def test_extension_lowercased(self, tmp_csv) -> None:
        meta = data_loader.get_file_metadata(tmp_csv, tmp_csv.name)
        assert meta["extension"] == "csv"


# ---------------------------------------------------------------------------
# infer_column_types
# ---------------------------------------------------------------------------


@pytest.fixture()
def typed_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "amount": [1.0, 2.5, 3.0, 4.0] * 25,
            "when": pd.date_range("2024-01-01", periods=100),
            "when_str": (
                pd.date_range("2024-01-01", periods=100, freq="h").astype(str)
            ),
            "OrderID": [f"INV-{i:04d}" for i in range(100)],
            "status": (["ok", "failed", "pending"] * 33) + ["ok"],
            "notes": [f"note {i} " + "x" * 40 for i in range(100)],
        }
    )


class TestInferColumnTypes:
    @pytest.mark.parametrize(
        ("column", "expected"),
        [
            ("amount", "numeric"),
            ("when", "datetime"),
            ("when_str", "datetime"),
            ("OrderID", "identifier"),
            ("status", "categorical"),
            ("notes", "text"),
        ],
    )
    def test_bucket_assignment(self, typed_df, column, expected) -> None:
        assert data_loader.infer_column_types(typed_df)[column] == expected

    def test_every_column_classified(self, typed_df) -> None:
        types = data_loader.infer_column_types(typed_df)
        assert set(types) == set(typed_df.columns)


# ---------------------------------------------------------------------------
# preview_data
# ---------------------------------------------------------------------------


class TestPreviewData:
    def test_n_rows(self, small_df) -> None:
        assert len(data_loader.preview_data(small_df, n=5)) == 5

    def test_default_is_10_rows(self, small_df) -> None:
        assert len(data_loader.preview_data(small_df)) == 10

    def test_n_larger_than_frame(self, small_df) -> None:
        assert len(data_loader.preview_data(small_df, n=500)) == 100
