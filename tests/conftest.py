"""Shared fixtures for the analytics test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

N_SMALL = 100
N_ELEC = 2000


@pytest.fixture()
def small_df() -> pd.DataFrame:
    """100 rows: one numeric column with NaNs, one categorical, one datetime."""
    rng = np.random.default_rng(42)
    values = rng.normal(loc=50.0, scale=10.0, size=N_SMALL)
    values[[5, 20, 77]] = np.nan
    return pd.DataFrame(
        {
            "value": values,
            "category": rng.choice(["alpha", "beta", "gamma"], size=N_SMALL),
            "timestamp": pd.date_range("2024-01-01", periods=N_SMALL, freq="D"),
        }
    )


@pytest.fixture()
def electricity_df() -> pd.DataFrame:
    """2000 minute-level readings with a sinusoidal power signal (0.5-5 kW)."""
    rng = np.random.default_rng(7)
    t = np.arange(N_ELEC)
    power = 2.75 + 2.25 * np.sin(2.0 * np.pi * t / 1440.0)
    power[[100, 500, 900]] = np.nan
    voltage = rng.uniform(230.0, 250.0, size=N_ELEC)
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2008-01-01", periods=N_ELEC, freq="min"),
            "global_active_power": power,
            "global_reactive_power": rng.uniform(0.0, 0.5, size=N_ELEC),
            "voltage": voltage,
            "global_intensity": power * 1000.0 / voltage,
            "sub_metering_1": rng.uniform(0.0, 40.0, size=N_ELEC),
            "sub_metering_2": rng.uniform(0.0, 30.0, size=N_ELEC),
            "sub_metering_3": rng.uniform(0.0, 20.0, size=N_ELEC),
        }
    )


@pytest.fixture()
def tmp_csv(tmp_path: Path, small_df: pd.DataFrame) -> Path:
    """The small fixture DataFrame persisted as a CSV file."""
    path = tmp_path / "small.csv"
    small_df.to_csv(path, index=False)
    return path
