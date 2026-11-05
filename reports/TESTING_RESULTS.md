# Testing & Verification Results — honest matrix

Environment of record: **macOS (Darwin) · Python 3.13.11** (`.venv/bin/python`) · project root `/Users/ayya/developer/ptoject`.
Every ✅ row below was **re-executed while writing this report**; every 🟡 row was **not executed** and says why.

## 1. Environment

| Check | Command | Result |
|---|---|---|
| Python version | `.venv/bin/python --version` | ✅ Python 3.13.11 |
| Core packages | importlib.metadata | ✅ streamlit 1.66.1 · plotly 7.1.0 · pandas 3.1.0 · numpy 2.5.4 · openpyxl 3.1.5 · pytest 9.2.0 · pyarrow 26.0.0 |
| Docker | `docker --version` | ❌ not installed on build machine |
| Java | `java -version` | ❌ `/usr/bin/java` is the macOS stub — “Unable to locate a Java Runtime”. Homebrew **openjdk 27.0.1 finished installing post-build** (see `/tmp/openjdk_install.log`), so the JVM exists now but the **PySpark local-mode verification is still pending** (Spark 4.x officially wants Java 17/21; JDK 27 is newer than the supported line) |

## 2. Automated test suite

| Check | Command | Result |
|---|---|---|
| Full pytest run | `.venv/bin/python -m pytest tests/ -q --no-header` | ✅ **185 passed, 2 warnings in 1.22 s** |
| Warning triage | pytest output | ⚠️ 2 × `Pandas4Warning: Series.dt.weekday is deprecated` in `src/electricity_analytics.py:67` (cosmetic; replacement `dt.day_of_week` noted) |

Test files: `test_data_loader.py`, `test_data_validation.py`, `test_data_cleaning.py`,
`test_general_analytics.py`, `test_electricity_analytics.py`, `test_visualization.py`,
`test_export_reports.py`, `test_integration.py` (+ `conftest.py`).

## 3. Dashboard verification

| Check | Command / method | Result |
|---|---|---|
| Headless page walk (all 6 pages, real 2.07M-row sample loaded through the sidebar button) | `streamlit.testing.v1.AppTest.from_file("app.py")`; click `btn_sample_electricity`; `set_value(page).run()` per page | ✅ cold start OK · sample installed (2,075,259 rows, 99.12 % complete) · **all 6 pages rendered, 0 exceptions, 0 `st.error` blocks** · Electricity page drew 15 metric blocks + 8 Plotly charts |
| Live server boot | `.venv/bin/streamlit run app.py --server.headless true --server.port 8511` then `curl http://localhost:8511/_stcore/health` | ✅ health **HTTP 200**, app page **HTTP 200**; server stopped cleanly |

Rerun commands:

```bash
.venv/bin/python -m pytest tests/ -q --no-header
# AppTest walk — load the whole dataset through the UI button, then visit every page:
.venv/bin/python - <<'PY'
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=300).run()
at.sidebar.button(key="btn_sample_electricity").click().run()
for p in at.sidebar.radio[0].options:
    at.sidebar.radio[0].set_value(p).run(); assert not at.exception, p
print("all pages OK")
PY
.venv/bin/streamlit run app.py --server.headless true   # then curl /_stcore/health
```

## 4. Dataset & analytics verification (numbers of record)

| Check | Result |
|---|---|
| Electricity raw load (`pd.read_csv(..., sep=';', na_values=['?'])`) | ✅ **2,075,259 rows × 9 cols**, read ≈ 0.4 s |
| Normalization + datetime parse (`src` modules) | ✅ 10 cols incl. derived `datetime`; range **2006-12-16 17:24 → 2010-11-26 21:02**; 191.9 MB in memory |
| Completeness | ✅ **99.12 %**; missing `global_active_power` = 25,979 rows (1.25 %) |
| `power_stats` | ✅ avg **1.092 kW**, max **11.122 kW**, min 0.076 kW (2,049,280 valid readings) |
| `energy_kwh` | ✅ total **37,283.7 kWh** |
| `compute_hourly_profile` | ✅ peak hour **20:00** (1.899 kW avg); lowest 04:00 (0.444 kW) |
| `compute_daily_pattern` | ✅ Saturday highest (1.248 kW), Thursday lowest (0.982 kW) |
| `compute_monthly_pattern` | ✅ 48 months with data; top-3: **2007-12 (1,210.1 kWh), 2007-01 (1,150.2 kWh), 2008-01 (1,086.2 kWh)** |
| `high_consumption_periods` | ✅ top-3 days: **2006-12-23 (79.56 kWh), 2007-02-03 (67.16 kWh), 2006-12-26 (65.57 kWh)** |
| `submetering_comparison` | ✅ SM3 **72.7 %** (13,235.2 kWh) · SM2 14.6 % (2,661.0) · SM1 12.6 % (2,299.1) |
| `voltage_current_stats` | ✅ avg 240.84 V (223.2–254.15) · avg current 4.63 A |
| Online Retail load (`load_sample_dataset('online_retail')`) | ✅ **541,909 rows × 8 cols**, ≈ 15 s (openpyxl) |

