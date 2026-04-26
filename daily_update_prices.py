"""
daily_update_prices.py - yfinance 日次株価差分更新 (db_v0.7 / Phase 3.1)
                        v2 / 失敗31 対応

機能:
  raw.prices に存在しない (ticker, date) を yfinance から取得し追記する。
  毎日 16:30 JST 想定 (東証大引け 15:30 + 反映マージン1h)。

設計原則:
  - 完全無料 (BigQuery 無料枠維持)
  - パーティションフィルタ必須 (§4)
  - SELECT * 禁止 (§4)
  - ストリーミング挿入禁止 / load_table_from_dataframe 使用 (§4)
  - DRY RUN は BQ 書き込みを行わない。
    本スクリプトは checkpoint を使わないため SR-10 自動準拠。

【v2 変更内容 / 失敗31 対応】
  v1 では SCAN_DAYS=30 / NEW_TICKER_DAYS=60 のミスマッチで、
  raw.prices の最終データが 30日以上前の銘柄に対し、
  no_baseline_fallback 経路で 60日前から再取得し、既存データと重複した。

  v2 修正:
  (a) SCAN_DAYS を 30 → 400 に拡大 (5年間のうち最近1年強をカバー)。
      これにより、しばらくデータ更新がない銘柄も latest_date を取れる。
  (b) no_baseline_fallback 経路を廃止。latest_date=None の銘柄は
      reason='no_baseline_skip' でスキップする (重複の可能性を絶つ)。
      本当の新規銘柄の初回投入は initial_import.py の責務とする。

依存: initial_import.py の投入結果 (raw.prices, raw.tickers)

CLI:
  python daily_update_prices.py --ticker 7203 --dry    # 単体 DRY
  python daily_update_prices.py --ticker 7203          # 単体本番
  python daily_update_prices.py --limit 10 --dry       # 10銘柄 DRY
  python daily_update_prices.py --dry                  # 全銘柄 DRY
  python daily_update_prices.py                        # 全銘柄本番
"""

import os
import time
import argparse
from datetime import datetime, timezone, date, timedelta
from collections import Counter

import pandas as pd
import yfinance as yf
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

PROJECT       = "project-3eaadce9-f852-40e1-932"
TABLE_PRICES  = f"{PROJECT}.raw.prices"
TABLE_TICKERS = f"{PROJECT}.raw.tickers"

CHUNK_SIZE      = 50    # チャンク投入サイズ (銘柄)
SCAN_DAYS       = 400   # MAX(date) 取得時のパーティション範囲 (日) ← v2: 30→400
MAX_SCAN_GB     = 1.5   # スキャン量上限 (v2: 1.0→1.5 に拡大、SCAN_DAYS拡大に対応)
SLEEP_FETCH     = 0.5   # yfinance 呼び出し間隔 (秒)
SLEEP_CHUNK     = 1.0   # チャンク投入間隔 (秒)
# NEW_TICKER_DAYS 廃止 (v2 / 失敗31対応)

client = bigquery.Client(project=PROJECT)


# ---------------------------------------------------------------------------
# BigQuery helpers
# ---------------------------------------------------------------------------
def get_active_tickers():
    sql = f"""
        SELECT ticker
        FROM `{TABLE_TICKERS}`
        WHERE is_active = TRUE
        ORDER BY ticker
    """
    return [row.ticker for row in client.query(sql).result()]


def get_latest_dates():
    """
    各 ticker の現在の MAX(date) を一括取得。
    パーティションフィルタを必ずかけ、DRY RUN でスキャン量を確認する (§4 / G3)。
    """
    sql = f"""
        SELECT ticker, MAX(`date`) AS max_date
        FROM `{TABLE_PRICES}`
        WHERE `date` >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL {SCAN_DAYS} DAY)
        GROUP BY ticker
    """

    # G3: BigQuery DRY RUN
    dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry_job = client.query(sql, job_config=dry_cfg)
    gb = dry_job.total_bytes_processed / 1e9
    print(f"  [BQ DRY] get_latest_dates scan: {gb:.4f} GB")
    if gb > MAX_SCAN_GB:
        raise RuntimeError(
            f"スキャン量が上限超過: {gb:.2f} GB > {MAX_SCAN_GB} GB. "
            "SQL を見直してください"
        )

    # 本実行
    return {row.ticker: row.max_date for row in client.query(sql).result()}


def upload_chunk(dfs, dry_run=False):
    combined = pd.concat(dfs, ignore_index=True)
    if dry_run:
        return len(combined)
    job = client.load_table_from_dataframe(
        combined,
        TABLE_PRICES,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND"),
    )
    job.result()
    return len(combined)


