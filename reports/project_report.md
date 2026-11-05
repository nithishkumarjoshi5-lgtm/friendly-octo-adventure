# Household Electricity Analytics — Big Data Course Project Report

**Course:** Fundamentals of Big Data · **Deliverable:** interactive analytics dashboard + batch Big Data pipeline
**Stack:** Python 3.13.11 · pandas 3.1.0 · Plotly 7.1.0 · Streamlit 1.66.1 · Hadoop/HDFS · Hive 4 · PySpark 4 · Apache Pig (optional) · Docker Compose · Cloudflare Tunnel
**Date:** October 2026

---

## Abstract

This project builds an end-to-end analytics product around the UCI *Individual
Household Electric Power Consumption* dataset: **2,075,259 minute-level readings ×
9 variables** collected in one household between **16 December 2006 and
26 November 2010** (99.12 % complete). A six-page Streamlit dashboard ingests the
raw data (bundled sample, validated CSV upload, or pipeline-produced Parquet),
validates and cleans it with explicit, logged policies, and analyses it with
pandas: power statistics, energy accounting (**kWh = kW/60**, since the meter
writes exactly one row per minute), hourly/weekday/monthly consumption profiles,
sub-metering shares, voltage/current behaviour, peak periods and two-period
comparisons — all rendered with Plotly and exportable as CSV, TXT, Markdown and
PNG. Headline results computed on the full dataset: mean active power
**1.092 kW** (max 11.122 kW), total energy **≈ 37,283.7 kWh**, a daily consumption
peak at **20:00** (1.899 kW average) and a winter-dominated monthly profile
(top-3 months: Dec 2007, Jan 2007, Jan 2008). A Hadoop/HDFS + Hive + PySpark
batch pipeline (plus an optional Pig script) is fully scripted in the repository
to demonstrate the course's distributed-computing tools; these JVM components
are **provided but were not executed on the build machine** (no JVM/Docker),
a status documented honestly throughout this report and in
`reports/TESTING_RESULTS.md`. The Python path is verified by **185 passing
pytest tests**, a headless AppTest walk of all six dashboard pages and a live
server boot check.

## 1. Objectives

1. Apply the full Big Data lifecycle — ingestion, validation, cleaning, storage,
   analysis, visualization, publication — to a real 2-million-row sensor dataset.
2. Build an interactive dashboard that answers concrete consumption questions:
   *when* is power used (hour/day/month profiles), *how much* is used (kWh), and
   *where* it goes (three sub-meters).
3. Make the pipeline dataset-agnostic: the same code path must handle any
   tabular CSV/XLSX (demonstrated with UCI *Online Retail*, 541,909 × 8).
4. Demonstrate the course's distributed tooling — HDFS storage, Hive SQL,
   Pig Latin, Spark DataFrames — with honest execution status.
5. Guarantee code quality with an automated test suite and reproducible
   verification commands.

## 2. Datasets

### 2.1 Individual Household Electric Power Consumption (primary)

