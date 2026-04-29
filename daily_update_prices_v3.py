"""
daily_update_prices_v3.py - yfinance 日次株価差分更新 (db_v0.9 / Phase 3.2.1)
                            v3 / 失敗36 (yfinance rate limit) 対応

機能:
  raw.prices に存在しない (ticker, date) を yfinance から取得し追記する。
  毎日 16:30 JST 想定 (東証大引け 15:30 + 反映マージン1h)。

設計原則 (v2 から継承):
  - 完全無料 (BigQuery 無料枠維持)
  - パーティションフィルタ必須 (§4)
  - SELECT * 禁止 (§4)
  - ストリーミング挿入禁止 / load_table_from_dataframe 使用 (§4)
  - DRY RUN は BQ 書き込みを行わない
  - latest_date=None の銘柄は no_baseline_skip (失敗31対応・継続)

【v3 変更内容 / 失敗36 対応】
  v2 では yf.Ticker(...).history() を per-ticker で叩いていたため、
  GHA Ubuntu ランナーで YFRateLimitError が大量発生 (10/10失敗)。

  v3 修正:
  (a) yf.download(tickers=[...], group_by='ticker') でチャンク50銘柄を一括取得。
      これにより API 呼び出し数を 1/50 に削減。
  (b) チャンクごとに retry (exponential backoff: 30s -> 60s -> 120s)。
  (c) チャンク全体が失敗した場合は per-ticker fallback に降格。
  (d) 失敗率 > 50% で job 全体を fail させる (P2-3 採用)。
  (e) yfinance 1.0系 を requirements.txt で要求 (crumb/cookie/rate-limit 修正含む)。
  (f) reason 種別を拡張: rate_limit_retry_exhausted, bulk_fail_fallback_ok 等。

依存: initial_import.py の投入結果 (raw.prices, raw.tickers)
      yfinance>=1.0.0,<2.0.0 (requirements.txt)

CLI:
  python daily_update_prices_v3.py --ticker 7203 --dry    # 単体 DRY
  python daily_update_prices_v3.py --ticker 7203          # 単体本番
  python daily_update_prices_v3.py --limit 10 --dry       # 10銘柄 DRY
  python daily_update_prices_v3.py --dry                  # 全銘柄 DRY
  python daily_update_prices_v3.py                        # 全銘柄本番
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

CHUNK_SIZE        = 50    # チャンク投入サイズ (銘柄) v2 から維持
SCAN_DAYS         = 400   # MAX(date) 取得時のパーティション範囲 (日) v2 から維持
MAX_SCAN_GB       = 1.5   # スキャン量上限 v2 から維持
SLEEP_BETWEEN_CHUNK = 2.0   # チャンク間スリープ (秒) v3: 1.0 -> 2.0 (rate-limit 緩和)
RETRY_MAX         = 3     # チャンク取得 retry 回数
RETRY_BASE_SLEEP  = 30    # retry 待機基数 (秒) -> 30, 60, 120
FAIL_RATIO_LIMIT  = 0.5   # 失敗率がこれを超えたら job 全体を fail

client = bigquery.Client(project=PROJECT)


# ---------------------------------------------------------------------------
# BigQuery helpers (v2 から無変更)
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
    sql = f"""
        SELECT ticker, MAX(`date`) AS max_date
        FROM `{TABLE_PRICES}`
        WHERE `date` >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL {SCAN_DAYS} DAY)
        GROUP BY ticker
    """
    dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry_job = client.query(sql, job_config=dry_cfg)
    gb = dry_job.total_bytes_processed / 1e9
    print(f"  [BQ DRY] get_latest_dates scan: {gb:.4f} GB")
    if gb > MAX_SCAN_GB:
        raise RuntimeError(
            f"スキャン量が上限超過: {gb:.2f} GB > {MAX_SCAN_GB} GB. "
            "SQL を見直してください"
        )
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
# yfinance fetch (v3 改修部分)
# ---------------------------------------------------------------------------
def _build_record_df(ticker, df_one, latest_date):
    """
    1銘柄分の生 yfinance DataFrame を raw.prices スキーマに整形して返す.
    latest_date 以前の行は除外.
    返り値: (整形済 DataFrame or None, reason_str)
    """
    if df_one is None or df_one.empty:
        return None, "empty_response"

    df_one = df_one.dropna(how="all")
    if df_one.empty:
        return None, "empty_response"

    df_one = df_one.reset_index()
    # yfinance が返す日付列名は 'Date' or 'Datetime'
    date_col = "Date" if "Date" in df_one.columns else "Datetime"
    df_one["date"] = pd.to_datetime(df_one[date_col]).dt.tz_localize(None).dt.date

    df_one = df_one[df_one["date"] > latest_date]
    if df_one.empty:
        return None, "no_new_rows"

    # Open/High/Low/Close/Volume 欠損行を除外
    df_one = df_one.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if df_one.empty:
        return None, "all_rows_nan"

    out = pd.DataFrame()
    out["ticker"]     = [ticker] * len(df_one)
    out["date"]       = df_one["date"].values
    out["open"]       = df_one["Open"].round(2).values
    out["high"]       = df_one["High"].round(2).values
    out["low"]        = df_one["Low"].round(2).values
    out["close"]      = df_one["Close"].round(2).values
    out["volume"]     = pd.array(df_one["Volume"].values, dtype="Int64")
    out["adj_close"]  = df_one["Close"].round(2).values
    out["source"]     = "yfinance"
    out["fetched_at"] = datetime.now(timezone.utc)
    return out, "ok"


def fetch_yfinance_bulk(tickers_chunk, latest_dates):
    """
    チャンク (最大 CHUNK_SIZE 銘柄) をまとめて yf.download で取得.

    返り値: dict {ticker: (DataFrame or None, reason_str)}
    """
    # 各 ticker の取得開始日を決定 (チャンク内の最早日付を使う)
    starts = []
    eligible = []  # (ticker, latest_date) のリスト
    skipped = {}   # 取得不要な ticker は事前に reason を確定
    today = date.today()

    for code in tickers_chunk:
        latest = latest_dates.get(code)
        if latest is None:
            skipped[code] = (None, "no_baseline_skip")
            continue
        start = latest + timedelta(days=1)
        if start > today:
            skipped[code] = (None, "already_up_to_date")
            continue
        starts.append(start)
        eligible.append((code, latest))

    # 全銘柄スキップなら早期リターン
    if not eligible:
        return skipped

    earliest_start = min(starts)
    yf_tickers = [f"{c}.T" for c, _ in eligible]
    yf_to_code = {f"{c}.T": c for c, _ in eligible}
    latest_map = dict(eligible)

    # チャンク取得 (retry 付き)
    df_bulk = None
    last_err_type = None
    for attempt in range(RETRY_MAX):
        try:
            df_bulk = yf.download(
                tickers=yf_tickers,
                start=earliest_start.isoformat(),
                progress=False,
                threads=True,
                group_by="ticker",
                auto_adjust=False,
            )
            if df_bulk is not None and not df_bulk.empty:
                break
        except Exception as e:
            last_err_type = type(e).__name__
            if attempt < RETRY_MAX - 1:
                wait = RETRY_BASE_SLEEP * (2 ** attempt)
                print(f"    [retry] {last_err_type} -> wait {wait}s "
                      f"(attempt {attempt + 1}/{RETRY_MAX})")
                time.sleep(wait)
            continue

    # 全 retry 失敗
    if df_bulk is None or df_bulk.empty:
        # per-ticker fallback に降格
        result = dict(skipped)
        for code, latest in eligible:
            df_one, reason = _fetch_single_fallback(code, latest)
            if reason == "ok":
                result[code] = (df_one, "bulk_fail_fallback_ok")
            else:
                result[code] = (None, f"rate_limit_retry_exhausted:{reason}")
        return result

    # チャンク取得成功 -> ticker 別に分割
    result = dict(skipped)
    for yf_t, code in yf_to_code.items():
        latest = latest_map[code]

        # group_by='ticker' の場合 columns は MultiIndex (ticker, field)
        try:
            if isinstance(df_bulk.columns, pd.MultiIndex):
                if yf_t not in df_bulk.columns.get_level_values(0):
                    result[code] = (None, "missing_in_response")
                    continue
                df_one = df_bulk[yf_t].copy()
            else:
                # 単一銘柄の場合 MultiIndex にならない
                df_one = df_bulk.copy()
        except KeyError:
            result[code] = (None, "missing_in_response")
            continue

        out, reason = _build_record_df(code, df_one, latest)
        result[code] = (out, reason)

    return result


def _fetch_single_fallback(code, latest_date):
    """
    バルク失敗時の per-ticker fallback. v2 と同等のロジック.
    """
    today = date.today()
    start = latest_date + timedelta(days=1)
    if start > today:
        return None, "already_up_to_date"
    try:
        df = yf.Ticker(f"{code}.T").history(start=start.isoformat())
    except Exception as e:
        return None, f"fetch_error:{type(e).__name__}"
    out, reason = _build_record_df(code, df, latest_date)
    return out, reason


def fetch_yfinance(code, latest_date):
    """
    単一銘柄取得 (run_single 用).
    """
    if latest_date is None:
        return None, "no_baseline_skip"
    return _fetch_single_fallback(code, latest_date)


# ---------------------------------------------------------------------------
# Main runners
# ---------------------------------------------------------------------------
def run(dry_run=False, limit=None):
    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"=== Daily Update Prices v3 [{mode}] ===")
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
    print(f"  チャンクサイズ: {CHUNK_SIZE} (バルク取得)")

    new_rows     = 0
    reason_count = Counter()

    # チャンク単位でループ
    total_chunks = (len(tickers) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for chunk_idx in range(total_chunks):
        start_i = chunk_idx * CHUNK_SIZE
        end_i = min(start_i + CHUNK_SIZE, len(tickers))
        chunk = tickers[start_i:end_i]

        # バルク取得
        results = fetch_yfinance_bulk(chunk, latest_dates)

        # チャンク内の有効 DataFrame を集める
        chunk_dfs   = []
        chunk_codes = []
        for code in chunk:
            df, reason = results.get(code, (None, "missing_in_response"))
            reason_count[reason] += 1
            if df is not None and not df.empty:
                chunk_dfs.append(df)
                chunk_codes.append(code)

        # チャンク投入
        if chunk_dfs:
            rows = upload_chunk(chunk_dfs, dry_run=dry_run)
            new_rows += rows
            tag = "DRY-投入" if dry_run else "投入"
            print(f"  >>> {tag}: chunk {chunk_idx + 1:>3}/{total_chunks} "
                  f"{len(chunk_codes)}銘柄 / {rows}行 (累計: {new_rows:,})")
        else:
            # 静かなチャンク (全 already_up_to_date 等) は heartbeat だけ
            if (chunk_idx + 1) % 10 == 0:
                print(f"  [progress] chunk {chunk_idx + 1:>3}/{total_chunks}, "
                      f"new_rows={new_rows:,}")

        time.sleep(SLEEP_BETWEEN_CHUNK)

    # サマリ
    print()
    print(f"=== 完了 [{mode}] ===")
    print(f"  対象銘柄数: {len(tickers):,}")
    print(f"  追加行数  : {new_rows:,}")
    print(f"  内訳:")
    for reason, cnt in reason_count.most_common():
        print(f"    {reason:<32} {cnt:>6,}")
    if dry_run:
        print(f"\n  ※ DRY RUN — BigQuery への投入はしていません")

    # 失敗率チェック (P2-3)
    fail_keys = [k for k in reason_count if k.startswith("rate_limit_retry_exhausted")
                 or k.startswith("fetch_error")]
    fail_count = sum(reason_count[k] for k in fail_keys)
    eligible = len(tickers) - reason_count.get("no_baseline_skip", 0) \
                            - reason_count.get("already_up_to_date", 0)
    if eligible > 0:
        ratio = fail_count / eligible
        print(f"\n  失敗率: {fail_count}/{eligible} = {ratio:.2%} "
              f"(上限 {FAIL_RATIO_LIMIT:.0%})")
        if ratio > FAIL_RATIO_LIMIT:
            raise RuntimeError(
                f"失敗率が上限超過: {ratio:.2%} > {FAIL_RATIO_LIMIT:.0%}. "
                "yfinance のレート制限が強い可能性. 別日に再試行してください."
            )


def run_single(ticker, dry_run=False):
    mode = "DRY" if dry_run else "LIVE"
    print(f"=== Single Test v3: {ticker} [{mode}] ===")

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
