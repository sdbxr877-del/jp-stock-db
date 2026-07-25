#!/usr/bin/env python3
"""MOF JGB constant-maturity yields ingest into raw.jgb_yields.

Source:
  Current month : https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv
  Full history  : https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv
CSV layout:
  row 1 : title line
  row 2 : header "Date,1Y,2Y,...,10Y,...,40Y"
  data  : "YYYY/M/D,<val>,..." ; empty cell means no data (skip as NULL)
  encoding: Shift-JIS (cp932)
Design:
  - long output: data_date / tenor / value / updated_at
  - WRITE_APPEND ; downstream analytics.jgb_yields_latest dedups by MAX(updated_at)
  - default incremental (current month) ; --backfill for full history
  - --dry-run for fetch-only (no BQ write)
Env:
  GCP_PROJECT_ID : required ; BigQuery resolved via ADC.
Usage:
  python scripts/mof_jgb_ingest.py --dry-run
  python scripts/mof_jgb_ingest.py --backfill --dry-run
  python scripts/mof_jgb_ingest.py --backfill
  python scripts/mof_jgb_ingest.py
"""
import argparse
import csv
import datetime
import io
import os
import sys
import pandas as pd
import requests
from google.cloud import bigquery

BQ_DATASET_ID = "raw"
BQ_TABLE_ID = "jgb_yields"
CURRENT_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
HISTORY_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv"

BQ_SCHEMA = [
    bigquery.SchemaField("data_date", "DATE", mode="REQUIRED", description="JGB reference date"),
    bigquery.SchemaField("tenor", "STRING", mode="REQUIRED", description="maturity bucket e.g. 10Y"),
    bigquery.SchemaField("value", "FLOAT", mode="REQUIRED", description="yield percent"),
    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED", description="cloud insert time"),
]


def fetch_csv_text(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    resp.encoding = "cp932"
    return resp.text


def parse_jgb_csv(text: str) -> pd.DataFrame:
    reader = csv.reader(io.StringIO(text))
    header = None
    tenors = []
    records = []
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for row in reader:
        if not row:
            continue
        first = row[0].strip()
        if header is None:
            if first == "Date":
                header = row
                tenors = [c.strip() for c in row[1:]]
            continue
        try:
            d = datetime.datetime.strptime(first, "%Y/%m/%d").date()
        except ValueError:
            continue
        for i, tenor in enumerate(tenors, start=1):
            if i >= len(row):
                continue
            cell = row[i].strip()
            if cell == "" or cell.startswith("-"):
                continue
            try:
                val = float(cell)
            except ValueError:
                continue
            records.append({
                "data_date": d,
                "tenor": tenor,
                "value": val,
                "updated_at": now_iso,
            })
    df = pd.DataFrame(records)
    if not df.empty:
        df["updated_at"] = pd.to_datetime(df["updated_at"])
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="MOF JGB -> raw.jgb_yields ingestion")
    parser.add_argument("--dry-run", action="store_true", help="fetch only, no BQ write")
    parser.add_argument("--backfill", action="store_true", help="use full history file instead of current month")
    args = parser.parse_args()
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        print("[CRITICAL] required GCP project id is not set.", file=sys.stderr)
        return 2
    url = HISTORY_URL if args.backfill else CURRENT_URL
    print(f"[INFO] start {datetime.datetime.now().isoformat()} dry_run={args.dry_run} backfill={args.backfill}")
    print(f"[INFO] source {url}")
    try:
        text = fetch_csv_text(url)
    except requests.exceptions.RequestException as err:
        print(f"[API ERROR] {err}", file=sys.stderr)
        return 1
    master = parse_jgb_csv(text)
    if master.empty:
        print("[INFO] no valid rows parsed. nothing to load.")
        return 0
    print(f"[INFO] total rows={len(master)} tenors={master['tenor'].nunique()} dates={master['data_date'].nunique()}")
    print(f"[INFO] date range {master['data_date'].min()} .. {master['data_date'].max()}")
    latest10 = master[master["tenor"] == "10Y"].sort_values("data_date").tail(1)
    if not latest10.empty:
        r = latest10.iloc[0]
        print(f"[INFO] latest 10Y {r['data_date']} {r['value']}")
    if args.dry_run:
        print("[DRY-RUN] BQ write skipped. sample (head 5):")
        print(master.head(5).to_string(index=False))
        return 0
    destination = f"{project_id}.{BQ_DATASET_ID}.{BQ_TABLE_ID}"
    client = bigquery.Client(project=project_id)
    job_config = bigquery.LoadJobConfig(schema=BQ_SCHEMA, write_disposition="WRITE_APPEND")
    print(f"[INFO] loading {len(master)} rows -> {destination}")
    load_job = client.load_table_from_dataframe(master, destination, job_config=job_config)
    load_job.result()
    print(f"[SUCCESS] appended {len(master)} rows to {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
