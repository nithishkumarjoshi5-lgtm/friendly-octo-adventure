"""Missing value and duplicate row handling utilities."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

_MISSING_STRATEGIES = {"keep", "drop_rows", "fill_mean", "fill_median", "fill_mode"}


def missing_value_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-column missing value counts and percentages (0-100, 2 decimals)."""
    total = len(df)
    records = []
    for col in df.columns:
        count = int(df[col].isna().sum())
        pct = round(count / total * 100, 2) if total else 0.0
        records.append({"column": col, "missing_count": count, "missing_pct": pct})
    return pd.DataFrame(records, columns=["column", "missing_count", "missing_pct"])


def duplicate_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """Summary of fully duplicated rows in the DataFrame."""
    total = len(df)
    dupes = int(df.duplicated().sum())
    return {
        "total_rows": total,
        "duplicate_rows": dupes,
        "duplicate_pct": round(dupes / total * 100, 2) if total else 0.0,
        "unique_rows": total - dupes,
    }


def _resolve_columns(
    df: pd.DataFrame, columns: Optional[Iterable[Any]], kind: str
) -> List[Any]:
    if columns is not None:
        selected = [c for c in columns if c in df.columns]
    else:
        selected = list(df.columns)
    if kind == "numeric":
        return [c for c in selected if pd.api.types.is_numeric_dtype(df[c])]
    if kind == "string":
        return [
            c
            for c in selected
            if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c])
        ]
    return selected


def _format_value(value: Any) -> str:
    try:
        return str(round(float(value), 4))
    except (TypeError, ValueError):
        return str(value)


def handle_missing(
    df: pd.DataFrame, strategy: str = "keep", columns: Optional[List[Any]] = None
) -> Tuple[pd.DataFrame, List[str]]:
    """Apply a missing value strategy; returns (new_df, log_messages).

    Strategies: keep, drop_rows, fill_mean, fill_median (numeric columns only),
    fill_mode (string columns only). Invalid strategy raises ValueError.
    """
    if strategy not in _MISSING_STRATEGIES:
        raise ValueError(
            f"Invalid strategy: {strategy!r}. Choose from {sorted(_MISSING_STRATEGIES)}."
        )
    result = df.copy()
    log: List[str] = []
    if strategy == "keep":
        log.append("Strategy 'keep': missing values left unchanged.")
        return result, log
    if strategy == "drop_rows":
        before = len(result)
        subset = [c for c in columns if c in result.columns] if columns else None
        result = result.dropna(subset=subset)
        dropped = before - len(result)
        log.append(f"Dropped {dropped} rows containing missing values.")
        return result, log
    if strategy in {"fill_mean", "fill_median"}:
        stat = "mean" if strategy == "fill_mean" else "median"
        for col in _resolve_columns(result, columns, "numeric"):
            missing = int(result[col].isna().sum())
            if missing == 0:
                continue
            value = result[col].mean() if stat == "mean" else result[col].median()
            result[col] = result[col].fillna(value)
            log.append(
                f"Filled {missing} missing values in '{col}' with {stat} {_format_value(value)}."
            )
        return result, log
    for col in _resolve_columns(result, columns, "string"):
        missing = int(result[col].isna().sum())
        if missing == 0:
            continue
        modes = result[col].mode(dropna=True)
        if modes.empty:
            continue
        result[col] = result[col].fillna(modes.iloc[0])
        log.append(
            f"Filled {missing} missing values in '{col}' with mode {_format_value(modes.iloc[0])}."
        )
    return result, log


def handle_duplicates(df: pd.DataFrame, strategy: str = "keep") -> Tuple[pd.DataFrame, List[str]]:
    """Keep or drop duplicate rows; returns (new_df, log_messages)."""
    if strategy not in {"keep", "drop"}:
        raise ValueError(f"Invalid strategy: {strategy!r}. Choose 'keep' or 'drop'.")
    result = df.copy()
    dupes = int(df.duplicated().sum())
    log: List[str] = []
    if strategy == "drop":
        if dupes > 0:
            result = df.drop_duplicates(keep="first")
            log.append(f"Dropped {dupes} duplicate rows (kept first occurrence).")
        else:
            log.append("No duplicate rows found; nothing dropped.")
    else:
        log.append("Strategy 'keep': duplicate rows left unchanged.")
    return result, log


def quality_warnings(df: pd.DataFrame) -> List[str]:
    """Human-readable warnings about data quality issues; empty list if clean."""
    warnings: List[str] = []
    total = len(df)
    high_missing = missing_value_summary(df)
    high_missing = high_missing[high_missing["missing_pct"] > 20]
    if not high_missing.empty:
        warnings.append(f"{len(high_missing)} columns have >20% missing values")
    dupes = int(df.duplicated().sum())
    if dupes > 0:
        warnings.append(f"{dupes:,} duplicate rows found")
    for col in df.columns:
        if total and bool(df[col].isna().all()):
            warnings.append(f"Column '{col}' is fully empty")
        elif int(df[col].nunique(dropna=True)) <= 1:
            warnings.append(f"Column '{col}' has constant value")
    return warnings
