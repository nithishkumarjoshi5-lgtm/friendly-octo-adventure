# Presentation — Household Electricity Analytics (17 slides)

> Mirrors `reports/presentation.pptx` 1:1. All numbers are measured, not estimated
> (see `reports/TESTING_RESULTS.md`). Slides 8–13 are the dashboard-evidence section
> (real screenshots) inserted after Key Findings.

---

## Slide 1 — Title

**Household Electricity Analytics**
*4 years · 1 household · 2,075,259 minutes of power data*

Big Data course project — Streamlit dashboard · pandas/Plotly analytics · HDFS/Hive/Spark batch pipeline
Python 3.13 · UCI Individual Household Electric Power Consumption · November 2026
**VINNAKOTA NITHISH KUMAR JOSHI (2300049053)**
Dept. of Electronics and Communication Engineering
Guide: K. PRAVALLIKA · Koneru Lakshmaiah Education Foundation (Deemed to be University)

---

## Slide 2 — Objectives

- Apply the full Big Data lifecycle to a real 2M-row sensor dataset:
  **ingest → validate → clean → analyze → visualize → export → publish**
- Answer concrete questions: *when* is power used, *how much*, and *where it goes*
- One generic pipeline for any tabular dataset (demo: UCI Online Retail, 541,909 rows)
- Express the same analysis in course tooling: **HDFS · Hive · Pig · Spark**
- Guarantee quality: **185 automated tests**, honest tested-vs-provided status

---

## Slide 3 — Datasets

**Primary — UCI Individual Household Electric Power Consumption** (CC BY 4.0)
- 2,075,259 rows × 9 cols · 1 reading/minute · 130 MB text
- 2006-12-16 17:24 → 2010-11-26 21:02 · 48 months with data
- 99.12 % complete · missing values encoded as `?`

**Secondary — UCI Online Retail** (CC BY 4.0)
- 541,909 rows × 8 cols · UK e-commerce 2010–2011
- proves the pipeline is dataset-agnostic

---

## Slide 4 — System architecture

*(diagram: reports/architecture_diagram.svg)*

- Interactive path: ingestion → validation & cleaning → pandas analytics → Plotly → 6-page Streamlit dashboard
- Batch path: HDFS → Hive / PySpark → Parquet → dashboard
- Edge: Cloudflare Tunnel → users
- Color code: green = tested · amber = provided-only

---

## Slide 5 — Pipeline & cleaning policies

1. **Load** — bundled samples · validated CSV upload ≤ 200 MB · chunked reader (100k rows) · Parquet
2. **Validate** — completeness %, memory footprint, type inference, quality warnings
3. **Clean** — missing: keep / drop / fill mean–median–mode · duplicates: keep / drop · every action logged
4. **Analyze** — energy assumption documented everywhere: **kWh = kW / 60** (one row per minute)
5. **Visualize & export** — CSV · TXT stats/quality · Markdown report · PNG

---

## Slide 6 — Dashboard tour (6 pages)

1. 📊 **Project Overview** — KPIs, quality warnings, pipeline explainer, Parquet loader
2. 🔍 **Data Explorer** — date/category filters, search, cleaning controls, 500-row previews
3. 📈 **Statistical Analysis** — summaries, frequencies, correlations, IQR outliers
4. ⚡ **Electricity Analysis** — trends, hourly/weekday/monthly profiles, sub-metering, peaks, period compare
5. 🎨 **Custom Visualization** — any column pair, recommended chart types
6. 📥 **Reports & Downloads** — filtered CSV, stats/quality TXT, Markdown, PNG

---

## Slide 7 — Key findings (full dataset, computed by this project's code)

- **Average power 1.092 kW** · max 11.122 kW → **total 37,283.7 kWh** in ≈ 4 years
- **Evening peak: 20:00** (1.899 kW avg) · overnight low 04:00 (0.444 kW)
- **Saturday** heaviest (1.248 kW) · **Thursday** lightest (0.982 kW)
- Winter-dominated months: top-3 = **Dec 2007 · Jan 2007 · Jan 2008**
- Biggest single days: **2006-12-23 (79.6 kWh)**, 2007-02-03, 2006-12-26
- Sub-metering: climate/heating circuit **72.7 %** of metered load · laundry 14.6 % · kitchen 12.6 %

---

## Slide 8 — Dashboard evidence · Overview KPIs

*(screenshot: `reports/screenshots/02_overview_kpis.png`, full-width, right facts card)*

**Takeaway:** the full sample loads in one click — 2,075,259 rows, 99.12 % complete.
- Dataset at a glance: 2,075,259 records · 10 columns · 191.9 MB in memory
- Power KPIs: avg 1.092 kW · max 11.122 kW · min 0.076 kW
- Data-quality panel reports completeness and warnings before any analysis

---

## Slide 9 — Dashboard evidence · Correlation heatmap

