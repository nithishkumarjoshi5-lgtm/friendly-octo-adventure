"""Loading, previewing and type-inference utilities for tabular datasets."""

from __future__ import annotations

import io
import os
import re
from typing import Any, Callable, Dict, Optional

import pandas as pd

CHUNK_SIZE = 100_000

_NA_VALUES = ["?", "", "NA", "N/A", "null"]
_DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"
_IDENTIFIER_TOKENS = {"id", "ids", "uuid", "code", "no"}


def _as_buffer(source: Any) -> Optional[io.BytesIO]:
    """Wrap upload-like objects exposing getvalue() into a seekable buffer."""
    if hasattr(source, "getvalue"):
        return io.BytesIO(source.getvalue())
    return None


def _read_csv_flexible(source: Any, **kwargs: Any) -> pd.DataFrame:
    """Read a CSV with delimiter autodetection, falling back to ','."""
    try:
        return pd.read_csv(source, sep=None, engine="python", na_values=_NA_VALUES, **kwargs)
    except Exception:
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_csv(source, sep=",", na_values=_NA_VALUES, **kwargs)


def load_csv(source: Any, nrows: Optional[int] = None) -> pd.DataFrame:
    """Load a CSV from a filesystem path or an uploaded file-like object."""
    return _read_csv_flexible(_as_buffer(source) or source, nrows=nrows)


def read_csv_chunked(
    source: Any,
    func: Callable[[pd.DataFrame], Any],
    chunk_size: int = CHUNK_SIZE,
) -> None:
    """Stream a CSV in chunks of chunk_size rows, applying func to each."""
    reader = _read_csv_flexible(_as_buffer(source) or source, chunksize=chunk_size)
    for chunk in reader:
        func(chunk)


def _human_size(num_bytes: float) -> str:
    """Format a byte count as a human-readable string."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def get_file_metadata(source: Any, filename: str) -> Dict[str, Any]:
    """Return filename, size and extension metadata for a path or upload."""
    if hasattr(source, "getvalue"):
        size = len(source.getvalue())
    elif isinstance(source, (str, os.PathLike)) and os.path.exists(os.fspath(source)):
        size = os.path.getsize(os.fspath(source))
    elif isinstance(source, (bytes, bytearray)):
        size = len(source)
    else:
        size = 0
    extension = os.path.splitext(str(filename))[1].lstrip(".").lower()
    return {
        "filename": str(filename),
        "size_bytes": int(size),
        "size_human": _human_size(size),
        "extension": extension,
    }


def _is_string_like(series: pd.Series) -> bool:
    return pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)


_NUMERIC_LIKE = r"\d+(\.\d+)?"
_DATETIME_SAMPLE = 10_000


def _datetime_candidates(series: pd.Series) -> pd.Series:
    """Non-null values as strings with numeric-looking values masked out."""
    values = series.dropna().astype(str)
    return values.mask(values.str.fullmatch(_NUMERIC_LIKE))


def _parse_rate(series: pd.Series) -> float:
    """Fraction of non-null values that parse as datetimes (0.0 when empty)."""
    candidates = _datetime_candidates(series).dropna()
    if candidates.empty:
        return 0.0
    if len(candidates) > _DATETIME_SAMPLE:
        candidates = candidates.iloc[:_DATETIME_SAMPLE]
    try:
        parsed = pd.to_datetime(candidates, format="mixed", errors="coerce")
    except Exception:
        return 0.0
    return float(parsed.notna().mean())


def _coerce_datetime(series: pd.Series) -> pd.Series:
    """Convert a string series to datetime; unparseable values become NaT."""
    try:
        parsed = pd.to_datetime(
            _datetime_candidates(series), format="mixed", errors="coerce"
        )
        result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[us]")
        result.loc[parsed.index] = parsed
        return result
    except Exception:
        return series


def parse_datetime_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Build a 'datetime' column from Date+Time pairs and coerce datetime-like columns.

    Never raises: returns the original DataFrame unchanged on any failure.
    """
    try:
        result = df.copy()
        lowered: Dict[str, Any] = {}
        for col in result.columns:
            lowered.setdefault(str(col).strip().lower(), col)
        date_col = lowered.get("date")
        time_col = lowered.get("time")
        if date_col is not None and time_col is not None:
            combined = (
                result[date_col].astype(str).str.strip()
                + " "
                + result[time_col].astype(str).str.strip()
            )
            result["datetime"] = pd.to_datetime(
                combined, format=_DATETIME_FORMAT, errors="coerce"
            )
        for col in result.columns:
            if col in (date_col, time_col):
                continue
            if _is_string_like(result[col]) and _parse_rate(result[col]) > 0.8:
                result[col] = _coerce_datetime(result[col])
        return result
    except Exception:
        return df


def _is_identifier_name(column: Any) -> bool:
    """Match column names containing id/uuid/code/no as a standalone token."""
    tokens = set()
    for chunk in re.findall(r"[A-Za-z0-9]+", str(column)):
        tokens.update(t.lower() for t in re.split(r"(?<=[a-z0-9])(?=[A-Z])", chunk))
    return bool(tokens & _IDENTIFIER_TOKENS)


def _unique_ratio(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float(series.nunique(dropna=True)) / float(series.size)


def _mean_text_length(series: pd.Series) -> float:
    values = series.dropna().astype(str)
    if values.empty:
        return 0.0
    return float(values.str.len().mean())


def infer_column_types(df: pd.DataFrame) -> Dict[str, str]:
    """Classify each column as numeric, datetime, identifier, categorical or text."""
    types: Dict[str, str] = {}
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            types[col] = "numeric"
            continue
        if pd.api.types.is_datetime64_any_dtype(series):
            types[col] = "datetime"
            continue
        if _is_string_like(series) and _parse_rate(series) > 0.8:
            types[col] = "datetime"
            continue
        ratio = _unique_ratio(series)
        if _is_identifier_name(col) and ratio > 0.9:
            types[col] = "identifier"
            continue
        if (
            _is_string_like(series)
            and ratio > 0.95
            and _mean_text_length(series) <= 32
        ):
            types[col] = "identifier"
            continue
        if _is_string_like(series) and series.nunique(dropna=True) <= 50:
            types[col] = "categorical"
            continue
        types[col] = "text"
    return types


def preview_data(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Return the first n rows of the DataFrame."""
    return df.head(n)


def load_sample_dataset(name: str, data_dir: str = "data/raw") -> pd.DataFrame:
    """Load a bundled sample dataset by name ('electricity' or 'online_retail')."""
    if name == "electricity":
        path = os.path.join(data_dir, "household_power_consumption.txt")
        return pd.read_csv(path, sep=";", na_values=["?"], low_memory=False)
    if name == "online_retail":
        path = os.path.join(data_dir, "Online Retail.xlsx")
        return pd.read_excel(path)
    raise ValueError(f"Unknown sample dataset: {name!r}. Use 'electricity' or 'online_retail'.")
