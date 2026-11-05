"""General-purpose analytics helpers for exploratory data analysis."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

_IDENTIFIER_PATTERN = re.compile(r"(^|_)id$|(^|_)no$|(^|_)code$|uuid|invoice")


def numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summary statistics for every numeric column.

    Returns a DataFrame indexed by column name with columns:
    count, mean, median, mode, min, max, std, missing.
    """
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.empty:
        return pd.DataFrame()

    rows: dict[str, dict[str, float]] = {}
    for col in numeric_df.columns:
        series = numeric_df[col]
        modes = series.mode(dropna=True)
        rows[col] = {
            "count": int(series.count()),
            "mean": float(series.mean()) if series.count() else np.nan,
            "median": float(series.median()) if series.count() else np.nan,
            "mode": float(modes.iloc[0]) if not modes.empty else np.nan,
            "min": float(series.min()) if series.count() else np.nan,
            "max": float(series.max()) if series.count() else np.nan,
            "std": float(series.std()) if series.count() > 1 else np.nan,
            "missing": int(series.isna().sum()),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def categorical_frequencies(
    df: pd.DataFrame, max_categories: int = 20
) -> dict[str, pd.DataFrame]:
    """Value counts per object- or string-typed column.

    Each column maps to a DataFrame with columns ``value``, ``count``,
    ``percent``, capped at the ``max_categories`` most frequent values plus
    an "OTHER" row summing the remainder when more values exist.
    """
    result: dict[str, pd.DataFrame] = {}
    for col in df.columns:
        series = df[col]
        if not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):
            continue

        total = int(series.count())
        if total == 0:
            result[col] = pd.DataFrame(
                {"value": pd.Series(dtype=object), "count": pd.Series(dtype=int), "percent": pd.Series(dtype=float)}
            )
            continue

        counts = series.value_counts(dropna=True)
        top = counts.head(max_categories)
        other = counts.iloc[max_categories:].sum()
        rows: list[dict] = [
            {"value": value, "count": int(count), "percent": count / total * 100.0}
            for value, count in top.items()
        ]
        if other > 0:
            rows.append({"value": "OTHER", "count": int(other), "percent": other / total * 100.0})
        result[col] = pd.DataFrame(rows, columns=["value", "count", "percent"])
    return result


def correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation matrix over numeric columns (empty if <2)."""
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.shape[1] < 2:
        return pd.DataFrame()
    return numeric_df.corr(numeric_only=True)


def outlier_summary(df: pd.DataFrame, method: str = "iqr") -> pd.DataFrame:
    """Outlier counts and IQR bounds per numeric column.

    Bounds follow the standard rule: Q1 - 1.5*IQR and Q3 + 1.5*IQR.
    """
    if method != "iqr":
        raise ValueError(f"Unsupported method: {method!r}. Only 'iqr' is available.")

    numeric_df = df.select_dtypes(include=[np.number])
    rows: dict[str, dict[str, float]] = {}
    for col in numeric_df.columns:
        series = numeric_df[col].dropna()
        count = len(series)
        if count == 0:
            rows[col] = {
                "n_outliers": 0,
                "outlier_pct": 0.0,
                "lower_bound": np.nan,
                "upper_bound": np.nan,
            }
            continue

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        n_outliers = int(((series < lower) | (series > upper)).sum())
        rows[col] = {
            "n_outliers": n_outliers,
            "outlier_pct": n_outliers / count * 100.0,
            "lower_bound": float(lower),
            "upper_bound": float(upper),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def detect_identifier_columns(df: pd.DataFrame) -> list[str]:
    """Detect columns that look like identifiers.

    A column qualifies if it has unique_ratio > 0.9 and its name matches
    common identifier patterns (id/no/code/uuid/invoice), or if it is
    non-numeric with unique_ratio > 0.95.
    """
    identified: list[str] = []
    for col in df.columns:
        series = df[col]
        n_unique = series.nunique(dropna=True)
        n_non_null = int(series.count())
        if n_non_null == 0:
            continue
        unique_ratio = n_unique / n_non_null
        if _IDENTIFIER_PATTERN.search(col.lower()) and unique_ratio > 0.9:
            identified.append(col)
        elif unique_ratio > 0.95 and not pd.api.types.is_numeric_dtype(series):
            identified.append(col)
    return identified
