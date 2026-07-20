"""macro_series_import.py — マクロ系列(指数・VIX・為替・商品・暗号資産)の初回投入.

ロードマップ P1 (A09/A10) 対応。raw.prices へマクロ9系列のベースラインを投入する。

背景:
    daily_update_prices_v3.py は latest_dates に存在しない ticker を
    "no_baseline_skip" でスキップするため、日次ジョブだけでは新規系列が入らない。
    本スクリプトでベースラインを作れば、以後は日次ジョブが latest+1 で自動追随する。

既存流儀との整合 (initial_import.py 実測に一致させている):
    adj_close = Close.round(2)   (yfinance auto_adjust=True 前提)
    source    = "yfinance"
    volume    = Int64
    period    = "5y"
    書込み    = load_table_from_dataframe / WRITE_APPEND

TOPIX は Yahoo に指数そのものが無く (^TPX / 998405.T / ^JPXN は全て 404)、
既存 raw.tickers の 1306 (NEXT FUNDS TOPIX連動型ETF) が日次取得済みのため対象外。

冪等性:
    投入前に raw.prices の既存行数を系列ごとに数え、1行以上ある系列はスキップする。
    二重投入を防ぐため、再実行しても安全。

使い方:
    python macro_series_import.py --dry    # 取得のみ・BQ 書込み無し
    python macro_series_import.py          # 実投入
"""

import argparse
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
from google.cloud import bigquery

PROJECT      = "project-3eaadce9-f852-40e1-932"
TABLE_PRICES = f"{PROJECT}.raw.prices"
TABLE_TICKERS = f"{PROJECT}.raw.tickers"

PERIOD          = "5y"
PARTITION_FLOOR = "2000-01-01"   # SR-1: partition テーブル直参照の下限フィルタ
MAX_SCAN_GB     = 1.5            # bq-dry-run-required: 本実行前の上限 (project_rules_db_v1 §4)

# yfinance シンボル (2026-07-20 に probe で生存確認済)
MACRO_SYMBOLS = [
    "^N225",
    "^SOX",
    "^GSPC",
    "^IXIC",
    "^VIX",
    "JPY=X",
    "BTC-USD",
    "HG=F",
    "GC=F",
]

# raw.tickers 登録用のメタデータ。market='INDEX' により
# 01 の母集団ガードと 03 の allowed_markets の双方から除外される。
MACRO_NAMES = {
    "^N225":   "日経平均株価",
    "^SOX":    "フィラデルフィア半導体株指数",
    "^GSPC":   "S&P500",
    "^IXIC":   "NASDAQ総合指数",
    "^VIX":    "VIX指数",
    "JPY=X":   "米ドル/円",
    "BTC-USD": "ビットコイン/米ドル",
    "HG=F":    "銅先物(COMEX)",
    "GC=F":    "金先物(COMEX)",
}

INDEX_MARKET = "INDEX"

client = bigquery.Client(project=PROJECT)


def get_existing_counts(symbols):
    """対象シンボルの raw.prices 既存行数を返す (冪等性ガード)."""
    sql = f"""
        SELECT ticker, COUNT(*) AS c
        FROM `{TABLE_PRICES}`
        WHERE date >= DATE('{PARTITION_FLOOR}')
          AND ticker IN UNNEST(@symbols)
        GROUP BY ticker
    """
    params = [bigquery.ArrayQueryParameter("symbols", "STRING", symbols)]

    # bq-dry-run-required Pattern A: DRY RUN でスキャン量を検証してから本実行
    cfg_dry = bigquery.QueryJobConfig(
        query_parameters=params, dry_run=True, use_query_cache=False
    )
    dry_job = client.query(sql, job_config=cfg_dry)
    gb = dry_job.total_bytes_processed / (1024 ** 3)
    print(f"  [BQ DRY] get_existing_counts scan: {gb:.6f} GB (MAX_SCAN_GB={MAX_SCAN_GB})")
    if gb > MAX_SCAN_GB:
        raise SystemExit(
            f"DRY RUN over MAX_SCAN_GB: {gb:.6f} > {MAX_SCAN_GB}"
        )

    cfg = bigquery.QueryJobConfig(query_parameters=params)
    return {row.ticker: row.c for row in client.query(sql, job_config=cfg).result()}


def get_registered_tickers(symbols):
    """raw.tickers に既に登録済みのシンボル集合を返す (冪等性ガード)."""
    sql = f"""
        SELECT ticker
        FROM `{TABLE_TICKERS}`
        WHERE ticker IN UNNEST(@symbols)
    """
    params = [bigquery.ArrayQueryParameter("symbols", "STRING", symbols)]

    # bq-dry-run-required Pattern A: DRY RUN でスキャン量を検証してから本実行
    cfg_dry = bigquery.QueryJobConfig(
        query_parameters=params, dry_run=True, use_query_cache=False
    )
    dry_job = client.query(sql, job_config=cfg_dry)
    gb = dry_job.total_bytes_processed / (1024 ** 3)
    print(f"  [BQ DRY] get_registered_tickers scan: {gb:.6f} GB (MAX_SCAN_GB={MAX_SCAN_GB})")
    if gb > MAX_SCAN_GB:
        raise SystemExit(
            f"DRY RUN over MAX_SCAN_GB: {gb:.6f} > {MAX_SCAN_GB}"
        )

    cfg = bigquery.QueryJobConfig(query_parameters=params)
    return {row.ticker for row in client.query(sql, job_config=cfg).result()}


