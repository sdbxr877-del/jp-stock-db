#!/usr/bin/env python3
"""Dry-run only validator for 03_screening_candidates.sql (v83 wire-up).

Reads the same YAML config that run_screening.py uses, so the Japanese market
names in allowed_markets stay UTF-8 and never pass through a shell argument.
Performs a dry run ONLY. It never executes the statement and never writes.

Usage:
    python verify_03_dryrun.py
"""
from __future__ import annotations

import pathlib
import sys

import yaml
from google.cloud import bigquery

BASE_DIR = pathlib.Path(__file__).resolve().parent
SQL_PATH = BASE_DIR / "sql" / "03_screening_candidates.sql"
CONFIG_PATH = BASE_DIR / "screening_config.yaml"
MAX_SCAN_GB = 1.5


def main() -> int:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    project = cfg["project"]
    s = cfg["screening"]

    sql = SQL_PATH.read_text(encoding="utf-8").replace("{{PROJECT}}", project)
    left = sql.count("{{PROJECT}}")
    print(f"placeholder_left={left}")
    print(f"proj_count={sql.count(project)}")
    if left != 0:
        print("SUBSTITUTION FAILED")
        return 2

    roe_scale = 0.01 if s.get("roe_is_percentage") else 1.0
    params = [
        bigquery.ScalarQueryParameter("min_turnover_yen", "FLOAT64", float(s["min_turnover_yen"])),
        bigquery.ArrayQueryParameter("allowed_markets", "STRING", list(s["allowed_markets"])),
        bigquery.ScalarQueryParameter("per_max", "FLOAT64", float(s["per_max"])),
        bigquery.ScalarQueryParameter("roe_min", "FLOAT64", float(s["roe_min"])),
        bigquery.ScalarQueryParameter("roe_cap", "FLOAT64", float(s["roe_cap"])),
        bigquery.ScalarQueryParameter("mom_3m_min", "FLOAT64", float(s["mom_3m_min"])),
        bigquery.ScalarQueryParameter("roe_scale", "FLOAT64", roe_scale),
    ]
    print(f"param_count={len(params)}")
    print(f"markets_count={len(list(s['allowed_markets']))}")

    client = bigquery.Client(project=project, location=cfg.get("location"))
    job_cfg = bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False, query_parameters=params
    )
    job = client.query(sql, job_config=job_cfg)
    b = job.total_bytes_processed or 0
    gb = b / 1e9
    print(f"syntax=OK")
    print(f"scan_bytes={b}")
    print(f"scan_gb={gb:.4f}")
    verdict = "G3 PASS" if gb <= MAX_SCAN_GB else "G3 FAIL"
    print(f"{verdict} (limit {MAX_SCAN_GB} GB)")
    return 0 if gb <= MAX_SCAN_GB else 3


if __name__ == "__main__":
    sys.exit(main())
