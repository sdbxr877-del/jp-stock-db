#!/usr/bin/env python3
"""Phase 3 screening runner (MVP v1).

Execution order: 00_ddl -> 01_daily_metrics -> 02_fundamentals_latest -> 03_screening_candidates
Each query is dry-run first to report scanned bytes (dry-run-required rule).
daily_metrics is updated idempotently for the target date via DELETE -> INSERT
(BEGIN TRANSACTION, no MERGE).

Usage:
    python run_screening.py                      # latest trading date in raw.prices
    python run_screening.py --target-date 2026-06-13
    python run_screening.py --skip-ddl           # daily_metrics already created

Deps: google-cloud-bigquery, pyyaml
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

import yaml
from google.cloud import bigquery

BASE_DIR = pathlib.Path(__file__).resolve().parent
SQL_DIR = BASE_DIR / "sql"
CONFIG_PATH = BASE_DIR / "screening_config.yaml"

# Lower bound (days) for the partition filter used when resolving the target date.
TARGET_DATE_LOOKBACK_DAYS = 90


def load_config(path: pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_sql(name: str, project: str) -> str:
    text = (SQL_DIR / name).read_text(encoding="utf-8")
    return text.replace("{{PROJECT}}", project)


def run_query(client: bigquery.Client, sql: str, params=None, label: str = "") -> bigquery.QueryJob:
    """Dry-run to report scanned bytes, then execute for real."""
    params = params or []
    # 1) dry-run (dry-run-required). Scripts may report scan=0.
    dry_cfg = bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False, query_parameters=params
    )
    dry = client.query(sql, job_config=dry_cfg)
    gb = (dry.total_bytes_processed or 0) / 1e9
    print(f"[dry-run] {label:24s}: {gb:7.3f} GB scan")
    # 2) real execution
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    job = client.query(sql, job_config=cfg)
    job.result()
    print(f"[done]    {label:24s}: job={job.job_id}")
    return job


def resolve_target_date(client: bigquery.Client, project: str, override: str | None) -> dt.date:
    """Return the target date.

    Without an override, use the latest date in raw.prices restricted to the same
    population as 01_daily_metrics: tickers whose market is not 'INDEX'.
    Macro series (market='INDEX') carry values on weekends and market holidays, so
    a plain MAX(date) can resolve to a non-trading day and make 01 insert zero rows.
    A partition lower bound is applied (partition-filter-required rule).
    """
    if override:
        return dt.date.fromisoformat(override)
    sql = f"""
SELECT MAX(p.date) AS d
FROM `{project}.raw.prices` p
WHERE p.date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL {TARGET_DATE_LOOKBACK_DAYS} DAY)
  AND NOT EXISTS (
    SELECT 1
    FROM `{project}.raw.tickers` t
    WHERE t.ticker = p.ticker
      AND t.market = 'INDEX'
  )
"""
    d = list(client.query(sql).result())[0]["d"]
    if d is None:
        raise SystemExit(
            "resolve_target_date: no trading date found in raw.prices within "
            f"{TARGET_DATE_LOOKBACK_DAYS} days; pass --target-date explicitly"
        )
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-date", default=None, help="YYYY-MM-DD (default: latest trading date)")
    ap.add_argument("--skip-ddl", action="store_true", help="skip DDL when daily_metrics exists")
    args = ap.parse_args()

    cfg = load_config(CONFIG_PATH)
    project = cfg["project"]
    s = cfg["screening"]
    client = bigquery.Client(project=project, location=cfg.get("location"))

    target_date = resolve_target_date(client, project, args.target_date)
    print(f"target_date = {target_date}")

    if not args.skip_ddl:
        run_query(client, read_sql("00_ddl.sql", project), label="00_ddl")

    # 01 daily_metrics (single target date, idempotent DELETE -> INSERT)
    p01 = [bigquery.ScalarQueryParameter("target_date", "DATE", target_date)]
    run_query(client, read_sql("01_daily_metrics.sql", project), p01, "01_daily_metrics")

    # 02 fundamentals_latest (latest financials for all tickers)
    run_query(client, read_sql("02_fundamentals_latest.sql", project), label="02_fundamentals_latest")

    # 03 screening_candidates (threshold injection)
    roe_scale = 0.01 if s.get("roe_is_percentage") else 1.0
    p03 = [
        bigquery.ScalarQueryParameter("min_turnover_yen", "FLOAT64", float(s["min_turnover_yen"])),
        bigquery.ArrayQueryParameter("allowed_markets", "STRING", list(s["allowed_markets"])),
        bigquery.ScalarQueryParameter("per_max", "FLOAT64", float(s["per_max"])),
        bigquery.ScalarQueryParameter("roe_min", "FLOAT64", float(s["roe_min"])),
        bigquery.ScalarQueryParameter("roe_cap", "FLOAT64", float(s["roe_cap"])),
        bigquery.ScalarQueryParameter("mom_3m_min", "FLOAT64", float(s["mom_3m_min"])),
        bigquery.ScalarQueryParameter("roe_scale", "FLOAT64", roe_scale),
    ]
    run_query(client, read_sql("03_screening_candidates.sql", project), p03, "03_screening_candidates")

    n = list(
        client.query(f"SELECT COUNT(*) AS c FROM `{project}.analytics.screening_candidates`").result()
    )[0]["c"]
    print(f"screening_candidates rows = {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
