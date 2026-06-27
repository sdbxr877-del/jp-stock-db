#!/usr/bin/env python3
"""FRED マクロ指標を取得し raw.fred_indicators へ追記ロードする取込スクリプト（P4-1）。

出典: 設計仕様書「債券市場のマクロ数理構造」の FRED 取込 Python を流儀適用。
主な改修:
  - --dry-run を追加（BQ 書込なし・取得件数とサンプルのみ表示。§1.6 / DRY10件→本番）
  - dataset/table を既存の raw.fred_indicators に変更
  - 監視 series を 10 本に拡張（仕様6本 + DGS2/DGS10/DGS3MO/WALCL）。ECB資産は SR-9 実査後に追加
  - 未使用 import 除去・ADC ローカル認証前提（bigquery.Client は引数の project のみ）
  - 休業日に FRED が返す "." を除去して数理的整合性を維持

認証・環境変数:
  FRED_API_KEY   : FRED の API キー（必須）
  GCP_PROJECT_ID : 例 project-3eaadce9-f852-40e1-932（必須）
  BigQuery は ADC（gcloud auth application-default login 済）で解決する。

使い方:
  python scripts/fred_ingest.py --dry-run          # 取得のみ（BQ非書込）
  python scripts/fred_ingest.py --dry-run --days 10
  python scripts/fred_ingest.py                     # 本番（raw.fred_indicators へ追記）
"""

import argparse
import datetime
import os
import sys

import pandas as pd
import requests
from google.cloud import bigquery

# ----------------------------------------------------------------------
# 定数
# ----------------------------------------------------------------------
BQ_DATASET_ID = "raw"
BQ_TABLE_ID = "fred_indicators"

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"

# 監視対象 Series ID : システム上の識別名称
# 仕様明記6本 + 派生で追加4本（DGS2/DGS10/DGS3MO/WALCL）。ECB資産は符号確定後に追加予定。
INDICATORS = {
    "T10Y2Y": "US_10Y_2Y_Spread",
    "T10Y3M": "US_10Y_3M_Spread",
    "BAMLH0A0HYM2": "US_HighYield_Spread",
    "DFII10": "US_10Y_Real_Yield",
    "T10YIE": "US_10Y_BEI",
    "NFCI": "National_Financial_Conditions_Index",
    "DGS2": "US_2Y_Treasury_Yield",
    "DGS10": "US_10Y_Treasury_Yield",
    "DGS3MO": "US_3M_Treasury_Yield",
    "WALCL": "FRB_Total_Assets",
}

BQ_SCHEMA = [
    bigquery.SchemaField("data_date", "DATE", mode="REQUIRED", description="経済データの対象日付"),
    bigquery.SchemaField("indicator_code", "STRING", mode="REQUIRED", description="FRED固有のSeries ID"),
    bigquery.SchemaField("indicator_name", "STRING", mode="REQUIRED", description="システム上の識別名称"),
    bigquery.SchemaField("value", "FLOAT", mode="REQUIRED", description="インジケーターの測定値"),
    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED", description="レコードのクラウド挿入日時"),
]


def fetch_fred_series(series_id: str, api_key: str, days_to_fetch: int) -> pd.DataFrame:
    """1 series 分の観測値を取得し、クレンジング済み DataFrame を返す。

    休業日に FRED が返す値 "." は除外する。失敗時は空 DataFrame を返す（処理は継続）。
    """
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days_to_fetch)
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start.strftime("%Y-%m-%d"),
        "observation_end": today.strftime("%Y-%m-%d"),
    }

    try:
        resp = requests.get(FRED_OBS_URL, params=params, timeout=15)
        resp.raise_for_status()
        observations = resp.json().get("observations", [])
    except requests.exceptions.RequestException as err:
        print(f"[API ERROR] {series_id}: {err}", file=sys.stderr)
        return pd.DataFrame()
    except ValueError as err:
        print(f"[DATA ERROR] {series_id}: {err}", file=sys.stderr)
        return pd.DataFrame()

    now_iso = datetime.datetime.utcnow().isoformat()
    records = []
    for obs in observations:
        raw_value = obs.get("value")
        if raw_value and raw_value != ".":
            try:
                num = float(raw_value)
            except ValueError:
                continue
            records.append({
                "data_date": obs.get("date"),
                "indicator_code": series_id,
                "indicator_name": INDICATORS[series_id],
                "value": num,
                "updated_at": now_iso,
            })
    return pd.DataFrame(records)


def build_master(api_key: str, days_to_fetch: int) -> pd.DataFrame:
    """全 series を取得し垂直統合した DataFrame を返す。"""
    frames = []
    for series_id in INDICATORS:
        df = fetch_fred_series(series_id, api_key, days_to_fetch)
        if df.empty:
            print(f"[WARNING] no valid rows: {series_id}")
        else:
            print(f"[OK] {series_id}: {len(df)} rows")
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    master = pd.concat(frames, ignore_index=True)
    master["data_date"] = pd.to_datetime(master["data_date"]).dt.date
    master["updated_at"] = pd.to_datetime(master["updated_at"])
    return master


def main() -> int:
    parser = argparse.ArgumentParser(description="FRED -> raw.fred_indicators ingestion")
    parser.add_argument("--dry-run", action="store_true", help="BQ へ書き込まず取得結果のみ表示")
    parser.add_argument("--days", type=int, default=10, help="取得対象の遡及日数（default 10）")
    args = parser.parse_args()

    api_key = os.environ.get("FRED_API_KEY")
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not api_key:
        print("[CRITICAL] required FRED API credential is not set.", file=sys.stderr)
        return 2
    if not project_id:
        print("[CRITICAL] required GCP project id is not set.", file=sys.stderr)
        return 2

    print(f"[INFO] start {datetime.datetime.now().isoformat()} dry_run={args.dry_run} days={args.days}")
    master = build_master(api_key, args.days)

    if master.empty:
        print("[INFO] no valid records for any indicator. nothing to load.")
        return 0

    print(f"[INFO] total rows={len(master)} indicators={master['indicator_code'].nunique()}")
    print("[INFO] per-indicator latest:")
    latest = master.sort_values("data_date").groupby("indicator_code").tail(1)
    for _, row in latest.iterrows():
        print(f"        {row['indicator_code']:<14} {row['data_date']} {row['value']}")

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