def register_tickers(dry_run=False):
    """未登録のマクロ系列を raw.tickers へ market='INDEX' で登録する."""
    registered = get_registered_tickers(MACRO_SYMBOLS)
    missing = [s for s in MACRO_SYMBOLS if s not in registered]
    print(f"  raw.tickers 登録済み: {len(registered)} / 未登録: {len(missing)}")
    if not missing:
        return 0

    df = pd.DataFrame({
        "ticker":       missing,
        "name":         [MACRO_NAMES[s] for s in missing],
        "market":       INDEX_MARKET,
        "sector_code":  None,
        "sector_name":  None,
        "fiscal_month": None,
        "is_active":    True,
        "updated_at":   datetime.now(timezone.utc),
    })
    df = df.astype({
        "ticker": "string", "name": "string", "market": "string",
        "sector_code": "string", "sector_name": "string",
        "fiscal_month": "string", "is_active": "boolean",
    })

    if dry_run:
        print(f"  [DRY] raw.tickers へ {len(missing)} 行を登録予定: {missing}")
        return 0

    schema = [
        bigquery.SchemaField("ticker",       "STRING"),
        bigquery.SchemaField("name",         "STRING"),
        bigquery.SchemaField("market",       "STRING"),
        bigquery.SchemaField("sector_code",  "STRING"),
        bigquery.SchemaField("sector_name",  "STRING"),
        bigquery.SchemaField("fiscal_month", "STRING"),
        bigquery.SchemaField("is_active",    "BOOL"),
        bigquery.SchemaField("updated_at",   "TIMESTAMP"),
    ]
    job = client.load_table_from_dataframe(
        df, TABLE_TICKERS,
        job_config=bigquery.LoadJobConfig(
            schema=schema, write_disposition="WRITE_APPEND"
        )
    )
    job.result()
    print(f"  raw.tickers 登録完了: {len(missing)} 行")
    return len(missing)


def fetch_one(symbol):
    """1系列を yfinance から取得し raw.prices の列構成へ整形する."""
    hist = yf.Ticker(symbol).history(period=PERIOD, auto_adjust=True)
    if hist is None or len(hist) == 0:
        return None

    hist = hist.reset_index()
    date_col = "Date" if "Date" in hist.columns else "Datetime"
    stamps = pd.to_datetime(hist[date_col])
    if stamps.dt.tz is not None:
        stamps = stamps.dt.tz_localize(None)

    out = pd.DataFrame({
        "ticker":     symbol,
        "date":       stamps.dt.date,
        "open":       hist["Open"].round(2),
        "high":       hist["High"].round(2),
        "low":        hist["Low"].round(2),
        "close":      hist["Close"].round(2),
        "volume":     hist["Volume"].astype("Int64"),
        "adj_close":  hist["Close"].round(2),
        "source":     "yfinance",
        "fetched_at": datetime.now(timezone.utc),
    })
    return out


def upload(frames):
    combined = pd.concat(frames, ignore_index=True)
    job = client.load_table_from_dataframe(
        combined, TABLE_PRICES,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
    )
    job.result()
    return len(combined)


def main(dry_run=False):
    print("=== Macro Series Import (A09/A10) ===")
    register_tickers(dry_run=dry_run)
    existing = get_existing_counts(MACRO_SYMBOLS)
    print(f"  対象系列: {len(MACRO_SYMBOLS)} / 既存行あり: {len(existing)}")

    frames = []
    for symbol in MACRO_SYMBOLS:
        already = existing.get(symbol, 0)
        if already > 0:
            print(f"  [skip] {symbol}: 既存 {already} 行")
            continue
        df = fetch_one(symbol)
        if df is None:
            print(f"  [FAIL] {symbol}: 取得0行")
            continue
        print(f"  [ok]   {symbol}: {len(df)} 行 "
              f"({df['date'].min()} .. {df['date'].max()})")
        frames.append(df)

    if not frames:
        print("  投入対象なし。終了。")
        return

    total = sum(len(f) for f in frames)
    if dry_run:
        print(f"  [DRY] 投入予定 {total} 行 / {len(frames)} 系列。書込みは行わない。")
        return

    written = upload(frames)
    print(f"  投入完了: {written} 行 / {len(frames)} 系列")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="BQ 書込みを行わない")
    args = parser.parse_args()
    main(dry_run=args.dry)
