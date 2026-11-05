# Household Electricity Analytics — Design (autonomous)

## Decision Summary
- **Core app**: Python 3.13 venv + Streamlit + Plotly + Pandas/NumPy (per spec §8).
- **Cloudflare**: Workers/Pages cannot host Streamlit (stateful Python WebSocket server) nor JVM Big Data tools. Cloudflare role = **Tunnel** (public demo URL via `cloudflared`). Documented honestly.
- **Big Data components**: Hive/HDFS/Pig = scripts + Docker Compose + docs (not executable here: no Java cluster). PySpark = real scripts, tested in local mode if openjdk install succeeds; otherwise clearly marked untested per spec §7 honesty rule.
- **Energy assumption**: minute-level sampling → `kWh = kW × (1/60)` summed. Documented in code + report.

## Interface Contracts (fixed — all modules code against these)

### src/data_loader.py
- `CHUNK_SIZE = 100_000`
- `load_csv(source, nrows=None) -> pd.DataFrame` (source: path or UploadedFile; sep autodetect; na_values=['?',''])
- `read_csv_chunked(source, func, chunk_size=CHUNK_SIZE)` — apply func per chunk, merge results
- `get_file_metadata(source, filename) -> dict` — filename, size_bytes, size_human, extension
- `parse_datetime_columns(df) -> pd.DataFrame` — combines Date/Time pairs, converts parseable cols
- `infer_column_types(df) -> dict[str,str]` — "numeric"|"categorical"|"datetime"|"identifier"|"text"
- `preview_data(df, n=10) -> pd.DataFrame`
- `load_sample_dataset(name, data_dir="data/raw") -> pd.DataFrame` — "electricity" (txt, sep=';', na '?') | "online_retail" (xlsx)

### src/data_cleaning.py
- `missing_value_summary(df) -> pd.DataFrame` — column, missing_count, missing_pct
- `duplicate_summary(df) -> dict` — total_rows, duplicate_rows, duplicate_pct, unique_rows
- `handle_missing(df, strategy, columns=None) -> tuple[pd.DataFrame, list[str]]` — keep|drop_rows|fill_mean|fill_median|fill_mode; returns log (never silent)
- `handle_duplicates(df, strategy) -> tuple[pd.DataFrame, list[str]]` — keep|drop; returns log
- `quality_warnings(df) -> list[str]`

### src/data_validation.py
- `validate_csv_upload(uploaded_file) -> tuple[bool, str]`
- `validate_dataframe(df) -> dict` — rows, cols, memory_mb, completeness_pct, numeric_cols, categorical_cols, datetime_cols
- `ELECTRICITY_REQUIRED_PATTERNS` + `is_electricity_dataset(df) -> bool`
- `normalize_electricity_columns(df) -> pd.DataFrame` — lowercase/underscore rename

### src/general_analytics.py
- `numeric_summary(df) -> pd.DataFrame` — count, mean, median, mode, min, max, std, missing per numeric col
- `categorical_frequencies(df, max_categories=20) -> dict[str, pd.DataFrame]`
- `correlation_matrix(df) -> pd.DataFrame` (empty df if <2 numeric cols)
- `outlier_summary(df, method="iqr") -> pd.DataFrame` — per numeric col: n_outliers, outlier_pct, lower, upper
- `detect_identifier_columns(df) -> list[str]`

### src/electricity_analytics.py
All operate on normalized df (datetime `datetime` col + `global_active_power` kW etc.). Returns DataFrames/dicts only.
- `power_stats(df) -> dict` — avg_kw, max_kw, min_kw, count
- `energy_kwh(readings) -> float` — kW × 1/60 summed
- `compute_hourly_profile(df) -> pd.DataFrame` — hour, avg_kw
- `compute_daily_pattern(df) -> pd.DataFrame` — weekday, avg_kw
- `compute_monthly_pattern(df) -> pd.DataFrame` — year_month, kwh
- `compute_daily_summary(df) -> pd.DataFrame` — date, kwh, avg_kw, max_kw
- `submetering_comparison(df) -> pd.DataFrame` — sub_metering, total_kwh (Wh→kWh)
- `voltage_current_stats(df) -> dict` — avg_voltage, avg_current, min/max
- `high_consumption_periods(df, top_n=10) -> pd.DataFrame` — date, kwh desc
- `compare_periods(df, start1, end1, start2, end2) -> dict`

### src/visualization.py
All return `plotly.graph_objects.Figure`.
- `plot_time_series(df, x, y, title)` / `plot_bar(x, y, title, labels)` / `plot_line(x, y, title, labels)`
- `plot_hourly_profile(hourly_df)` / `plot_monthly_trend(monthly_df)` / `plot_submetering(sub_df)`
- `plot_correlation_heatmap(corr_df)` / `plot_histogram(series, bins=50)` / `plot_box(series, title)` / `plot_scatter(df, x, y, sample=5000)`
- `recommend_chart_types(col_type_a, col_type_b=None) -> list[str]` — guards incompatible combos
- `figure_to_bytes(fig, fmt="png") -> bytes`

### src/export_reports.py
All return `bytes`.
- `export_dataframe_csv(df) -> bytes`
- `export_stats_report(stats: dict) -> bytes` — CSV/text
- `export_quality_report(quality: dict) -> bytes`
- `export_consolidated_report(ctx: dict) -> bytes` — Markdown consolidated report

### app.py (integration — written by lead)
Sidebar radio → 6 pages: Overview, Data Explorer, Statistical Analysis, Electricity Analysis, Custom Visualization, Reports & Downloads (plus Big Data Backend info section). `st.session_state.df`; `@st.cache_data` on load + aggregates; electricity section gated by `is_electricity_dataset`.

## Data facts
- `data/raw/household_power_consumption.txt`: sep=';', na='?', Date dd/mm/yyyy + Time hh:mm:ss, Global_active_power kW, Global_reactive_power kW, Voltage V, Global_intensity A, Sub_metering_1..3 Wh; 2,075,259 rows.
- `data/raw/Online Retail.xlsx`: InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country; 541,909 rows.

## Error handling
Invalid/empty CSV → friendly error, no crash. Missing electricity columns → section hidden. No silent NaN replacement — every transformation logs. Empty results guarded before plotting.

## Testing
pytest: synthetic CSVs (missing, mixed, invalid, 50k-row perf smoke) + unit tests per module; integration tests skip gracefully if raw files absent.
