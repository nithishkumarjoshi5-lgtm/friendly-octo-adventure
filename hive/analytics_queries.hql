-- =============================================================================
-- analytics_queries.hql
--
-- Stage 2 of the Hive part of the project: the six required analytics queries
-- on top of the cleaned power_clean table produced by create_tables.hql.
--
-- Units cheat-sheet:
--   * global_active_power is average kW per MINUTE, so per-row energy is
--     kW / 60 (one minute = 1/60 hour). SUM(...)/60 therefore gives kWh.
--   * sub_metering_1..3 are watt-hours per minute; totals in kWh = SUM / 1000.
--
-- How to run (from the project root):
--   beeline -u jdbc:hive2://localhost:10000 -n hive -f hive/analytics_queries.hql
-- Each SELECT prints its own result table in beeline, in file order (a) .. (f).
-- =============================================================================

-- Select the project database (create_tables.hql already created it).
USE electricity;

-- -----------------------------------------------------------------------------
-- (a) Average consumption per hour of the day
--     Answers: "at which times of day does this household typically use the
--     most power?" hour(dt) = 0..23. We report the mean power in kW and the
--     total energy in kWh across all days, plus how many readings back it up.
-- -----------------------------------------------------------------------------
SELECT
    HOUR(dt)                                   AS hour_of_day,
    ROUND(AVG(global_active_power), 4)         AS avg_power_kw,
    ROUND(SUM(global_active_power) / 60, 2)    AS total_kwh,
    COUNT(*)                                   AS minute_readings
FROM power_clean
GROUP BY HOUR(dt)
ORDER BY hour_of_day;

-- -----------------------------------------------------------------------------
-- (b) Daily summaries
--     One row per calendar day: total energy (kWh), average load (kW) and the
--     single highest minute-level peak (kW). to_date(dt) truncates the
--     timestamp to a plain date, which is our GROUP BY key.
-- -----------------------------------------------------------------------------
SELECT
    TO_DATE(dt)                                AS day,
    ROUND(SUM(global_active_power) / 60, 2)    AS kwh,
    ROUND(AVG(global_active_power), 4)         AS avg_kw,
    ROUND(MAX(global_active_power), 4)         AS peak_kw
FROM power_clean
GROUP BY TO_DATE(dt)
ORDER BY day;

-- -----------------------------------------------------------------------------
-- (c) Monthly trends
--     Total kWh per calendar month (year(dt), month(dt)) - the series to plot
--     to see seasonality (winter heating peaks vs. summer lows) and the drop
--     towards the end of the measurement period.
-- -----------------------------------------------------------------------------
SELECT
    YEAR(dt)                                   AS yr,
    MONTH(dt)                                  AS mo,
    ROUND(SUM(global_active_power) / 60, 2)    AS kwh
FROM power_clean
GROUP BY YEAR(dt), MONTH(dt)
ORDER BY yr, mo;

-- -----------------------------------------------------------------------------
-- (d) Top 10 peak-usage days
--     Same per-day kWh as in (b), but wrapped in a subquery so we can sort by
--     the aggregate and keep only the ten hungriest days.
-- -----------------------------------------------------------------------------
SELECT
    day,
    ROUND(kwh, 2) AS kwh
FROM (
    SELECT
        TO_DATE(dt)                             AS day,
        SUM(global_active_power) / 60           AS kwh
    FROM power_clean
    GROUP BY TO_DATE(dt)
) daily_totals
ORDER BY kwh DESC
LIMIT 10;

-- -----------------------------------------------------------------------------
-- (e) Sub-metering totals in kWh
--     The three sub-meters are cumulative Wh readings per minute, so dividing
--     their grand totals by 1000 converts Wh -> kWh:
--       sub_metering_1 = kitchen (dishwasher, oven, microwave)
--       sub_metering_2 = laundry room (washing machine, dryer, fridge)
--       sub_metering_3 = electric water heater + air conditioner
-- -----------------------------------------------------------------------------
SELECT
    ROUND(SUM(sub_metering_1) / 1000, 2) AS kitchen_kwh,
    ROUND(SUM(sub_metering_2) / 1000, 2) AS laundry_room_kwh,
    ROUND(SUM(sub_metering_3) / 1000, 2) AS water_heater_ac_kwh
FROM power_clean;

-- -----------------------------------------------------------------------------
-- (f) Average voltage by month
--     Mains voltage should hover around 230-240 V; monthly means show grid
--     stability (sags when the neighborhood load is high). Rounded to 2 dp
--     because beeline prints full DOUBLE precision otherwise.
-- -----------------------------------------------------------------------------
SELECT
    YEAR(dt)                                   AS yr,
    MONTH(dt)                                  AS mo,
    ROUND(AVG(voltage), 2)                     AS avg_voltage_v
FROM power_clean
GROUP BY YEAR(dt), MONTH(dt)
ORDER BY yr, mo;