| Property | Value (measured on the bundled file) |
|---|---|
| Source | UCI ML Repository, dataset [235](https://archive.ics.uci.edu/dataset/235), CC BY 4.0 |
| Size | 2,075,259 rows × 9 columns (~130 MB, `;`-separated text) |
| Sampling | one row per minute |
| Coverage | 2006-12-16 17:24 → 2010-11-26 21:02 (48 calendar months with data) |
| Completeness | 99.12 % (missing values encoded as `?`) |
| Missing `global_active_power` | 25,979 rows (1.25 %) |
| In-memory footprint | 191.9 MB after normalization + datetime parsing |

Columns: `Date`, `Time`, `Global_active_power` (kW), `Global_reactive_power`
(kW), `Voltage` (V), `Global_intensity` (A), `Sub_metering_1..3` (Wh) — kitchen,
laundry room, and climate-control/heating sub-circuits respectively.

### 2.2 Online Retail (secondary, generality demo)

UCI dataset [352](https://archive.ics.uci.edu/dataset/352), CC BY 4.0 —
**541,909 rows × 8 columns** of UK e-commerce transactions (2010–2011), loaded
from the bundled `.xlsx` via openpyxl in ≈ 15 s. It exercises the generic
Explorer/Statistics/Custom-visualization pages (categorical filters on
`Country`, text search on `Description`, etc.).

## 3. Methodology

### 3.1 Processing pipeline

```
load → normalize columns → parse datetimes → profile (validate_dataframe)
     → optional cleaning (missing/duplicate strategies, always logged)
     → analytics (cached) → Plotly figures → Streamlit pages → exports
```

Ingestion paths: bundled samples (`load_sample_dataset`), sidebar CSV upload
validated by `validate_csv_upload` (≤ 200 MB, non-empty, parseable) and parsed
with a **100,000-row chunked reader**, or pipeline Parquet from
`data/processed/` (Project Overview page).

### 3.2 Cleaning policies

Missing values (five explicit strategies): `keep` (report only), `drop_rows`,
`fill_mean`, `fill_median`, `fill_mode` — every applied operation is recorded in
an on-screen cleaning log. Duplicates: `keep` or `drop`, with a duplicate summary
(count + %) always displayed. Column names are lower-cased
(`normalize_electricity_columns`) and `Date`+`Time` are fused into a typed
`datetime` column (`%d/%m/%Y %H:%M:%S`). Nothing is silently dropped: the
`quality_warnings` module surfaces completeness, duplicate and type issues on
the Overview page.

### 3.3 Energy accounting assumption

The meter writes **one instantaneous kW reading per minute**, therefore each
reading contributes `kW × (1/60) h` of energy:

> **kWh = Σ (kW) / 60** — implemented in `src/electricity_analytics.energy_kwh`
> and used consistently by the dashboard, the Hive queries and the Spark jobs
> (documented in `hive/create_tables.hql` and `spark/process_dataset.py`).

Sub-metering columns are already watt-hours per minute, so they are summed
directly and compared against the metered total.

## 4. System architecture

Two cooperating layers (see `reports/architecture_diagram.svg`):

1. **Interactive path (tested):** data sources → ingestion (`src/data_loader.py`)
   → validation & cleaning (`data_validation.py`, `data_cleaning.py`) → pandas
   analytics (`general_analytics.py`, `electricity_analytics.py`) → Plotly
   visualization (`visualization.py`) → six-page Streamlit dashboard (`app.py`)
   → Cloudflare Tunnel → users.
2. **Batch path (provided):** raw `.txt` → HDFS (auto-uploaded by
   `docker-compose.bigdata.yml`) → Hive (`hive/*.hql`, schema-on-read external
   table → typed Parquet `power_clean` table → six SQL analytics) and PySpark
   (`spark/process_dataset.py` → cleaned Parquet + hourly/daily aggregate CSVs)
   → dashboard loads the Parquet output. An optional Pig script repeats the
   analysis on the local filesystem.

Session-state model in the app: `df` (raw) → `df_norm` (normalized + parsed) →
`df_view` (filtered/cleaned view, rebuilt each run); heavy electricity
computations are memoized with `@st.cache_data` keyed on a **cheap content
fingerprint** (row count, timestamp bounds, power sum) instead of hashing 2M rows.

## 5. Implementation details per module

| Module | Responsibility |
|---|---|
| `src/data_loader.py` | sample loaders, upload buffer handling, chunked CSV reading (100k), file metadata (size/type/rows), column type inference (numeric/datetime/identifier/categorical/text) |
| `src/data_validation.py` | `validate_csv_upload` (never raises), `validate_dataframe` profiling (rows/cols/completeness %/memory MB), electricity-dataset detection + column normalization |
| `src/data_cleaning.py` | missing/duplicate summaries, five missing-value and two duplicate strategies, `quality_warnings` |
| `src/general_analytics.py` | numeric summary (count/mean/median/mode/min/max/std/missing), categorical frequencies, Pearson correlation matrix, IQR outlier scan |
| `src/electricity_analytics.py` | `power_stats`, `energy_kwh`, hourly/weekday/monthly profiles, per-day summary, sub-metering comparison, voltage/current stats, top-N peak days, two-period comparison; all guards against missing columns, never mutate inputs |
| `src/visualization.py` | 11 Plotly builders on the `plotly_white` template, ≤ 10k-point downsampling, placeholder figures for empty inputs, optional kaleido PNG bytes |
| `src/export_reports.py` | in-memory CSV/TXT/Markdown exporters (never touch disk) |
| `app.py` | 6 pages, session state, cache wrappers, sidebar ingestion, Big Data explainer |
| `hive/`, `spark/`, `pig/` | batch pipeline (Section 7) |

## 6. Analysis results (computed on the full 2,075,259-row dataset)

All numbers below were produced by running the project's own `src` modules on
`data/raw/household_power_consumption.txt` (script of record in
`reports/TESTING_RESULTS.md`). Nothing is estimated.

**Power statistics** (2,049,280 valid `global_active_power` readings):

| Metric | Value |
|---|---|
| Mean active power | **1.092 kW** |
| Maximum | **11.122 kW** |
| Minimum | 0.076 kW |
| Total energy | **37,283.7 kWh** (≈ 4.26 years of metering) |
| Average voltage / current | 240.84 V (223.2–254.15) · 4.63 A |

**Temporal patterns**

- *Hour of day:* consumption peaks at **20:00** (1.899 kW average) — the evening
  cooking/heating window — and bottoms out at **04:00** (0.444 kW).
- *Day of week:* **Saturday** is the heaviest day (1.248 kW avg), **Thursday**
  the lightest (0.982 kW).
- *Monthly energy:* strong winter seasonality — top-3 months are **Dec 2007
  (1,210.1 kWh), Jan 2007 (1,150.2 kWh), Jan 2008 (1,086.2 kWh)**; summer
  months drop below ~500 kWh (Aug 2008: 205.7 kWh over a partial month).

**Peaks — top-3 days by energy**

| Date | Energy | Avg power | Peak power |
|---|---|---|---|
| 2006-12-23 | 79.56 kWh | 3.31 kW | 8.70 kW |
| 2007-02-03 | 67.16 kWh | 2.80 kW | 7.90 kW |
| 2006-12-26 | 65.57 kWh | 2.73 kW | 6.50 kW |

**Sub-metering shares** (of the 18,195.3 kWh actually sub-metered):
climate/heating circuit **sub_metering_3 = 72.7 %** (13,235.2 kWh),
laundry **sub_metering_2 = 14.6 %** (2,661.0 kWh), kitchen
**sub_metering_1 = 12.6 %** (2,299.1 kWh) — the household's energy story is
dominated by fixed climate-control load, with cooking/laundry as secondary
contributors.

**Interpretation.** A single household averaged ≈ 1.1 kW continuously
(≈ 26 kWh/day) across four years; usage is evenings-, weekends- and
winter-driven, and roughly three quarters of metered circuit load is the
climate/water-heating circuit — consistent with a Northern-France household
(the dataset's documented origin) before any efficiency retrofits.

## 7. Big Data integration

Each course tool has a concrete role in the repository:

| Tool | Role in this project | Execution status |
|---|---|---|
| **HDFS (Hadoop 3.4.1)** | durable store for the 130 MB raw file (`/data/electricity`), auto-uploaded at stack start; NameNode UI on :9870 | 🟡 Provided — not executed on the build machine (no Docker/JVM) |
| **Hive 4 (+ PostgreSQL 16 metastore)** | SQL warehouse: EXTERNAL schema-on-read table over the raw text, INSERT-OVERWRITE into a typed Parquet `power_clean` table, six analytics queries (`hive/analytics_queries.hql`) | 🟡 Provided — not executed here |
| **PySpark 4** | distributed cleaning & feature build (`process_dataset.py`: clean → Parquet + hourly/daily aggregate CSVs) and analysis (`electricity_analysis.py`: profiles, trends, peaks, correlations); runs `local[*]` or on the Compose Spark cluster | 🟡 Provided — byte-compiles clean; local-mode run requires Java 17/21 (OpenJDK was installed on the machine only after the build; local verification pending) |
| **Apache Pig (optional)** | same hourly-average / daily-kWh analysis in Pig Latin on the local filesystem (`pig -x local`) | 🟡 Provided — not executed here |
| **Docker Compose** | one-command orchestration of the whole stack (`docker-compose.bigdata.yml`) | 🟡 Provided — not executed here |

The dashboard deliberately consumes only the flat Parquet/CSV outputs of the
batch layer, so the interactive path keeps working without a cluster — a
practical Lambda-style split between batch processing and serving.

## 8. Testing

**`pytest tests/ -q` → 185 passed, 2 warnings, 1.22 s** (Python 3.13.11,
pytest 9.2.0). Coverage spans all seven `src` modules plus an end-to-end
integration test (load → normalize → validate → analyze → export) and a
Streamlit `AppTest` walk of all six pages. The only warnings are pandas
deprecation notices (`Series.dt.weekday`), scheduled for `day_of_week`.

Additional verifications recorded in `reports/TESTING_RESULTS.md`:
headless `AppTest` page walk with the real 2.07M-row sample (all pages render,
0 exceptions; Electricity page draws 15 metrics + 8 charts), `streamlit run`
boot check (health endpoint HTTP 200), full-dataset loads through the `src`
modules (electricity in ≈ 0.4 s raw read; retail `.xlsx` in ≈ 15 s), and
`py_compile` smoke tests of both Spark scripts.

## 9. Performance notes

- **2.07M rows** load from the raw text in ≈ 0.4 s (pandas C engine); the full
  analytics chain (stats → 4 group-bys → peaks → comparison) completes in ≈ 3.8 s
  end-to-end on a laptop, so page interactions stay inside Streamlit's
  re-run budget.
- Heavy electricity computations are wrapped in `@st.cache_data` keyed on a
  cheap fingerprint (rows, timestamp bounds, rounded power sum) — refiltering
  does not re-hash a 192 MB DataFrame.
- Plotly rendering is bounded by **automatic downsampling to ≤ 10,000 points**
  for long series and sampling (5k) for coloured scatters; the Explorer previews
  data in 500-row chunks.
- Uploads are capped at 200 MB and parsed in 100k-row chunks to bound memory.

## 10. Limitations

1. The distributed layer (HDFS/Hive/Spark/Pig) is **provided but not executed**
   on the build machine (no Docker/JVM at build time); its scripts follow
   official quickstart patterns and byte-compile, but cluster behaviour
   (memory, shuffle tuning) is unverified.
2. `kaleido` is not installed, so server-side PNG export degrades gracefully to
   Plotly's interactive toolbar export.
3. Energy accounting assumes exactly one row per minute; gaps (1.25 % of
   `global_active_power` rows are missing) make `energy_kwh` a slight
   **under**-estimate — visible in partial months such as Aug 2008.
4. Single-user demo scope: no authentication on the Streamlit app or the
   tunnel; the dashboard is designed for course evaluation, not production.
5. Sub-metering shares are computed against metered sub-total (18,195.3 kWh),
   not the 37,283.7 kWh whole-home total, because sub-metering covers only part
   of the installation.

## 11. Conclusion

The project demonstrates a complete Big Data product on a genuinely large,
messy, real-world sensor dataset: a 2.07-million-row pipeline that loads in
under a second, cleans with explicit logged policies, answers the course's
consumption questions with reproducible numbers (1.092 kW average, 37,283.7 kWh
over four years, 20:00 evening peak, winter-dominated seasonality, 72.7 % of
sub-metered load on the climate circuit), and presents everything in a
six-page dashboard guarded by 185 passing tests. The Hadoop/Hive/Spark layer
shows the same analysis expressed in distributed tooling; its honest
provided-vs-tested status is documented so evaluators can re-run every step
from `docs/BIGDATA_SETUP.md` and `reports/TESTING_RESULTS.md`.

## References

1. UCI Machine Learning Repository. *Individual Household Electric Power
   Consumption*. <https://archive.ics.uci.edu/dataset/235> (CC BY 4.0).
2. UCI Machine Learning Repository. *Online Retail*.
   <https://archive.ics.uci.edu/dataset/352> (CC BY 4.0).
3. Apache Software Foundation. *Hadoop*, *Hive*, *Spark*, *Pig* official
   documentation — <https://hadoop.apache.org>, <https://hive.apache.org>,
   <https://spark.apache.org>, <https://pig.apache.org>.
4. Streamlit, Plotly, pandas documentation — <https://docs.streamlit.io>,
   <https://plotly.com/python>, <https://pandas.pydata.org/docs>.
5. Project-internal: `docs/BIGDATA_SETUP.md`, `reports/TESTING_RESULTS.md`,
   `reports/ATTRIBUTION.md`.