Reproduce the numbers:

```bash
.venv/bin/python - <<'PY'
import pandas as pd
from src.data_validation import normalize_electricity_columns
from src.data_loader import parse_datetime_columns
from src.electricity_analytics import (power_stats, energy_kwh,
    compute_hourly_profile, high_consumption_periods, submetering_comparison)
df = parse_datetime_columns(normalize_electricity_columns(
    pd.read_csv("data/raw/household_power_consumption.txt", sep=";", na_values=["?"])))
print(df.shape, power_stats(df), energy_kwh(df["global_active_power"]))
print(compute_hourly_profile(df).loc[lambda d: d["avg_kw"].idxmax()])
print(high_consumption_periods(df, 3)); print(submetering_comparison(df))
PY
```

## 5. Big Data components — provided, NOT executed here

| Component | Evidence gathered | Status |
|---|---|---|
| `spark/process_dataset.py`, `spark/electricity_analysis.py` | `.venv/bin/python -m py_compile spark/*.py` → ✅ compile clean | 🟡 **Provided** — runtime needs a JVM; not executed (no Docker; JDK only landed post-build, version 27 vs Spark-4-supported 17/21). **PySpark local-mode verification pending.** |
| `hive/create_tables.hql`, `hive/analytics_queries.hql` | reviewed; syntax mirrors official Hive 4 quickstart patterns | 🟡 **Provided** — not executed (no JVM/Docker) |
| `pig/electricity_analysis.pig` | reviewed; local-filesystem mode | 🟡 **Provided** — not executed |
| `docker-compose.bigdata.yml` | service/image conventions verified against official docs during the build (apache/hadoop 3.4.1, apache/hive 4.0.0, postgres:16, apache/spark 4.0.5-python3) | 🟡 **Provided** — stack never started here |
| Cloudflare Tunnel | deployment configuration only | 🟡 **Provided** — live public serving not part of this test matrix |

How to execute them yourself: **`docs/BIGDATA_SETUP.md`** (Option A Docker,
Option B manual Hadoop+Hive, Option C PySpark local mode).

## 6. Documentation cross-check

- Numbers quoted in `README.md`, `reports/project_report.md`,
  `reports/presentation.md`/`.pptx` and this file all come from the runs in
  Section 4 — no metric is estimated or invented.
- Final re-verification before publishing: `pytest` re-run → **185 passed**;
  all deliverables present (`README.md`, `reports/project_report.md`,
  `reports/presentation.pptx`, `reports/presentation.md`,
  `reports/architecture_diagram.svg`, `reports/TESTING_RESULTS.md`,
  `reports/ATTRIBUTION.md`).

## 7. PySpark local-mode verification (supersedes the "pending" notes in §1 Java row and §5)

Executed 2026-10-29 on the same macOS machine. Both Spark scripts ran for real
on the full 2,075,259-row dataset — this closes the last 🟡 row that a JVM
could cover.

### Environment / versions

