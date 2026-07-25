"""BOJ TANKAN business-conditions DI ingest (quarterly, db=CO).

Fetches 4 headline Judgment-Survey DI series (Large enterprises,
Manufacturing / Non-manufacturing, Actual / Forecast) from the BOJ
Time-Series Data Search API and loads them into raw.tankan_di.

Load-job only: performs a BigQuery load (WRITE_TRUNCATE, idempotent
full refresh). Run with --dry-run to fetch/parse and print row counts
WITHOUT touching BigQuery (Section 1.6 self-gate).

HTTP via urllib (stdlib); BigQuery via google-cloud-bigquery.
"""

import argparse
import calendar
import datetime as dt
import json
import time
import urllib.request

PROJECT = "project-3eaadce9-f852-40e1-932"
DATASET = "raw"
TABLE = "tankan_di"

API_BASE = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
DB = "CO"

# Large enterprises: Manufacturing / Non-manufacturing, Actual / Forecast.
# Series names are taken from the API response at runtime (not hardcoded).
SERIES_CODES = [
    "TK99F1000601GCQ01000",  # Manufacturing / Actual
    "TK99F1000601GCQ11000",  # Manufacturing / Forecast
    "TK99F2000601GCQ01000",  # Non-manufacturing / Actual
    "TK99F2000601GCQ11000",  # Non-manufacturing / Forecast
]

QUARTER_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}
USER_AGENT = "jp-stock-db/boj-tankan-ingest"


def survey_period_to_date(period):
    """Map a YYYYQQ integer (QQ in 01..04) to a quarter-end date."""
    year = period // 100
    quarter = period % 100
    month = QUARTER_MONTH[quarter]
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, last_day)


def fetch_series(code):
    url = "{0}?db={1}&code={2}".format(API_BASE, DB, code)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("STATUS") != 200:
        raise RuntimeError("API error for {0}: {1}".format(code, payload.get("MESSAGE")))
    rows = payload.get("RESULTSET") or []
    if not rows:
        raise RuntimeError("empty RESULTSET for {0}".format(code))
    return rows[0]


def parse_last_update(value):
    if value in (None, "", 0):
        return None
    text = str(value)
    if len(text) != 8:
        return None
    return dt.date(int(text[0:4]), int(text[4:6]), int(text[6:8]))


def coerce_value(raw):
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if text == "" or text in ("NA", "-", "*"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def build_rows(ingested_at):
    records = []
    for code in SERIES_CODES:
        series = fetch_series(code)
        name = series.get("NAME_OF_TIME_SERIES_J")
        unit = series.get("UNIT_J")
        category = series.get("CATEGORY_J")
        last_update = parse_last_update(series.get("LAST_UPDATE"))
        values = series.get("VALUES") or {}
        dates = values.get("SURVEY_DATES") or []
        vals = values.get("VALUES") or []
        if len(dates) != len(vals):
            raise RuntimeError("length mismatch for {0}".format(code))
        for period, raw in zip(dates, vals):
            period = int(period)
            records.append({
                "series_code": code,
                "series_name": name,
                "category": category,
                "unit": unit,
                "survey_period": period,
                "data_date": survey_period_to_date(period).isoformat(),
                "value": coerce_value(raw),
                "last_update": last_update.isoformat() if last_update else None,
                "ingested_at": ingested_at,
            })
        time.sleep(1)
    return records


def load_rows(records):
    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT)
    table_id = "{0}.{1}.{2}".format(PROJECT, DATASET, TABLE)
    schema = [
        bigquery.SchemaField("series_code", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("series_name", "STRING"),
        bigquery.SchemaField("category", "STRING"),
        bigquery.SchemaField("unit", "STRING"),
        bigquery.SchemaField("survey_period", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("data_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("value", "FLOAT64"),
        bigquery.SchemaField("last_update", "DATE"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="data_date",
        ),
        clustering_fields=["series_code"],
    )
    job = client.load_table_from_json(records, table_id, job_config=job_config)
    job.result()
    return client.get_table(table_id).num_rows


def main():
    parser = argparse.ArgumentParser(description="BOJ TANKAN DI ingest")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and parse only; do not touch BigQuery")
    args = parser.parse_args()

    ingested_at = dt.datetime.now(dt.UTC).isoformat()
    records = build_rows(ingested_at)

    total = len(records)
    non_null = sum(1 for r in records if r["value"] is not None)
    per_series = {}
    for r in records:
        per_series[r["series_code"]] = per_series.get(r["series_code"], 0) + 1
    dates = sorted(r["data_date"] for r in records)

    print("rows_total={0}".format(total))
    print("rows_value_non_null={0}".format(non_null))
    print("series_count={0}".format(len(per_series)))
    for code in SERIES_CODES:
        print("  {0} n={1}".format(code, per_series.get(code, 0)))
    if dates:
        print("data_date_min={0} data_date_max={1}".format(dates[0], dates[-1]))
    print("sample_first={0}".format(json.dumps(records[0], ensure_ascii=True)))
    print("sample_last={0}".format(json.dumps(records[-1], ensure_ascii=True)))

    if args.dry_run:
        print("DRY_RUN=1 no load performed")
        return

    loaded = load_rows(records)
    print("LOADED table_num_rows={0}".format(loaded))


if __name__ == "__main__":
    main()
