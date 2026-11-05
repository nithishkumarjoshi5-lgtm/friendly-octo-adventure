# Big Data Setup Guide

How to run the Big-Data backend of the *Fundamentals of Big Data* project: HDFS
storage, Apache Hive SQL analytics, PySpark processing and an optional Apache
Pig job, all working on the UCI **Individual Household Electric Power
Consumption** dataset (`data/raw/household_power_consumption.txt`, ~2.07
million minute-level rows, Dec 2006 - Nov 2010).

```
                          +------------------------------+
 data/raw/*.txt --------->| HDFS  (namenode + datanode)  |
        (auto-uploaded)   +---------------+--------------+
                                          |
                    +---------------------+---------------------+
                    v                                           v
        +-----------------------+                  +------------------------+
        | Hive 4 (metastore on  |                  | PySpark (process ->    |
        | PostgreSQL 16) +      |                  | Parquet + aggregates)  |
        | HiveServer2 :10000    |                  +-----------+------------+
        +-----------+-----------+                              |
                    |                                          v
                    v                               data/processed/*.csv
        hive/create_tables.hql                     data/processed/power_consumption_parquet
        hive/analytics_queries.hql                             |
                    |                                          v
                    +-------------------------> Streamlit dashboard (src/)
```

Project files covered by this guide:

| File | Purpose |
|---|---|
| `docker-compose.bigdata.yml` | Hadoop HDFS + Hive 4 + PostgreSQL 16 + Spark stack |
| `hive/create_tables.hql` | raw external table -> cleaned `power_clean` table |
| `hive/analytics_queries.hql` | the six required analytics queries |
| `spark/process_dataset.py` | raw txt -> cleaned Parquet + hourly/daily CSVs |
| `spark/electricity_analysis.py` | profiles, trends, peaks, correlations |
| `pig/electricity_analysis.pig` | optional Pig Latin version of the analysis |
| `requirements-spark.txt` | `pyspark>=4.0` for the local-mode path |

---

## 0. Prerequisites

* 8 GB RAM free is comfortable for the Docker stack (4 GB can work but is slow).
* ~3 GB disk for images + volumes (the dataset itself is ~130 MB).
* `git bash`/terminal basics - every command below runs from the **project
  root** (the folder containing this `docs/`, `hive/`, `spark/`, `pig/`).
* Ports used: `9870, 9864, 9000` (HDFS), `10000, 10002` (HiveServer2), `9083`
  (metastore), `8080, 8081, 7077` (Spark). Stop local services that clash, or
  remap the left-hand port in `docker-compose.bigdata.yml`.

---

## Option A - Docker Compose (recommended)

Everything runs in containers; no Java installation needed on the host.

**Requires:** Docker Engine 24+ with Docker Compose **v2.23.1 or newer**
(check with `docker compose version` - the compose file uses inline
`configs:` content).

### A.1 Start the stack

```bash
# pull images + start HDFS, PostgreSQL, Hive, Spark; the one-shot
# `postgres-jdbc-driver` and `hdfs-init` services fetch the JDBC driver and
# upload the dataset into HDFS automatically
docker compose -f docker-compose.bigdata.yml up -d

# watch the boot sequence until hdfs-init reports the upload
docker compose -f docker-compose.bigdata.yml logs -f hdfs-init
```

Verify the dataset landed in HDFS:

```bash
docker compose -f docker-compose.bigdata.yml exec namenode \
    hdfs dfs -ls /data/electricity
```

Web UIs while the stack is up:

| URL | What |
|---|---|
| http://localhost:9870 | HDFS NameNode (Utilities -> Browse the file system) |
| http://localhost:10002 | HiveServer2 |
| http://localhost:8080 / 8081 | Spark master / worker |

### A.2 Run the Hive pipeline

```bash
# 1. create database + tables, clean the data (INSERT OVERWRITE)
docker compose -f docker-compose.bigdata.yml exec hive-server2 \
    beeline -u jdbc:hive2://localhost:10000 -n hive -f /opt/work/hive/create_tables.hql

# 2. run the six analytics queries
docker compose -f docker-compose.bigdata.yml exec hive-server2 \
    beeline -u jdbc:hive2://localhost:10000 -n hive -f /opt/work/hive/analytics_queries.hql
```

(`./hive` is mounted read-only into the container at `/opt/work/hive`, so the
files are always the ones in your repo. `-n hive` is just the username -
HiveServer2 here accepts any.)

### A.3 Run the PySpark scripts

