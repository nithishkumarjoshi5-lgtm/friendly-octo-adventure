-- =============================================================================
-- create_tables.hql
--
-- Stage 1 of the Hive part of the project: turn the raw UCI "Individual
-- Household Electric Power Consumption" text file into a typed, cleaned Hive
-- table that the analytics queries can work with.
--
-- Dataset facts (needed to understand this script):
--   * file layout: 9 columns separated by ';' (no quotes, no escaping):
--       Date;Time;Global_active_power;Global_reactive_power;Voltage;
--       Global_intensity;Sub_metering_1;Sub_metering_2;Sub_metering_3
--   * Date is dd/mm/yyyy, Time is hh:mm:ss, sampling is once per minute
--     (2,075,259 rows, December 2006 - November 2010).
--   * missing measurements are stored as the literal string '?'.
--   * Global_*_power are in kilowatts (kW) per minute, Sub_metering_* are in
--     watt-hours (Wh) per minute.
--
-- How to run (from the project root, Hive already started):
--   beeline -u jdbc:hive2://localhost:10000 -n hive -f hive/create_tables.hql
--
-- Energy assumption used everywhere in this project: because the meter writes
-- one row per minute,   kWh = kW * (1/60 h) = kW / 60   summed over the rows.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 0. Database
-- -----------------------------------------------------------------------------
-- A database is just a namespace that groups the project tables. IF NOT EXISTS
-- keeps this script re-runnable.
CREATE DATABASE IF NOT EXISTS electricity
COMMENT 'UCI Individual Household Electric Power Consumption (Dec 2006 - Nov 2010)';

USE electricity;

-- -----------------------------------------------------------------------------
-- 1. EXTERNAL table over the raw file (schema-on-read)
-- -----------------------------------------------------------------------------
-- EXTERNAL means Hive never owns or moves the file; it only reads it in place
-- from /data/electricity on HDFS. Every column is kept as STRING because the
-- raw file contains the '?' placeholder, which cannot be parsed as a number -
-- cleaning happens in step 2. 'date' and 'time' are backticked because they
-- collide with Hive type names.
CREATE EXTERNAL TABLE IF NOT EXISTS power_consumption (
    `date`                STRING COMMENT 'Meter date, format dd/MM/yyyy',
    `time`                STRING COMMENT 'Meter time, format HH:mm:ss (minute granularity)',
    global_active_power   STRING COMMENT 'Household global minute-average active power, kW',
    global_reactive_power STRING COMMENT 'Household global minute-average reactive power, kW',
    voltage               STRING COMMENT 'Minute-average line voltage, V',
    global_intensity      STRING COMMENT 'Household global minute-average current, A',
    sub_metering_1        STRING COMMENT 'Kitchen (dishwasher, oven, microwave), Wh',
    sub_metering_2        STRING COMMENT 'Laundry room (washer, dryer, fridge), Wh',
    sub_metering_3        STRING COMMENT 'Water heater + air conditioner, Wh'
)
ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ';'
STORED AS TEXTFILE
LOCATION '/data/electricity'
TBLPROPERTIES (
    -- The UCI file ships with a one-line header; tell Hive to skip it.
    'skip.header.line.count' = '1'
);

-- -----------------------------------------------------------------------------
-- 2. Cleaned, typed table
-- -----------------------------------------------------------------------------
-- A managed (non-EXTERNAL) table stored as Parquet: columnar + compressed, so
-- the analytics scans in analytics_queries.hql are much faster than reading the
-- 130 MB text file every time.
CREATE TABLE IF NOT EXISTS power_clean (
    dt                    TIMESTAMP COMMENT 'Reading timestamp built from date + time',
    global_active_power   DOUBLE    COMMENT 'kW',
    global_reactive_power DOUBLE    COMMENT 'kW',
    voltage               DOUBLE    COMMENT 'V',
    global_intensity      DOUBLE    COMMENT 'A',
    sub_metering_1        DOUBLE    COMMENT 'Wh',
    sub_metering_2        DOUBLE    COMMENT 'Wh',
    sub_metering_3        DOUBLE    COMMENT 'Wh'
)
STORED AS PARQUET;

-- -----------------------------------------------------------------------------
-- 3. Populate power_clean
-- -----------------------------------------------------------------------------
-- INSERT OVERWRITE replaces whatever is in power_clean, so re-running this
-- script never duplicates rows.
--   * unix_timestamp(..., 'dd/MM/yyyy HH:mm:ss') parses "date + time" into
--     epoch seconds; from_unixtime turns that back into a readable string
--     which is finally CAST to a real TIMESTAMP column.
--   * Rows containing '?' anywhere are dropped (about 1.25% of the dataset).
--   * The inner WHERE dt IS NOT NULL also drops any row whose timestamp failed
--     to parse, so power_clean never holds garbage rows.
INSERT OVERWRITE TABLE power_clean
SELECT
    dt,
    global_active_power,
    global_reactive_power,
    voltage,
    global_intensity,
    sub_metering_1,
    sub_metering_2,
    sub_metering_3
FROM (
    SELECT
        CAST(
            from_unixtime(
                unix_timestamp(CONCAT(`date`, ' ', `time`), 'dd/MM/yyyy HH:mm:ss')
            ) AS TIMESTAMP
        )                          AS dt,
        CAST(global_active_power   AS DOUBLE) AS global_active_power,
        CAST(global_reactive_power AS DOUBLE) AS global_reactive_power,
        CAST(voltage               AS DOUBLE) AS voltage,
        CAST(global_intensity      AS DOUBLE) AS global_intensity,
        CAST(sub_metering_1        AS DOUBLE) AS sub_metering_1,
        CAST(sub_metering_2        AS DOUBLE) AS sub_metering_2,
        CAST(sub_metering_3        AS DOUBLE) AS sub_metering_3
    FROM power_consumption
    -- Defensive extra guard: if the file ever gets loaded without the header
    -- being skipped, this row would slip through skip.header.line.count.
    WHERE `date` <> 'Date'
      AND global_active_power   <> '?'
      AND global_reactive_power <> '?'
      AND voltage               <> '?'
      AND global_intensity      <> '?'
      AND sub_metering_1        <> '?'
      AND sub_metering_2        <> '?'
      AND sub_metering_3        <> '?'
) parsed
WHERE dt IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 4. Quick sanity checks (feel free to comment these out later)
-- -----------------------------------------------------------------------------
-- Expected: ~2,049,280 rows (2,075,259 minus the ~1.25% missing '?' rows).
SELECT COUNT(*) AS total_clean_rows FROM power_clean;

-- Peek at the first few cleaned rows.
SELECT * FROM power_clean LIMIT 5;
