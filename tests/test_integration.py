"""Integration tests against the bundled real datasets (skipped when absent)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src import data_loader, data_validation, electricity_analytics

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_DATA = PROJECT_ROOT / "data" / "raw" / "household_power_consumption.txt"

pytestmark = pytest.mark.skipif(
    not REAL_DATA.exists(), reason="real household dataset not present"
)

N_ROWS = 50_000


@pytest.fixture(scope="module")
def raw_head():
    return data_loader.load_csv(REAL_DATA, nrows=N_ROWS)


def _prepared(raw_head):
    normalized = data_validation.normalize_electricity_columns(raw_head)
    return data_loader.parse_datetime_columns(normalized)


def test_load_50k_rows_shape(raw_head) -> None:
    assert raw_head.shape == (N_ROWS, 9)


def test_normalize_and_parse_real_data(raw_head) -> None:
    parsed = _prepared(raw_head)
    assert "global_active_power" in parsed.columns
    assert "sub_metering_1" in parsed.columns
    assert "datetime" in parsed.columns
    assert parsed["datetime"].notna().mean() > 0.9
    assert data_validation.is_electricity_dataset(parsed)


def test_daily_summary_bounds_on_real_data(raw_head) -> None:
    daily = electricity_analytics.compute_daily_summary(_prepared(raw_head))
    assert len(daily) <= 50
    assert (daily["kwh"] >= 0).all()
    assert len(daily) >= 2  # 50k minutes must span more than one day


def test_power_stats_sane_on_real_data(raw_head) -> None:
    stats = electricity_analytics.power_stats(_prepared(raw_head))
    assert stats["count"] > 0
    assert stats["avg_kw"] > 0
    assert stats["min_kw"] <= stats["avg_kw"] <= stats["max_kw"]


def test_submetering_on_real_data(raw_head) -> None:
    sub = electricity_analytics.submetering_comparison(_prepared(raw_head))
    assert (sub["total_kwh"] >= 0).all()
    total = sub["pct_of_total"].sum()
    if total > 0:
        assert total == pytest.approx(100.0)


def test_perf_load_50k_rows_under_30s() -> None:
    start = time.monotonic()
    df = data_loader.load_csv(REAL_DATA, nrows=N_ROWS)
    elapsed = time.monotonic() - start
    assert len(df) == N_ROWS
    assert elapsed < 30.0, f"loading 50k rows took {elapsed:.1f}s"
