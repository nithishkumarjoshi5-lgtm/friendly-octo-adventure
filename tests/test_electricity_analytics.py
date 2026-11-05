"""Tests for src.electricity_analytics."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src import electricity_analytics


@pytest.fixture()
def week_df() -> pd.DataFrame:
    """Hourly readings spanning exactly one full week (all 7 weekdays)."""
    hours = pd.date_range("2024-01-01", periods=7 * 24, freq="h")
    return pd.DataFrame({"datetime": hours, "global_active_power": 2.0})


# ---------------------------------------------------------------------------
# power_stats / energy_kwh
# ---------------------------------------------------------------------------


class TestPowerStats:
    def test_keys_and_sanity(self, electricity_df) -> None:
        stats = electricity_analytics.power_stats(electricity_df)
        assert set(stats) == {"avg_kw", "max_kw", "min_kw", "count"}
        assert 0.5 <= stats["avg_kw"] <= 5.0
        assert stats["max_kw"] <= 5.0 + 1e-9
        assert stats["min_kw"] >= 0.5 - 1e-9
        assert stats["min_kw"] < stats["avg_kw"] < stats["max_kw"]

    def test_nan_rows_excluded(self, electricity_df) -> None:
        stats = electricity_analytics.power_stats(electricity_df)
        assert stats["count"] == 1997
        series = electricity_df["global_active_power"].dropna()
        assert stats["avg_kw"] == pytest.approx(series.mean())
        assert stats["max_kw"] == pytest.approx(series.max())

    def test_does_not_mutate_input(self, electricity_df) -> None:
        snapshot = electricity_df.copy()
        electricity_analytics.power_stats(electricity_df)
        pd.testing.assert_frame_equal(electricity_df, snapshot)


class TestEnergyKwh:
    def test_equals_sum_over_60(self, electricity_df) -> None:
        series = electricity_df["global_active_power"]
        assert electricity_analytics.energy_kwh(series) == pytest.approx(
            series.dropna().sum() / 60.0
        )

    def test_consistent_with_power_stats(self, electricity_df) -> None:
        stats = electricity_analytics.power_stats(electricity_df)
        expected = stats["avg_kw"] * stats["count"] / 60.0
        assert electricity_analytics.energy_kwh(
            electricity_df["global_active_power"]
        ) == pytest.approx(expected)

    def test_all_nan_series_gives_zero(self) -> None:
        assert electricity_analytics.energy_kwh(pd.Series([np.nan, np.nan])) == 0.0


# ---------------------------------------------------------------------------
# time-based profiles
# ---------------------------------------------------------------------------


class TestHourlyProfile:
    def test_has_all_24_hours(self, electricity_df) -> None:
        hourly = electricity_analytics.compute_hourly_profile(electricity_df)
        assert list(hourly.columns) == ["hour", "avg_kw"]
        assert len(hourly) == 24
        assert set(hourly["hour"]) == set(range(24))
        assert np.isfinite(hourly["avg_kw"]).all()
        assert hourly["avg_kw"].between(0.0, 5.0).all()


class TestDailyPattern:
    def test_seven_rows_with_weekday_names(self, week_df) -> None:
        daily = electricity_analytics.compute_daily_pattern(week_df)
        assert len(daily) == 7
        assert list(daily["weekday"]) == list(range(7))
        assert list(daily["weekday_name"]) == [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        assert np.allclose(daily["avg_kw"], 2.0)

    def test_partial_data_only_existing_days(self, electricity_df) -> None:
        daily = electricity_analytics.compute_daily_pattern(electricity_df)
        assert len(daily) == 2


class TestMonthlyPattern:
    def test_kwh_non_negative_and_consistent(self, electricity_df) -> None:
        monthly = electricity_analytics.compute_monthly_pattern(electricity_df)
        assert list(monthly.columns) == ["year_month", "kwh"]
        assert (monthly["kwh"] >= 0).all()
        assert list(monthly["year_month"]) == ["2008-01"]
        assert monthly["kwh"].iloc[0] == pytest.approx(
            electricity_analytics.energy_kwh(electricity_df["global_active_power"])
        )


class TestDailySummary:
    def test_structure_and_totals(self, electricity_df) -> None:
        daily = electricity_analytics.compute_daily_summary(electricity_df)
        assert list(daily.columns) == ["date", "kwh", "avg_kw", "max_kw"]
        assert len(daily) == 2  # 2000 minutes span two calendar days
        assert (daily["kwh"] >= 0).all()
        assert daily["kwh"].sum() == pytest.approx(
            electricity_analytics.energy_kwh(electricity_df["global_active_power"])
        )
        assert (daily["max_kw"] >= daily["avg_kw"]).all()


# ---------------------------------------------------------------------------
# sub metering / voltage / high consumption
# ---------------------------------------------------------------------------


class TestSubmeteringComparison:
    def test_pct_sums_to_100(self, electricity_df) -> None:
        sub = electricity_analytics.submetering_comparison(electricity_df)
        assert list(sub.columns) == ["sub_metering", "total_kwh", "pct_of_total"]
        assert list(sub["sub_metering"]) == [
            "sub_metering_1",
            "sub_metering_2",
            "sub_metering_3",
        ]
        assert sub["pct_of_total"].sum() == pytest.approx(100.0, rel=1e-9)
        assert (sub["total_kwh"] >= 0).all()
        assert sub["total_kwh"].iloc[0] == pytest.approx(
            electricity_df["sub_metering_1"].sum() / 1000.0
        )


class TestVoltageCurrentStats:
    def test_stats_sane(self, electricity_df) -> None:
        stats = electricity_analytics.voltage_current_stats(electricity_df)
        assert set(stats) == {"avg_voltage", "min_voltage", "max_voltage", "avg_current"}
        assert 230.0 <= stats["min_voltage"] <= stats["avg_voltage"]
        assert stats["avg_voltage"] <= stats["max_voltage"] <= 250.0
        assert stats["avg_current"] > 0


class TestHighConsumptionPeriods:
    def test_returns_top_day(self, electricity_df) -> None:
        top = electricity_analytics.high_consumption_periods(electricity_df, top_n=1)
        assert len(top) == 1
        daily = electricity_analytics.compute_daily_summary(electricity_df)
        assert top["kwh"].iloc[0] == daily["kwh"].max()

    def test_top_n_larger_than_days(self, electricity_df) -> None:
        top = electricity_analytics.high_consumption_periods(electricity_df, top_n=100)
        assert len(top) == 2


# ---------------------------------------------------------------------------
# compare_periods
# ---------------------------------------------------------------------------


class TestComparePeriods:
    def test_keys_and_values(self, electricity_df) -> None:
        result = electricity_analytics.compare_periods(
            electricity_df,
            "2008-01-01",
            "2008-01-01",
            "2008-01-02",
            "2008-01-02",
        )
        assert set(result) == {
            "period1_kwh",
            "period2_kwh",
            "period1_avg_kw",
            "period2_avg_kw",
            "pct_change",
        }
        clean = electricity_df.dropna(subset=["global_active_power"])
        p1 = clean[clean["datetime"].dt.date == pd.Timestamp("2008-01-01").date()]
        p2 = clean[clean["datetime"].dt.date == pd.Timestamp("2008-01-02").date()]
        kwh1 = p1["global_active_power"].sum() / 60.0
        kwh2 = p2["global_active_power"].sum() / 60.0
        assert result["period1_kwh"] == pytest.approx(kwh1)
        assert result["period2_kwh"] == pytest.approx(kwh2)
        assert result["period1_avg_kw"] == pytest.approx(p1["global_active_power"].mean())
        assert result["pct_change"] == pytest.approx((kwh1 - kwh2) / kwh2 * 100.0)

    def test_empty_first_window(self, electricity_df) -> None:
        result = electricity_analytics.compare_periods(
            electricity_df,
            "1999-01-01",
            "1999-01-02",
            "2008-01-01",
            "2008-01-01",
        )
        assert result["period1_kwh"] == 0.0
        assert math.isnan(result["period1_avg_kw"])


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "func",
    [
        electricity_analytics.power_stats,
        electricity_analytics.compute_hourly_profile,
        electricity_analytics.compute_daily_pattern,
        electricity_analytics.compute_monthly_pattern,
        electricity_analytics.compute_daily_summary,
    ],
    ids=lambda func: func.__name__,
)
def test_missing_power_column_raises(func, electricity_df) -> None:
    with pytest.raises(ValueError, match="global_active_power"):
        func(electricity_df.drop(columns=["global_active_power"]))


def test_compare_periods_missing_power_column_raises(electricity_df) -> None:
    with pytest.raises(ValueError, match="global_active_power"):
        electricity_analytics.compare_periods(
            electricity_df.drop(columns=["global_active_power"]),
            "2008-01-01",
            "2008-01-01",
            "2008-01-02",
            "2008-01-02",
        )


def test_submetering_missing_column_raises(electricity_df) -> None:
    with pytest.raises(ValueError, match="sub_metering_2"):
        electricity_analytics.submetering_comparison(
            electricity_df.drop(columns=["sub_metering_2"])
        )


def test_voltage_stats_missing_column_raises(electricity_df) -> None:
    with pytest.raises(ValueError, match="voltage"):
        electricity_analytics.voltage_current_stats(
            electricity_df.drop(columns=["voltage"])
        )