*(screenshot: `reports/screenshots/03b_statistical_heatmap.png`)*

**Takeaway:** power ≈ current (+0.999) with a load-driven voltage dip (−0.40).
- corr(active power, intensity) ≈ +0.9989 — the physics check passes
- corr(active power, voltage) ≈ −0.40 — heavier loads pull the supply down
- IQR scan: 94,907 outlier minutes (4.63 %) above the 3.358 kW fence

---

## Slide 10 — Dashboard evidence · Peak days

*(screenshot: `reports/screenshots/04a_electricity_trends.png`)*

**Takeaway:** every top-consumption day is mid-winter, led by 79.56 kWh on 2006-12-23.
- Heaviest day: 2006-12-23 — 79.56 kWh at 3.31 kW average, 8.70 kW peak
- All top-10 days fall in Dec–Feb — the winter-heating signature
- Table and chart render from one cached computation — no drift between views

---

## Slide 11 — Dashboard evidence · Hourly profile

*(screenshot: `reports/screenshots/04b_electricity_hourly.png`)*

**Takeaway:** consumption peaks at 20:00 (1.899 kW) and bottoms out at 04:00 (0.444 kW).
- Evening cooking/heating window drives a 4.3× swing across the day
- Key metrics row: 37,283.7 kWh total · 240.84 V · 4.63 A — all live
- Every bar is a full-dataset group-by, rendered in the page re-run budget

---

## Slide 12 — Dashboard evidence · Live filtering

*(screenshot: `reports/screenshots/05b_electricity_kpis_filtered.png`)*

**Takeaway:** a date filter recomputes KPIs live — 26,875.1 kWh for 2008–2010.
- Filter 2008-01-01 → 2010-11-26: avg 1.071 kW · 241.34 V · 4.53 A
- Trend chart redraws auto-downsampled to ≤ 2,000 points
- Verified Reset restores the full 2,075,259-row dataset and original range

---

## Slide 13 — Dashboard evidence · Reports & Downloads

*(screenshot: `reports/screenshots/06_reports_downloads.png`)*

**Takeaway:** filtered CSV, TXT statistics, quality report, Markdown and PNG — one page.
- Downloads built in memory — nothing is written to server disk
- Consolidated Markdown report embeds the top-10 table and chart
- PNG export via the optional kaleido engine (verified byte output)

---

## Slide 14 — Big Data backend

| Tool | Role | Status |
|---|---|---|
| HDFS 3.4.1 | raw file in `/data/electricity`, auto-upload | provided — not executed here |
| Hive 4 + PostgreSQL | external table → typed Parquet `power_clean` + 6 SQL queries | provided — not executed here |
| PySpark 4 | clean → Parquet + hourly/daily aggregates; profiles/peaks/correlations job | ✅ verified — local mode on the full dataset (36 s + 10 s; matches pandas) |
| Apache Pig | same analysis in Pig Latin (optional) | provided — not executed here |
| Docker Compose | one-command stack orchestration | provided — not executed here |

Dashboard deliberately consumes only flat Parquet/CSV outputs → works without a cluster.

---

## Slide 15 — Testing & verification

- **pytest: 185 passed, 0 failed** (1.22 s) — all 7 `src` modules + integration test
- Headless **AppTest walk: all 6 pages**, real 2.07M-row sample, 0 exceptions
- Live server boot: health endpoint **HTTP 200**
- Full-dataset loads verified (electricity ≈ 0.4 s read · retail ≈ 15 s)
- **PySpark local-mode verified** (Spark 4.2.1 / OpenJDK 21): full 2.07M rows in 36 s + 10 s — aggregates match pandas exactly
- Honest boundary: HDFS/Hive/Pig/Docker stack **not executed** on the build machine (no Docker/JVM) — rerun via `docs/BIGDATA_SETUP.md`

---

## Slide 16 — Live demo plan (8 steps)

1. Open app (`streamlit run app.py`) 2. Load electricity sample 3. Show processing pipeline
4. Statistical Analysis 5. Graphs & peaks (20:00 peak, top-10 days) 6. Filter in Data Explorer
7. Download CSV + Markdown report 8. Explain the HDFS→Hive/Spark→Parquet backend

---

## Slide 17 — Conclusions

- End-to-end Big Data product: **2.07M messy rows → reproducible insight in seconds**
- Measured story: ~1.1 kW continuous draw, evenings + weekends + winter, ¾ of metered load is climate
- Engineering: cached analytics, bounded rendering, 185 green tests
- Distributed layer scripted and documented; honest provided-vs-tested matrix
- Everything reproducible: `README.md` · `docs/BIGDATA_SETUP.md` · `reports/TESTING_RESULTS.md`

**References:** UCI ML Repository datasets 235 & 352 (CC BY 4.0) · Apache Hadoop/Hive/Spark/Pig docs · Streamlit/Plotly/pandas docs
