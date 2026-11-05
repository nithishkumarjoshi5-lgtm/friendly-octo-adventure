"""Upload validation and DataFrame profiling utilities."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Tuple

import pandas as pd


def validate_csv_upload(uploaded_file: Any) -> Tuple[bool, str]:
    """Validate an uploaded file object or path; never raises.

    Returns (True, "") for a non-empty text file, else (False, reason).
    """
    try:
        if uploaded_file is None:
            return False, "No file provided."
        if hasattr(uploaded_file, "getvalue"):
            data = uploaded_file.getvalue()
            if not data:
                return False, "Uploaded file is empty."
            sample = bytes(data[:8192])
        elif isinstance(uploaded_file, (str, os.PathLike)):
            path = os.fspath(uploaded_file)
            if not os.path.exists(path):
                return False, f"File not found: {path}"
            if os.path.getsize(path) == 0:
                return False, "Uploaded file is empty."
            with open(path, "rb") as handle:
                sample = handle.read(8192)
        else:
            return False, "Unsupported file object."
        try:
            text = sample.decode("utf-8")
        except UnicodeDecodeError:
            text = sample.decode("latin-1")
        if not text.strip():
            return False, "Uploaded file is empty."
        if "\x00" in text:
            return False, "File does not appear to be a text or CSV file."
        return True, ""
    except Exception as exc:
        return False, f"Could not validate file: {exc}"


def validate_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
    """Profile a DataFrame: shape, memory, completeness and column type lists."""
    rows, cols = df.shape
    total_cells = rows * cols
    non_null = int(df.notna().sum().sum())
    completeness = round(non_null / total_cells * 100, 2) if total_cells else 0.0
    numeric_cols = [
        c
        for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c])
        and not pd.api.types.is_datetime64_any_dtype(df[c])
    ]
    categorical_cols = [
        c
        for c in df.columns
        if pd.api.types.is_object_dtype(df[c])
        or pd.api.types.is_string_dtype(df[c])
        or isinstance(df[c].dtype, pd.CategoricalDtype)
    ]
    datetime_cols = [
        c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])
    ]
    return {
        "rows": int(rows),
        "cols": int(cols),
        "memory_mb": float(df.memory_usage(deep=True).sum()) / (1024 * 1024),
        "completeness_pct": completeness,
        "numeric_cols": numeric_cols,
        "categorical_cols": categorical_cols,
        "datetime_cols": datetime_cols,
    }


def _normalize_name(name: Any) -> str:
    """Lowercase, strip, and replace spaces/dashes with underscores."""
    return re.sub(r"[\s\-]+", "_", str(name).strip().lower())


def normalize_electricity_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with normalized column names (e.g. 'Sub metering 1' -> 'sub_metering_1')."""
    result = df.copy()
    result.columns = [_normalize_name(c) for c in result.columns]
    return result


def is_electricity_dataset(df: pd.DataFrame) -> bool:
    """True when the DataFrame has global_active_power plus a date/time column."""
    names = {_normalize_name(c) for c in df.columns}
    return "global_active_power" in names and bool(names & {"date", "time", "datetime"})