# ---------------------------------------------------------------------------
# yfinance fetch
# ---------------------------------------------------------------------------
def fetch_yfinance(code, latest_date):
    """
    latest_date の翌日以降のデータを yfinance から取得。

    v2 変更: latest_date=None の銘柄はフォールバックせずスキップする
            (重複の可能性を絶つ。失敗31対応)
            真の新規銘柄の初回投入は initial_import.py の責務。

    返り値: (DataFrame or None, reason_str)
    """
    if latest_date is None:
        return None, "no_baseline_skip"

    today = date.today()
    start = latest_date + timedelta(days=1)
    if start > today:
        return None, "already_up_to_date"

    try:
        df = yf.Ticker(f"{code}.T").history(start=start.isoformat())
    except Exception as e:
        # 例外メッセージは type のみ. secret 漏洩防止のため詳細は出力しない
        return None, f"fetch_error:{type(e).__name__}"

    if df.empty:
        return None, "empty_response"

    df = df.reset_index()
    df["date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.date

    # 安全策: latest_date 以前の行を確実に除外
    df = df[df["date"] > latest_date]
    if df.empty:
        return None, "no_new_rows"

    df["ticker"]     = code
    df["open"]       = df["Open"].round(2)
    df["high"]       = df["High"].round(2)
    df["low"]        = df["Low"].round(2)
    df["close"]      = df["Close"].round(2)
    df["volume"]     = df["Volume"].astype("Int64")
    df["adj_close"]  = df["Close"].round(2)
    df["source"]     = "yfinance"
    df["fetched_at"] = datetime.now(timezone.utc)

    cols = ["ticker", "date", "open", "high", "low", "close",
            "volume", "adj_close", "source", "fetched_at"]
    return df[cols], "ok"


# ---------------------------------------------------------------------------
# Main runners
# ---------------------------------------------------------------------------
def run(dry_run=False, limit=None):
    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"=== Daily Update Prices [{mode}] ===")
    print(f"  実行時刻 (JST): {datetime.now().isoformat(timespec='seconds')}")

    tickers = get_active_tickers()
    if limit:
        tickers = tickers[:limit]
    print(f"  対象銘柄: {len(tickers):,}")

    print(f"  既存最大日付を取得中 (パーティション {SCAN_DAYS} 日)...")
    latest_dates = get_latest_dates()
    new_count = sum(1 for t in tickers if t not in latest_dates)
    print(f"  既存銘柄: {len(latest_dates):,} / "
          f"raw.prices に無し: {new_count:,}")

    chunk_dfs    = []
    chunk_codes  = []
    new_rows     = 0
    reason_count = Counter()

    for i, code in enumerate(tickers, start=1):
        latest = latest_dates.get(code)
        df, reason = fetch_yfinance(code, latest)
        reason_count[reason] += 1

        if df is not None and not df.empty:
            chunk_dfs.append(df)
            chunk_codes.append(code)

        # 進捗ハートビート (500件毎)
        if i % 500 == 0:
            print(f"  [progress] {i:>4}/{len(tickers)} processed, "
                  f"chunk_pending={len(chunk_dfs)}, new_rows={new_rows:,}")

        # チャンク投入
        if len(chunk_dfs) >= CHUNK_SIZE:
            rows = upload_chunk(chunk_dfs, dry_run=dry_run)
            new_rows += rows
            tag = "DRY-投入" if dry_run else "投入"
            print(f"  >>> {tag}: {len(chunk_codes)}銘柄 / {rows}行 "
                  f"(累計行: {new_rows:,}, 進捗: {i}/{len(tickers)})")
            chunk_dfs   = []
            chunk_codes = []
            time.sleep(SLEEP_CHUNK)
        else:
            time.sleep(SLEEP_FETCH)

    # 端数
    if chunk_dfs:
        rows = upload_chunk(chunk_dfs, dry_run=dry_run)
        new_rows += rows
        tag = "DRY-投入" if dry_run else "投入"
        print(f"  >>> {tag}(端数): {len(chunk_codes)}銘柄 / {rows}行")

    # サマリ
    print()
    print(f"=== 完了 [{mode}] ===")
    print(f"  対象銘柄数: {len(tickers):,}")
    print(f"  追加行数  : {new_rows:,}")
    print(f"  内訳:")
    for reason, cnt in reason_count.most_common():
        print(f"    {reason:<28} {cnt:>6,}")
    if dry_run:
        print(f"\n  ※ DRY RUN — BigQuery への投入はしていません")


def run_single(ticker, dry_run=False):
    mode = "DRY" if dry_run else "LIVE"
    print(f"=== Single Test: {ticker} [{mode}] ===")

    print(f"  既存最大日付を取得中...")
    latest_dates = get_latest_dates()
    latest = latest_dates.get(ticker)
    print(f"  {ticker} の現在の MAX(date): {latest}")

    df, reason = fetch_yfinance(ticker, latest)
    if df is None or df.empty:
        print(f"  結果: スキップ (reason={reason})")
        return

    print(f"  取得行数: {len(df)} (reason={reason})")
    print(df.to_string(index=False))

    if not dry_run:
        rows = upload_chunk([df])
        print(f"  -> BQ 投入: {rows} 行")
    else:
        print(f"  -> DRY RUN: 投入していません")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry",    action="store_true",
                        help="DRY RUN (BQ 書き込みなし)")
    parser.add_argument("--limit",  type=int, default=None,
                        help="先頭N銘柄のみ処理 (動作確認用)")
    parser.add_argument("--ticker", type=str, default=None,
                        help="単一銘柄テスト (例: 7203)")
    args = parser.parse_args()

    if args.ticker:
        run_single(args.ticker, dry_run=args.dry)
    else:
        run(dry_run=args.dry, limit=args.limit)
