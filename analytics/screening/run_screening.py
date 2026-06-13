#!/usr/bin/env python3
"""Phase 3 screening runner (MVP v1).

実行順: 00_ddl -> 01_daily_metrics -> 02_fundamentals_latest -> 03_screening_candidates
各クエリは dry-run でスキャン量を確認してから本実行(dry-run-required ルール準拠)。
daily_metrics は対象日の DELETE->INSERT(BEGIN TRANSACTION・MERGE 不使用)で冪等更新。

使い方:
    python run_screening.py                      # raw.prices の最新日を対象に実行
    python run_screening.py --target-date 2026-06-13
    python run_screening.py --skip-ddl           # daily_metrics 作成済の通常運用

依存: google-cloud-bigquery, pyyaml
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


def load_config(path: pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_sql(name: str, project: str) -> str:
    text = (SQL_DIR / name).read_text(encoding="utf-8")
    return text.replace("{{PROJECT}}", project)


def run_query(client: bigquery.Client, sql: str, params=None, label: str = "") -> bigquery.QueryJob:
    """dry-run でスキャン量を表示してから本実行する。"""
    params = params or []
    # 1) dry-run(dry-run-required)。スクリプトは scan=0 表示になり得る点に注意。
    dry_cfg = bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False, query_parameters=params
    )
    dry = client.query(sql, job_config=dry_cfg)
    gb = (dry.total_bytes_processed or 0) / 1e9
    print(f"[dry-run] {label:24s}: {gb:7.3f} GB scan")

    # 2) 本実行
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    job = client.query(sql, job_config=cfg)
    job.result()
    print(f"[done]    {label:24s}: job={job.job_id}")
    return job


def resolve_target_date(client: bigquery.Client, project: str, override: str | None) -> dt.date:
    if override:
        return dt.date.fromisoformat(override)
    sql = f"SELECT MAX(date) AS d FROM `{project}.raw.prices`"
    return list(client.query(sql).result())[0]["d"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-date", default=None, help="YYYY-MM-DD(既定: raw.prices の最新日)")
    ap.add_argument("--skip-ddl", action="store_true", help="daily_metrics 作成済なら DDL を省略")
    args = ap.parse_args()

    cfg = load_config(CONFIG_PATH)
    project = cfg["project"]
    s = cfg["screening"]
    client = bigquery.Client(project=project, location=cfg.get("location"))

    target_date = resolve_target_date(client, project, args.target_date)
    print(f"target_date = {target_date}")

    if not args.skip_ddl:
        run_query(client, read_sql("00_ddl.sql", project), label="00_ddl")

    # 01 daily_metrics(対象日1日分・冪等 DELETE->INSERT)
    p01 = [bigquery.ScalarQueryParameter("target_date", "DATE", target_date)]
    run_query(client, read_sql("01_daily_metrics.sql", project), p01, "01_daily_metrics")

    # 02 fundamentals_latest(全銘柄最新財務)
    run_query(client, read_sql("02_fundamentals_latest.sql", project), label="02_fundamentals_latest")

    # 03 screening_candidates(閾値注入)
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
