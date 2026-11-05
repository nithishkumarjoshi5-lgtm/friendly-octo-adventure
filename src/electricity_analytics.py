"""Analytics for the household electricity consumption dataset.

Contract: input DataFrames are normalized and parsed, with a ``datetime``
datetime64 column and lowercase columns ``global_active_power`` (kW,
minute-level instantaneous), ``global_reactive_power`` (kW), ``voltage`` (V),
``global_intensity`` (A), and ``sub_metering_1..3`` (Wh). All functions guard
against missing columns, drop rows with null ``global_active_power`` for their
computations, and never mutate the caller's DataFrame.
"""

from __future__ import annotations

import pandas as pd

_REQUIRED_BASE = ["datetime", "global_active_power"]
_REQUIRED_SUBMETERING = ["sub_metering_1", "sub_metering_2", "sub_metering_3"]
_REQUIRED_VOLTAGE_CURRENT = ["voltage", "global_intensity"]


def _require(df: pd.DataFrame, columns: list[str], context: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"{context}: missing required column(s): {', '.join(missing)}"
        )


def _clean_power(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(subset=["global_active_power"])


def power_stats(df: pd.DataFrame) -> dict:
    """Basic statistics for global active power (kW)."""
    _require(df, _REQUIRED_BASE, "power_stats")
    series = _clean_power(df)["global_active_power"]
    return {
        "avg_kw": float(series.mean()),
        "max_kw": float(series.max()),
        "min_kw": float(series.min()),
        "count": int(series.count()),
    }


def energy_kwh(readings: pd.Series) -> float:
    """Energy in kWh for kW readings sampled at 1-minute intervals.

    Assumes each reading is the instantaneous average power over the
    following minute, so energy = sum(kW) * (1/60) h = sum(kW) / 60 kWh.
    """
    return float(readings.dropna().sum() / 60.0)


def compute_hourly_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Average kW per hour of day (0-23)."""
    _require(df, _REQUIRED_BASE, "compute_hourly_profile")
    clean = _clean_power(df)
    grouped = clean.groupby(clean["datetime"].dt.hour)["global_active_power"].mean()
    return pd.DataFrame(
        {"hour": grouped.index.astype(int), "avg_kw": grouped.to_numpy(float)}
    ).reset_index(drop=True)


def compute_daily_pattern(df: pd.DataFrame) -> pd.DataFrame:
    """Average kW per weekday (0=Monday ... 6=Sunday)."""
    _require(df, _REQUIRED_BASE, "compute_daily_pattern")
    clean = _clean_power(df)
    weekday = clean["datetime"].dt.weekday
    grouped = clean.groupby(weekday)["global_active_power"].agg(["mean", "size"])
    names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
    return pd.DataFrame(
        {
            "weekday": grouped.index.astype(int),
            "weekday_name": grouped.index.map(names),
            "avg_kw": grouped["mean"].to_numpy(float),
        }
    ).reset_index(drop=True)


def compute_monthly_pattern(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly energy consumption in kWh."""
    _require(df, _REQUIRED_BASE, "compute_monthly_pattern")
    clean = _clean_power(df)
    month = clean["datetime"].dt.to_period("M")
    kwh = clean.groupby(month)["global_active_power"].sum() / 60.0
    return pd.DataFrame(
        {
            "year_month": kwh.index.astype(str),
            "kwh": kwh.to_numpy(float),
        }
    )


def compute_daily_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-day energy (kWh), average power (kW) and peak power (kW)."""
    _require(df, _REQUIRED_BASE, "compute_daily_summary")
    clean = _clean_power(df)
    date = clean["datetime"].dt.date
    grouped = clean.groupby(date)["global_active_power"].agg(
        kwh=lambda s: s.sum() / 60.0, avg_kw="mean", max_kw="max"
    )
    grouped = grouped.reset_index().rename(columns={"datetime": "date"})
    return grouped[["date", "kwh", "avg_kw", "max_kw"]]


def submetering_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """Total kWh per sub meter and their share of the total."""
    _require(df, _REQUIRED_SUBMETERING, "submetering_comparison")
    totals = {
        col: float(pd.to_numeric(df[col], errors="coerce").sum()) / 1000.0
        for col in _REQUIRED_SUBMETERING
    }
    grand_total = sum(totals.values())
    rows = [
        {
            "sub_metering": col,
            "total_kwh": kwh,
            "pct_of_total": (kwh / grand_total * 100.0) if grand_total > 0 else 0.0,
        }
        for col, kwh in totals.items()
    ]
    return pd.DataFrame(rows, columns=["sub_metering", "total_kwh", "pct_of_total"])


def voltage_current_stats(df: pd.DataFrame) -> dict:
    """Summary statistics for voltage (V) and current (A)."""
    _require(df, _REQUIRED_VOLTAGE_CURRENT, "voltage_current_stats")
    voltage = pd.to_numeric(df["voltage"], errors="coerce").dropna()
    current = pd.to_numeric(df["global_intensity"], errors="coerce").dropna()
    return {
        "avg_voltage": float(voltage.mean()),
        "min_voltage": float(voltage.min()),
        "max_voltage": float(voltage.max()),
        "avg_current": float(current.mean()),
    }


def high_consumption_periods(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Top days by energy consumption, from the daily summary."""
    daily = compute_daily_summary(df)
    return daily.sort_values("kwh", ascending=False).head(top_n).reset_index(drop=True)


def compare_periods(
    df: pd.DataFrame, start1: str, end1: str, start2: str, end2: str
) -> dict:
    """Compare energy and average power between two inclusive date ranges."""
    _require(df, _REQUIRED_BASE, "compare_periods")
    clean = _clean_power(df)
    dt = clean["datetime"]

    def _window(start: str, end: str) -> pd.DataFrame:
        mask = (dt >= pd.Timestamp(start)) & (dt <= pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(minutes=1))
        return clean.loc[mask]

    p1 = _window(start1, end1)
    p2 = _window(start2, end2)

    period1_kwh = float(p1["global_active_power"].sum() / 60.0)
    period2_kwh = float(p2["global_active_power"].sum() / 60.0)
    period1_avg = float(p1["global_active_power"].mean()) if not p1.empty else float("nan")
    period2_avg = float(p2["global_active_power"].mean()) if not p2.empty else float("nan")
    pct_change = (
        (period1_kwh - period2_kwh) / period2_kwh * 100.0 if period2_kwh else float("nan")
    )
    return {
        "period1_kwh": period1_kwh,
        "period2_kwh": period2_kwh,
        "period1_avg_kw": period1_avg,
        "period2_avg_kw": period2_avg,
        "pct_change": pct_change,
    }