| Check | Command | Result |
|---|---|---|
| Java (initial, brew `openjdk`) | `/opt/homebrew/opt/openjdk/bin/java -version` | ❌ **openjdk 27.0.1.0.3** — Spark 4.2.1 fails on it (`java.lang.ClassNotFoundException: jdk.internal.ref.Cleaner` at `org.apache.spark.unsafe.Platform.<init>`; JDK 27 is beyond Spark 4.x's supported 8/11/17/21 line) |
| Java (working) | `brew install openjdk@21` then `.../openjdk@21/libexec/openjdk.jdk/Contents/Home/bin/java -version` | ✅ **openjdk version "21.0.11" 2026-04-21** (Homebrew build 21.0.11) |
| PySpark | `.venv/bin/python -m pip install pyspark` (venv has no bare `pip` shim → `python -m pip`) | ✅ **pyspark 4.2.1** (+ py4j 0.10.9.9); `import pyspark; print(pyspark.__version__)` → `4.2.1` |
| Spark (JVM side) | from run log | `Running Spark version 4.2.1`, `Java version 21.0.11` |

### Exact commands

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export SPARK_HOME="$PWD/.venv/lib/python3.13/site-packages/pyspark"   # venv find-spark-home can't auto-detect
export PYSPARK_PYTHON="$PWD/.venv/bin/python"
export PYSPARK_DRIVER_PYTHON="$PWD/.venv/bin/python"

# Stage 1 — processing (script defaults: --input data/raw/household_power_consumption.txt --output data/processed)
.venv/bin/spark-submit \
  --conf spark.sql.legacy.timeParserPolicy=LEGACY \
  --conf spark.sql.ansi.enabled=false \
  spark/process_dataset.py
# exit 0, runtime 36 s

# Stage 2 — analysis (script flag: --parquet-path, default matches the written Parquet)
.venv/bin/spark-submit \
  --conf spark.sql.legacy.timeParserPolicy=LEGACY \
  --conf spark.sql.ansi.enabled=false \
  spark/electricity_analysis.py --parquet-path data/processed/power_consumption_parquet
# exit 0, runtime 10 s
```

### Failures encountered on the way (both fixed at runtime, no script edits)

1. **JDK 27**: `Py4JJavaError ... ClassNotFoundException: jdk.internal.ref.Cleaner`
   → installed `openjdk@21` via brew, pointed `JAVA_HOME` at it.
2. **`CANNOT_PARSE_TIMESTAMP`**: `Text '20/6/2007 22:10:00' could not be parsed
   at index 3` — the UCI dataset really contains non-zero-padded dates
   (`grep -c '^20/6/2007'` → 1440 rows; `1/1/2007` style too), and Spark 4's
   ANSI-mode default (`spark.sql.ansi.enabled=true`) turns strict-parser
   misses into exceptions, defeating the script's `filter(dt.isNotNull())`
   safety net. → `--conf spark.sql.legacy.timeParserPolicy=LEGACY
   --conf spark.sql.ansi.enabled=false` restores lenient parsing + NULL-drop.

### Run results

| Script | Status | Runtime | Output |
|---|---|---|---|
| `spark/process_dataset.py` | ✅ exit 0 | **36 s** | raw **2,075,259** → clean **2,049,280** rows (dropped 25,979 `'?'` rows = the same 1.25 % missing as §4) |
| `spark/electricity_analysis.py` | ✅ exit 0 | **10 s** | all 6 analyses printed (hourly profile, daily summary, monthly trend, top-10 peak days, sub-metering totals, 15 Pearson correlations) |

### Output listing (`ls -la data/processed/`)

```
daily_aggregates.csv/            (dir) part-00000-*.csv (1,433 data rows + header) + _SUCCESS
hourly_aggregates.csv/           (dir) part-00000-*.csv (34,168 data rows + header) + _SUCCESS
power_consumption_parquet/       (dir) 18 snappy.parquet parts (25 MB) + _SUCCESS
```

Hourly CSV head — plausible values (`avg_power_kw` max across file: **6.5605**, within 0–12):

```
date,hour,kwh,avg_power_kw,peak_power_kw,minute_readings
2006-12-16,17,2.5337,4.2229,7.706,36
2006-12-16,18,3.6322,3.6322,6.752,60
2006-12-16,19,3.4002,3.4002,4.07,60
2006-12-16,20,3.2686,3.2686,3.496,60
2006-12-16,21,3.0565,3.0565,3.502,60
```

### Cross-validation against the pandas-based numbers of record (§4)

PySpark aggregates match §4 exactly: peak hour **20:00 → 1.8991 kW** avg
(lowest 04:00 → 0.4438), top day **2006-12-23 → 79.56 kWh** (then 2007-02-03
67.16, 2006-12-26 65.57), sub-metering **SM1 2,299.14 / SM2 2,661.03 /
SM3 13,235.17 kWh** (72.7 % SM3 share), `corr(global_active_power,
global_intensity) = +0.9989`, `corr(GAP, voltage) = −0.3998`. The Spark
pipeline and the pandas/src pipeline produce identical analytics from the same
raw file.

## 8. Post-verification fixes (2026-10-29)

Three issues found while exercising the live dashboard were fixed in `app.py`
(+ one line in `requirements.txt`) and re-verified. No `src/` changes.

| # | Issue | Root cause | Fix |
|---|---|---|---|
| 1 | "↩️ Reset filters" button on the Data Explorer did nothing | The button assigned `st.session_state["filt_*"]` **after** the filter widgets had already been instantiated in that run, and the widgets were keyless — so their persisted internal state won on the rerun and the reset values never reached the UI | Every filter widget now carries an explicit `key` (`filt_start`, `filt_end`, `filt_cols`, `filt_search`, existing `cat_*`), and the reset moved into an `on_click=_clear_filters` callback that **deletes** the widget-state keys before the next script run, so widgets re-initialize to their defaults. `install_dataset` and the no-datetime branches now pop the same keys instead of writing `None` |
| 2 | Electricity KPIs ellipsized (e.g. "37,28…") | "37,283.7 kWh" in a 1-of-6 equal column left no room for the value | Units moved into the metric labels (`Total energy (kWh)` → value `37,283.7`) and the energy column widened (`st.columns([1, 1, 1, 1.6, 1, 1])`). Same treatment for the Compare-Periods metrics (units were `_fmt_num(..., " kWh")` suffixes) |
| 3 | Reports page showed "PNG export skipped" | Optional `kaleido` engine was not installed, so `figure_to_bytes` returned `b""` | `.venv/bin/python -m pip install kaleido` (installs kaleido 1.5.0 + choreographer) and `kaleido>=1.0` added to `requirements.txt` (promoted from the "optional extras" comment) |
| 4 | (optional perf) explorer/viz/reports re-ran `infer_column_types` / `quality_warnings` over the 2.07M-row frame on every rerun | per-page recomputation | New `cached_infer_column_types` / `cached_quality_warnings` wrappers (`@st.cache_data` with the existing `_power_hash` fingerprint), used on the Overview, Explorer, Custom-Viz and `build_custom_figure` call sites. No logic changes |

### Re-verification (all re-executed on 2026-10-29)

```
.venv/bin/python -c "import ast; ast.parse(open('app.py').read()); print('syntax ok')"
# syntax ok

.venv/bin/python -c "from src.data_loader import load_csv; from src.visualization import
  plot_histogram, figure_to_bytes; df=load_csv('data/raw/household_power_consumption.txt',
  nrows=2000); b=figure_to_bytes(plot_histogram(df['Global_active_power'].dropna())); print(len(b))"
# 57675   (was 0 before kaleido)

.venv/bin/python -c "import streamlit.testing.v1"  # AppTest walks, see below
```

Two `streamlit.testing.v1.AppTest` walks against the fixed `app.py`, 0 exceptions:

1. **Synthetic-data walk** — injected a small electricity frame, then:
   filters narrowed rows 720 → 528 (search) → 432 (date + categorical) with columns cut
   to 2 → **Reset restores all 720 rows, full date range, all columns, empty search/cats**;
   Electricity metric values exact with units in labels; Reports page renders the
   `⬇️ Download PNG` button with no "skipped" caption.
2. **Full-sample walk** (same method as §3) — loaded the real 2,075,259-row household
   sample through the sidebar button, all 6 pages rendered clean, and the Electricity
   KPIs now read **exactly**: `Total energy (kWh) = 37,283.7`, `Max power (kW) = 11.122`,
   `Avg power (kW) = 1.092`, `Avg voltage (V) = 240.84` (previously ellipsized).
   A date filter narrowed 2,075,259 → 1,068,303 rows and **Reset** restored the full
   dataset and the original range 2006-12-16 → 2010-11-26.

The live server (port 8501) picked up the changes via Streamlit's file-watcher and
answered `curl` with HTTP 200; no restart was needed.