The scripts default to `local[*]`, so they run inside the Spark container
without the cluster:

```bash
docker compose -f docker-compose.bigdata.yml exec spark-master \
    spark-submit --master local[*] /opt/work/spark/process_dataset.py

docker compose -f docker-compose.bigdata.yml exec spark-master \
    spark-submit --master local[*] /opt/work/spark/electricity_analysis.py
```

Outputs land in `./data/processed/` on the host (`./data` is bind-mounted):
`power_consumption_parquet/`, `hourly_aggregates.csv`, `daily_aggregates.csv`.

To use the standalone Spark cluster instead of local mode, submit against
`spark://spark-master:7077` (the master and worker both have the repo's
`spark/` and `data/` folders mounted at `/opt/work`).

### A.4 Tear down

```bash
docker compose -f docker-compose.bigdata.yml down      # keep data volumes
docker compose -f docker-compose.bigdata.yml down -v   # + wipe HDFS/Hive/Postgres data
```

---

## Option B - Manual Hadoop + Hadoop Hive install (advanced)

Only if you must run a "real" single-node cluster on Linux/macOS without
Docker. The short version; authoritative steps live in the official docs:

1. **Java 8** (Hadoop 3.3.x / Hive 4 run on OpenJDK 8; Java 11 works for
   Hadoop, keep 8 for Hive 4 compatibility) and **SSH localhost** password-less
   login for Hadoop scripts.
2. Download Hadoop from https://hadoop.apache.org/releases.html and follow the
   *Single Node Setup* guide:
   https://hadoop.apache.org/docs/stable/hadoop-project-dist/hadoop-common/SingleCluster.html
   - set `fs.defaultFS` to `hdfs://localhost:9000` in `etc/hadoop/core-site.xml`,
   `hdfs namenode -format`, then `start-dfs.sh`.
3. Load the dataset:
   ```bash
   hdfs dfs -mkdir -p /data/electricity
   hdfs dfs -put data/raw/household_power_consumption.txt /data/electricity/
   ```
4. Download Hive from https://hive.apache.org/general/downloads/ and follow
   https://cwiki.apache.org/confluence/display/Hive/AdminManual+Installation
   - run `schematool -initSchema -dbType derby`, start `hiveserver2 &`.
5. Run the HQL files exactly as in A.2, but from the host:
   ```bash
   beeline -u jdbc:hive2://localhost:10000 -n hive -f hive/create_tables.hql
   beeline -u jdbc:hive2://localhost:10000 -n hive -f hive/analytics_queries.hql
   ```

---

## Option C - PySpark local mode only (no Hadoop, no Docker)

This is what the demo laptop used: Spark in *local mode* processes the raw file
directly and writes the Parquet + CSV outputs the dashboard needs. Hive and Pig
are simply skipped.

1. **Java 17 or 21** must be on your PATH (Spark 4.x requirement):
   `java -version` -> `17.x`/`21.x`. Otherwise install, e.g.
   `brew install openjdk@17` (macOS) or `sudo apt install openjdk-17-jdk`
   (Ubuntu), then point `JAVA_HOME` at it.
2. Python 3.9+ with the project venv, then:

   ```bash
   pip install -r requirements-spark.txt        # pyspark>=4.0

   .venv/bin/python spark/process_dataset.py     # raw txt -> Parquet + CSVs
   .venv/bin/python spark/electricity_analysis.py
   ```

   Both scripts accept `--input/--output/--parquet-path`; defaults point at
   `data/raw/...` and `data/processed/...`, so the commands above work as-is
   from the project root.

---

## Apache Pig (optional component)

`pig/electricity_analysis.pig` repeats the hourly-average / daily-kWh analysis
in Pig Latin. It reads and writes **local filesystem** paths, so no HDFS
needed.

1. Install Pig from https://pig.apache.org/ (needs Java 8; set `PIG_HOME` and
   add `$PIG_HOME/bin` to `PATH`).
2. From the project root:

   ```bash
   pig -x local pig/electricity_analysis.pig
   ```

3. Results land in `data/processed/pig_hourly_avg/` and
   `data/processed/pig_daily_kwh/` as comma-separated `part-*` files
   (columns: `hour,avg_global_active_power_kw,readings` and `day,kwh`).
   Pig never overwrites: the script starts with `rmf` commands that remove the
   previous output directories for you.

---

## How processed results reach the dashboard

The Streamlit app (the `src/` part of the project) does **not** touch HDFS or
Hive. It only reads the flat outputs that `spark/process_dataset.py` writes
under `data/processed/`:

