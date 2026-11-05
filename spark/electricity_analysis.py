#!/usr/bin/env python3
"""
electricity_analysis.py - Stage 2 of the PySpark pipeline.

Reads the cleaned Parquet dataset produced by spark/process_dataset.py and
prints the six required analyses:

  1. hourly consumption profile        (average kW per hour of day, 0-23)
  2. daily summary                     (kWh / average / peak per day)
  3. monthly energy trend              (kWh per calendar month)
  4. top 10 peak-usage days            (highest daily kWh)
  5. sub-metering totals               (kitchen / laundry / water-heater+AC)
  6. pairwise Pearson correlations     between global_active_power,
     global_intensity, voltage and sub_metering_1..3 (df.stat.corr)

Usage
-----
  python spark/electricity_analysis.py \
      --parquet-path data/processed/power_consumption_parquet

Local mode only; every .show() / collect() below operates on small aggregates,
never on the full 2M-row dataset.

Units: power columns are kW (minute averages) -> kWh = SUM(kW) / 60;
       sub-metering columns are Wh -> kWh = SUM(Wh) / 1000.
"""

import argparse
import itertools

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

# Columns used for the correlation matrix.
CORRELATION_COLUMNS = [
    "global_active_power",
    "global_intensity",
    "voltage",
    "sub_metering_1",
    "sub_metering_2",
    "sub_metering_3",
]


def build_spark_session(app_name: str = "electricity-analysis") -> SparkSession:
    """Local Spark session; [*] = use all available CPU cores."""
    return (
        SparkSession.builder.master("local[*]")
        .appName(app_name)
        .getOrCreate()
    )


def load_parquet(spark: SparkSession, path: str) -> DataFrame:
    """Load the cleaned dataset written by process_dataset.py."""
    return spark.read.parquet(path)


def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def hourly_profile(df: DataFrame) -> DataFrame:
    """(1) Average load per hour of the day across the whole 4-year period."""
    return (
        df.groupBy("hour")
        .agg(
            F.round(F.avg("global_active_power"), 4).alias("avg_power_kw"),
            F.round(F.sum("global_active_power") / 60, 2).alias("total_kwh"),
            F.count("*").alias("minute_readings"),
        )
        .orderBy("hour")
    )


def daily_summary(df: DataFrame) -> DataFrame:
    """(2) kWh, average and peak load per calendar day."""
    return (
        df.groupBy("date")
        .agg(
            F.round(F.sum("global_active_power") / 60, 2).alias("kwh"),
            F.round(F.avg("global_active_power"), 4).alias("avg_kw"),
            F.round(F.max("global_active_power"), 4).alias("peak_kw"),
        )
        .orderBy("date")
    )


def monthly_trend(df: DataFrame) -> DataFrame:
    """(3) Total kWh per calendar month - the seasonality view."""
    return (
        df.groupBy("year", "month")
        .agg(F.round(F.sum("global_active_power") / 60, 2).alias("kwh"))
        .orderBy("year", "month")
    )


def top_peak_days(daily: DataFrame) -> DataFrame:
    """(4) The ten days with the highest total consumption."""
    return daily.orderBy(F.desc("kwh")).limit(10)


def submetering_totals(df: DataFrame) -> "dict[str, float]":
    """(5) Grand totals per sub-meter, converted Wh -> kWh."""
    row = df.agg(
        F.round(F.sum("sub_metering_1") / 1000, 2).alias("kitchen_kwh"),
        F.round(F.sum("sub_metering_2") / 1000, 2).alias("laundry_room_kwh"),
        F.round(F.sum("sub_metering_3") / 1000, 2).alias("water_heater_ac_kwh"),
    ).collect()[0]  # single aggregated row - safe to collect
    return row.asDict()


def correlation_report(df: DataFrame) -> None:
    """(6) Pairwise Pearson correlations (df.stat.corr) between key columns."""
    pairs = itertools.combinations(CORRELATION_COLUMNS, 2)
    for col_a, col_b in pairs:
        corr = df.stat.corr(col_a, col_b)
        print(f"corr({col_a:<20}, {col_b:<20}) = {corr:+.4f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analytics over the cleaned electricity Parquet dataset."
    )
    parser.add_argument(
        "--parquet-path",
        default="data/processed/power_consumption_parquet",
        help="Path to the Parquet dataset from process_dataset.py (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spark = build_spark_session()

    df = load_parquet(spark, args.parquet_path)
    print(f"loaded Parquet from : {args.parquet_path}")
    print(f"cleaned rows        : {df.count()}")

    # (1) Hourly profile ------------------------------------------------------
    banner("1) HOURLY PROFILE - average kW and total kWh per hour of day")
    hourly_profile(df).show(24)

    # (2) Daily summary -------------------------------------------------------
    banner("2) DAILY SUMMARY - first 15 days of the dataset")
    daily = daily_summary(df)
    daily.show(15)

    # (3) Monthly trend -------------------------------------------------------
    banner("3) MONTHLY TREND - kWh per calendar month")
    monthly_trend(df).show(50)

    # (4) Top 10 peak days ----------------------------------------------------
    banner("4) TOP 10 PEAK-USAGE DAYS")
    top_peak_days(daily).show(10)

    # (5) Sub-metering totals -------------------------------------------------
    banner("5) SUB-METERING TOTALS (kWh)")
    for name, value in submetering_totals(df).items():
        print(f"{name:<22}: {value:>12} kWh")

    # (6) Correlations --------------------------------------------------------
    banner("6) PEARSON CORRELATIONS (df.stat.corr)")
    correlation_report(df)

    spark.stop()


if __name__ == "__main__":
    main()
