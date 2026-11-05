-- =============================================================================
-- electricity_analysis.pig
--
-- OPTIONAL component: the same style of analysis as the Hive/Spark parts,
-- written in Apache Pig Latin and executed entirely on the local filesystem.
--
-- Dataset recap (needed to read this script):
--   data/raw/household_power_consumption.txt, ';' separated, one row/minute:
--   $0 Date(dd/mm/yyyy), $1 Time(hh:mm:ss), $2 Global_active_power(kW),
--   $3 Global_reactive_power(kW), $4 Voltage(V), $5 Global_intensity(A),
--   $6..$8 Sub_metering_1..3 (Wh). Missing values are the literal '?'.
--   NOTE: Pig counts fields from $0, so global_active_power - the 3rd CSV
--   column - is $2 (some tutorials count it as "column 3" starting from 1).
--
-- What it produces (under data/processed/, like the Spark job):
--   data/processed/pig_hourly_avg  -> hour, avg_global_active_power_kW, readings
--   data/processed/pig_daily_kwh   -> day, total kWh
--
-- How to run (needs Pig + Java installed; run from the project root):
--   pig -x local pig/electricity_analysis.pig
--   (-x local = everything on the local filesystem, no Hadoop cluster needed)
-- =============================================================================

-- Pig refuses to write into an existing directory, so remove previous outputs
-- first (rmf = "remove file/dir", silently ignored when it does not exist).
rmf data/processed/pig_hourly_avg
rmf data/processed/pig_daily_kwh

-- -----------------------------------------------------------------------------
-- 1. LOAD - read the raw text file with PigStorage(';')
--    Every field is loaded as chararray (plain text) because '?' cannot be
--    cast to a number; cleaning happens explicitly in the next steps.
-- -----------------------------------------------------------------------------
raw = LOAD 'data/raw/household_power_consumption.txt'
      USING PigStorage(';')
      AS (
          date:chararray,                -- $0 dd/mm/yyyy
          time:chararray,                -- $1 hh:mm:ss
          global_active_power:chararray, -- $2 kW  (3rd CSV column)
          global_reactive_power:chararray,
          voltage:chararray,
          global_intensity:chararray,
          sub_metering_1:chararray,
          sub_metering_2:chararray,
          sub_metering_3:chararray
      );

-- -----------------------------------------------------------------------------
-- 2. FILTER - keep only complete rows
--    Drop the header line and every row where global_active_power (the main
--    measure) is '?' or NULL, plus rows with '?' in the other measures so the
--    casts below never produce silent garbage.
-- -----------------------------------------------------------------------------
valid = FILTER raw BY
            date                    != 'Date'   -- CSV header line
            AND date                IS NOT NULL
            AND time                IS NOT NULL
            AND global_active_power IS NOT NULL   -- null field
            AND global_active_power != '?'        -- dataset's missing marker
            AND global_reactive_power IS NOT NULL
            AND global_reactive_power != '?'
            AND voltage             IS NOT NULL
            AND voltage             != '?'
            AND global_intensity    IS NOT NULL
            AND global_intensity    != '?'
            AND sub_metering_1      IS NOT NULL
            AND sub_metering_1      != '?'
            AND sub_metering_2      IS NOT NULL
            AND sub_metering_2      != '?'
            AND sub_metering_3      IS NOT NULL
            AND sub_metering_3      != '?';

-- -----------------------------------------------------------------------------
-- 3. FOREACH - project + cast the columns we need
--    * (double)cast turns the text numbers into real numbers for AVG/SUM.
--    * SUBSTRING(time, 0, 2) takes characters [0,2) of "hh:mm:ss", i.e. the
--      two-digit hour ("00".."23"); Pig string indexes are 0-based and the end
--      index is exclusive.
-- -----------------------------------------------------------------------------
clean = FOREACH valid GENERATE
            date                                   AS day,      -- keep for daily totals
            SUBSTRING(time, 0, 2)                  AS hour,
            (double)global_active_power            AS global_active_power,
            (double)global_reactive_power          AS global_reactive_power,
            (double)voltage                        AS voltage,
            (double)global_intensity               AS global_intensity,
            (double)sub_metering_1                 AS sub_metering_1,
            (double)sub_metering_2                 AS sub_metering_2,
            (double)sub_metering_3                 AS sub_metering_3;

-- -----------------------------------------------------------------------------
-- 4. GROUP + AGGREGATE
-- -----------------------------------------------------------------------------
-- 4a. Average active power per hour of day.
by_hour  = GROUP clean BY hour;
hourly   = FOREACH by_hour GENERATE
               group                                       AS hour,
               AVG(clean.global_active_power)              AS avg_global_active_power_kw,
               COUNT(clean)                                AS readings;

-- 4b. Total energy per day: minute kW summed, then / 60 because one minute is
--     1/60 of an hour (kWh = kW * hours).
by_day   = GROUP clean BY day;
daily    = FOREACH by_day GENERATE
               group                                       AS day,
               SUM(clean.global_active_power) / 60.0       AS kwh;

-- -----------------------------------------------------------------------------
-- 5. STORE - write the results as ','-separated files
--    (Pig writes part-* files; the header-less output is dashboard/CSV ready.)
-- -----------------------------------------------------------------------------
STORE hourly INTO 'data/processed/pig_hourly_avg' USING PigStorage(',');
STORE daily  INTO 'data/processed/pig_daily_kwh'  USING PigStorage(',');

-- Peek at the aggregates (printed to stdout; harmless, tiny result sets).
-- DESCRIBE clean;
-- ILLUSTRATE clean;