| File | Content | Producer |
|---|---|---|
| `data/processed/power_consumption_parquet/` | cleaned, typed dataset (timestamp + kW/V/A/Wh columns + date/hour/month/year) | `spark/process_dataset.py` |
| `data/processed/hourly_aggregates.csv` | kWh / avg / peak per day+hour | `spark/process_dataset.py` |
| `data/processed/daily_aggregates.csv` | kWh / avg / peak per day | `spark/process_dataset.py` |

So the full chain is: run **Option A.3 or Option C once**, and the dashboard
picks up the refreshed files (`pandas.read_parquet` /
`pandas.read_csv`). The Hive queries and the Pig job produce the same numbers
for the report; they are independent of the dashboard feed.

---

## Testing status

| Component | Status | Notes |
|---|---|---|
| `hive/create_tables.hql` | Provided — requires Java/Docker environment; not executed during this build (no JVM available) | syntax mirrors the official Hive 4 quickstart patterns |
| `hive/analytics_queries.hql` | Provided — requires Java/Docker environment; not executed during this build (no JVM available) | pure SQL over `power_clean` |
| `spark/process_dataset.py` | Provided — requires Java/Docker environment; not executed during this build (no JVM available) | byte-compiles clean; needs JVM at runtime |
| `spark/electricity_analysis.py` | Provided — requires Java/Docker environment; not executed during this build (no JVM available) | byte-compiles clean; needs JVM at runtime |
| `pig/electricity_analysis.pig` | Provided — requires Java/Docker environment; not executed during this build (no JVM available) | optional component |
| `docker-compose.bigdata.yml` | Provided — requires Java/Docker environment; not executed during this build (no JVM available) | image/service conventions verified against official docs (apache/hadoop 3.4.1, apache/hive 4.0.0, postgres:16, apache/spark 4.0.5-python3) |
| PySpark local mode (Option C) | ✅ TESTED locally — `spark-submit` `local[*]` on the full 2.07M-row dataset (Spark 4.2.1, OpenJDK 21.0.11): Parquet (18 parts, 25 MB) + hourly/daily CSVs produced in 36 s + 10 s; 2,075,259 raw → 2,049,280 clean rows; aggregates match the pandas-based dashboard numbers exactly | OpenJDK 27 does **not** work (Spark: `ClassNotFoundException: jdk.internal.ref.Cleaner`) — use 17/21. Dataset has non-zero-padded dates (`20/6/2007`), so pass `--conf spark.sql.legacy.timeParserPolicy=LEGACY --conf spark.sql.ansi.enabled=false`; in a pip venv also export `SPARK_HOME=.venv/lib/python3.13/site-packages/pyspark` |

---

## Troubleshooting

* **`hdfs-init` never finishes / "waiting for a live DataNode".**
  `docker compose logs datanode` - the usual cause is a clusterID mismatch
  after the NameNode was reformatted while the DataNode kept old data:
  `docker compose -f docker-compose.bigdata.yml down -v` and start again.
* **beeline prints `Connection refused`.**
  HiveServer2 takes ~30-60 s to open port 10000 after `up -d`. Check
  `docker compose logs hive-server2` / the http://localhost:10002 UI first.
* **hive-metastore exits with a schema error.**
  Make sure `postgres` is healthy first (`docker compose ps`); then restart the
  metastore - it runs `schematool -initOrUpgradeSchema` on boot. As a last
  resort: `down -v` (wipes the metastore DB) and re-run A.2.
* **`docker compose` complains about `configs.content`.**
  Your Compose is older than v2.23.1 - `docker compose version`, update Docker
  Desktop / the compose plugin.
* **PySpark: `java: command not found` or `UnsupportedClassVersionError`.**
  No JDK, or JDK < 17. Install Java 17/21 and export `JAVA_HOME`
  (e.g. `export JAVA_HOME=$(/usr/libexec/java_home -v 17)` on macOS).
* **PySpark `PYTHONHASHSEED` / worker warnings on macOS.**
  Harmless; optionally `export PYSPARK_PYTHON=python3` and
  `export SPARK_LOCAL_IP=127.0.0.1` first.
* **First Spark run is slow.** Spark unpacks and starts a JVM, and the 2M-row
  read is CPU-bound; 1-3 minutes in local mode is normal. Later runs reuse the
  OS page cache and are faster.
* **Dashboard shows stale numbers.** Re-run `spark/process_dataset.py` (Option
  A.3 or Option C); the CSV/Parquet files are overwritten in place on each run.
