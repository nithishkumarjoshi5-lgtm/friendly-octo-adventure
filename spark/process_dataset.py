#!/usr/bin/env python3
"""
process_dataset.py - Stage 1 of the PySpark pipeline.

Reads the raw UCI "Individual Household Electric Power Consumption" text file,
cleans it, derives calendar features, and writes:

  1. <output>/power_consumption_parquet   the cleaned dataset as Parquet
     (columnar format - this is what electricity_analysis.py and the dashboard
     read back),
  2. <output>/hourly_aggregates.csv       per (day, hour) energy summary,
  3. <output>/daily_aggregates.csv        per day energy summary.

Dataset notes
-------------
* separator ';', one row per minute, ~2.07 million rows (Dec 2006 - Nov 2010).
* missing values are the literal string '?'; the CSV reader maps them to null
  via the nullValue option, and we drop those rows afterwards.
* Global_*_power columns are kW (minute averages), Sub_metering_* are Wh.
  One minute = 1/60 h, so energy per row = kW / 60 kWh.

Usage
-----
  python spark/process_dataset.py \
      --input  data/raw/household_power_consumption.txt \
      --output data/processed

Runs in local mode (local[*] = one Spark context using every CPU core), so it
needs only a JVM + `pip install pyspark` - no cluster required. Only tiny
aggregates are printed/brought to the driver; the 2M-row dataset itself is
never collect()-ed.
"""

import argparse

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

# Explicit schema instead of inferSchema: the file is huge, inference would
# trigger an extra full pass, and '?' values would silently mis-type columns.
RAW_SCHEMA = StructType(
    [
        StructField("date", StringType(), True),                  # dd/mm/yyyy
        StructField("time", StringType(), True),                  # hh:mm:ss
        StructField("global_active_power", DoubleType(), True),   # kW
        StructField("global_reactive_power", DoubleType(), True), # kW
        StructField("voltage", DoubleType(), True),               # V
        StructField("global_intensity", DoubleType(), True),      # A
        StructField("sub_metering_1", DoubleType(), True),        # Wh
        StructField("sub_metering_2", DoubleType(), True),        # Wh
        StructField("sub_metering_3", DoubleType(), True),        # Wh
    ]
)

# Columns that may carry the '?' placeholder in the raw file.
NUMERIC_COLUMNS = [
    "global_active_power",
    "global_reactive_power",
    "voltage",
    "global_intensity",
    "sub_metering_1",
    "sub_metering_2",
    "sub_metering_3",
]


def build_spark_session(app_name: str = "electricity-process-dataset") -> SparkSession:
    """Local Spark session; [*] = use all available CPU cores."""
    return (
        SparkSession.builder.master("local[*]")
        .appName(app_name)
        .getOrCreate()
    )


def load_raw_data(spark: SparkSession, path: str) -> DataFrame:
    """Read the raw ';'-separated txt, treating '?' as NULL (nullValue)."""
    return (
        spark.read.option("header", True)   # first line holds column names
        .option("sep", ";")                 # semicolon-separated
        .option("nullValue", "?")           # dataset's missing marker -> null
        .schema(RAW_SCHEMA)
        .csv(path)                          # works fine for .txt files
    )


def clean_and_enrich(df: DataFrame) -> DataFrame:
    """Drop incomplete rows, build a timestamp and calendar features."""
    return (
        df.dropna(subset=NUMERIC_COLUMNS)  # equivalent to "filter out '?' rows"
        .withColumn(
            "dt",
            # "31/01/2007" + " " + "23:59:00" -> proper TIMESTAMP
            F.to_timestamp(
                F.concat_ws(" ", F.col("date"), F.col("time")),
                "dd/MM/yyyy HH:mm:ss",
            ),
        )
        .filter(F.col("dt").isNotNull())   # safety net for malformed lines
        .drop("date", "time")              # raw strings superseded by dt
        .withColumn("date", F.to_date("dt"))
        .withColumn("hour", F.hour("dt"))
        .withColumn("month", F.month("dt"))
        .withColumn("year", F.year("dt"))
    )


def build_hourly_aggregate(df: DataFrame) -> DataFrame:
    """Energy / load summary per calendar day and hour of day."""
    return (
        df.groupBy("date", "hour")
        .agg(
            F.round(F.sum("global_active_power") / 60, 4).alias("kwh"),
            F.round(F.avg("global_active_power"), 4).alias("avg_power_kw"),
            F.round(F.max("global_active_power"), 4).alias("peak_power_kw"),
            F.count("*").alias("minute_readings"),
        )
        .orderBy("date", "hour")
    )


def build_daily_aggregate(df: DataFrame) -> DataFrame:
    """Energy / load summary per calendar day."""
    return (
        df.groupBy("date")
        .agg(
            F.round(F.sum("global_active_power") / 60, 2).alias("kwh"),
            F.round(F.avg("global_active_power"), 4).alias("avg_power_kw"),
            F.round(F.max("global_active_power"), 4).alias("peak_power_kw"),
            F.count("*").alias("minute_readings"),
        )
        .orderBy("date")
    )


def write_csv(df: DataFrame, path: str) -> None:
    """Small aggregates: coalesce to a single CSV file with a header row."""
    (
        df.coalesce(1)
        .write.mode("overwrite")
        .option("header", True)
        .csv(path)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean the UCI electricity dataset and build Parquet + aggregate CSVs."
    )
    parser.add_argument(
        "--input",
        default="data/raw/household_power_consumption.txt",
        help="Path to the raw ';' separated dataset (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default="data/processed",
        help="Directory for the Parquet dataset and aggregate CSVs (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spark = build_spark_session()

    raw = load_raw_data(spark, args.input)
    cleaned = clean_and_enrich(raw)

    raw_count = raw.count()          # count() is an aggregate - no collect()
    clean_count = cleaned.count()
    print(f"raw rows       : {raw_count}")
    print(f"clean rows     : {clean_count}")
    print(f"rows dropped   : {raw_count - clean_count} ('?' / unparseable rows)")

    # ---- outputs -----------------------------------------------------------
    parquet_path = f"{args.output.rstrip('/')}/power_consumption_parquet"
    cleaned.write.mode("overwrite").parquet(parquet_path)
    print(f"parquet written: {parquet_path}")

    hourly = build_hourly_aggregate(cleaned)
    daily = build_daily_aggregate(cleaned)

    write_csv(hourly, f"{args.output.rstrip('/')}/hourly_aggregates.csv")
    write_csv(daily, f"{args.output.rstrip('/')}/daily_aggregates.csv")
    print(f"hourly aggregates -> {args.output}/hourly_aggregates.csv")
    print(f"daily aggregates  -> {args.output}/daily_aggregates.csv")

    # ---- small previews only (never collect() the full dataset) ------------
    print("\ncleaned sample:")
    cleaned.orderBy("dt").limit(5).select("dt", *NUMERIC_COLUMNS).show(truncate=False)

    print("hourly aggregate sample:")
    hourly.show(5, truncate=False)

    print("daily aggregate sample:")
    daily.show(5, truncate=False)

    spark.stop()


if __name__ == "__main__":
    main()
