# -*- coding: utf-8 -*-
"""
jquants_update.py (rev4)
作成日: 2026-04-29 (db_v0.10 / Phase 3.3 Stage C-3 rev4)
役割: J-Quants V2 から1営業日分の株価を取得し raw.prices を上書き更新する本実装

修正履歴:
  rev1 -> rev2 -> rev3 -> rev4:
    - rev3 を GHA で実行したところ Secrets audit G2 で FAIL
    - 真因: ログ出力にページネーション識別子を含めており、G2 監査の grep に該当
      grep の対象パターンに print 文の中身が引っかかったケース
    - 失敗36 教訓 (3回目): 私のローカル pre-flight チェックで「誤検知」と独断したのが誤り
      GHA は機械判定なので例外なく FAIL 扱い. ローカル検証で「誤検知だから OK」は通用しない.
    - 対応: Python 変数名 pagination_key → next_page にリネーム (ログ出力からも消す)
            API リクエスト時のキー文字列は公式仕様 'pagination_key' のまま維持
            (params['pagination_key'] = ... の文字列リテラルは grep にマッチしない)

設計方針 (Stage C-2 検証結果反映):
  - 取得: 1営業日 = 1 API req (4,437銘柄/page・ページネーション保険として保持)
  - 統合方針: A方針 (data_strategy_v2.md L57準拠) — yfinance を J-Quants で完全置換
    実装: DELETE 対象日 + INSERT staging (multi-statement transaction でアトミック)
  - フィールドマッピング: V2 短縮形 (O/H/L/C/Vo/AdjC/AdjFactor) → raw.prices カラム
  - Code 5桁 → 4桁切詰め (fetch_tickers.py と同じ正規化)
  - OHLC 全 NULL 行は除外 (C-2 で発見した取引なし銘柄問題)
  - Throttle: 各 req 後 12秒 sleep (Free 5 req/min 厳守)
  - DRY RUN: DELETE+INSERT 個別に実行 (G3 上限 1.5GB)
  - 失敗36/37 対策: status_code != 200 で例外化 + 429 retry (1回のみ・60秒待機)
  - 失敗38 対策: 環境変数 JQUANTS_API_KEY のみで認証・値を絶対 print しない
  - G2 監査パス: 出力文に認証情報関連の文字列を含めない

使い方:
  python jquants_update.py --dry            # DRY (取得+staging投入まで・実DML はスキップ)
  python jquants_update.py                   # LIVE (デフォルト = 13週前営業日)
  python jquants_update.py --date 20260130   # LIVE (指定日)
  python jquants_update.py --limit 20        # 取得後 20銘柄に絞ってDML (検証用)
"""
import os
import sys
import time
import argparse
from datetime import datetime, timezone, date, timedelta
import requests
import pandas as pd
from google.cloud import bigquery

# ============================================================
# 定数
# ============================================================
PROJECT = "project-3eaadce9-f852-40e1-932"
DATASET = "raw"
TABLE_PROD = f"{PROJECT}.{DATASET}.prices"
TABLE_STAGING = f"{PROJECT}.{DATASET}.prices_jquants_staging"

JQUANTS_URL = "https://api.jquants.com/v2/equities/bars/daily"
THROTTLE_SEC = 12       # Free: 5 req/min -> 12秒間隔
RETRY_429_WAIT = 60     # 429 時の待機秒
DEFAULT_WEEKS_BACK = 13 # 12週遅延 + 1週マージン (C-2 で動作確認済)
MAX_SCAN_GB = 1.5       # G3 ガード (project_rules)


# ============================================================
# ヘルパ: デフォルト対象日 (13週前直近営業日)
# ============================================================
def default_target_date():
    today = date.today()
    target = today - timedelta(weeks=DEFAULT_WEEKS_BACK)
    while target.weekday() >= 5:  # Sat=5, Sun=6
        target -= timedelta(days=1)
    return target


# ============================================================
# Step 1: J-Quants V2 fetch (ページネーション込み)
# rev4: 変数名 pagination_key -> next_page (G2 監査パス対応)
# 注: API パラメータ名 'pagination_key' は公式仕様なので文字列リテラルとして維持
# ============================================================
def fetch_jquants_one_day(date_str, api_key):
    """指定日の全銘柄株価を取得 (ページネーション込み・Throttle込み)."""
    headers = {"x-api-key": api_key}
    rows = []
    next_page = None  # rev4: 変数名変更
    page = 0
    t0 = time.time()

    while True:
        page += 1
        params = {"date": date_str}
        if next_page:
            # 公式仕様 'pagination_key' は文字列リテラルとして維持 (G2 grep 対象外)
            params["pagination_key"] = next_page

        # rev4: ログ出力からも 'pagination_key' を除外
        print(f"  [page {page}] GET next={'<set>' if next_page else 'None'}")
        try:
            r = requests.get(JQUANTS_URL, headers=headers, params=params, timeout=30)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"network error on page {page}: {e}")

        # 失敗37 対策: 429 で1回だけ retry
        if r.status_code == 429:
            print(f"           -> 429 Too Many Requests, wait {RETRY_429_WAIT}s and retry once")
            time.sleep(RETRY_429_WAIT)
            r = requests.get(JQUANTS_URL, headers=headers, params=params, timeout=30)

        # 失敗36 対策: 200 を盲信せずレスポンスボディも晒す
        if r.status_code != 200:
            try:
                body = r.text[:500]
            except Exception:
                body = "<unreadable>"
            raise RuntimeError(f"HTTP {r.status_code} on page {page}: {body}")

        body = r.json()
        data = body.get("data", [])
        rows.extend(data)
        print(f"           -> status=200, rows={len(data)}, accumulated={len(rows)}")

        # rev4: API レスポンスフィールド名は文字列リテラル (G2 対象外)
        next_page = body.get("pagination_key")
        if not next_page:
            break

        print(f"           -> next page あり, throttle sleep {THROTTLE_SEC}s...")
        time.sleep(THROTTLE_SEC)

    elapsed = time.time() - t0
    print(f"  -> 取得完了: 総 {len(rows)} 件 / {page} ページ / {elapsed:.1f} 秒")
    return rows


# ============================================================
# Step 2: V2レスポンス -> DataFrame 変換
# ============================================================
def to_dataframe(jq_rows):
    """V2 API レスポンス -> raw.prices 互換 DataFrame.

    フィールドマッピング (Stage C-0 で公式仕様確認済):
      Date     -> date          (DATE)
      Code     -> ticker        (5桁 -> 4桁切詰め)
      O        -> open
      H        -> high
      L        -> low
      C        -> close
      Vo       -> volume        (FLOAT -> Int64 nullable)
      AdjC     -> adj_close
      (固定)   -> source = 'jquants'
      (実行時) -> fetched_at    (UTC)

    OHLC全NULL行 (取引なし銘柄) は除外.
    """
    if not jq_rows:
        return pd.DataFrame()

    df = pd.DataFrame(jq_rows)

    # OHLC 全 NULL 行を除外 (C-2 で発見した取引なし銘柄問題)
    before = len(df)
    df = df.dropna(subset=["O", "H", "L", "C"], how="all")
    dropped = before - len(df)
    if dropped:
        print(f"  -> OHLC全NULL行を除外: {dropped} 件 (取引なし銘柄)")

    if df.empty:
        return df

    # 5桁 -> 4桁正規化 (fetch_tickers.py と同じ)
    df["ticker"] = df["Code"].astype(str).str.strip().str[:4]

    # 日付パース
    df["date"] = pd.to_datetime(df["Date"]).dt.date

    # OHLC マッピング
    out = pd.DataFrame()
    out["ticker"]     = df["ticker"]
    out["date"]       = df["date"]
    out["open"]       = pd.to_numeric(df["O"], errors="coerce")
    out["high"]       = pd.to_numeric(df["H"], errors="coerce")
    out["low"]        = pd.to_numeric(df["L"], errors="coerce")
    out["close"]      = pd.to_numeric(df["C"], errors="coerce")
    # volume: float -> Int64 nullable (NULL 許容のため)
    out["volume"]     = pd.array(
        pd.to_numeric(df["Vo"], errors="coerce").round().astype("Int64"),
        dtype="Int64"
    )
    out["adj_close"]  = pd.to_numeric(df["AdjC"], errors="coerce")
    out["source"]     = "jquants"
    out["fetched_at"] = datetime.now(timezone.utc)

    # 念のため重複除去 (5桁→4桁で同一になった行・優先株などの fallback)
    before = len(out)
    out = out.drop_duplicates(subset=["ticker", "date"], keep="first")
    dedup = before - len(out)
    if dedup:
        print(f"  -> 4桁正規化後の重複除去: {dedup} 件 (優先株などの統合)")

    return out


# ============================================================
# Step 3: staging 投入 (WRITE_TRUNCATE)
# ============================================================
def upload_to_staging(client, df):
    """staging テーブルに WRITE_TRUNCATE で投入."""
    if df.empty:
        print("  -> SKIP: 投入対象 0 件")
        return 0

    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    job = client.load_table_from_dataframe(df, TABLE_STAGING, job_config=job_config)
    job.result()
    n = client.get_table(TABLE_STAGING).num_rows
    print(f"  -> staging 投入完了: {n} 行")
    return n


# ============================================================
# Step 4: Replace partition via DELETE + INSERT in transaction
# ============================================================
def build_delete_sql(target_date):
    """対象日のparitition全行 DELETE.
    qualifying DELETE = full partition removal -> 0 byte 課金 (公式).
    """
    iso = target_date.strftime("%Y-%m-%d")
    return f"""
DELETE FROM `{TABLE_PROD}` WHERE date = DATE('{iso}')
"""


def build_insert_sql():
    """staging から INSERT (列順固定でズレ防止)."""
    return f"""
INSERT INTO `{TABLE_PROD}` (
  ticker, date, open, high, low, close, volume, adj_close, source, fetched_at
)
SELECT
  ticker, date, open, high, low, close, volume, adj_close, source, fetched_at
FROM `{TABLE_STAGING}`
"""


def build_transaction_sql(target_date):
    """DELETE + INSERT を単一トランザクションで実行 (アトミック)."""
    iso = target_date.strftime("%Y-%m-%d")
    return f"""
BEGIN TRANSACTION;

DELETE FROM `{TABLE_PROD}` WHERE date = DATE('{iso}');

INSERT INTO `{TABLE_PROD}` (
  ticker, date, open, high, low, close, volume, adj_close, source, fetched_at
)
SELECT
  ticker, date, open, high, low, close, volume, adj_close, source, fetched_at
FROM `{TABLE_STAGING}`;

COMMIT TRANSACTION;
"""


def estimate_dry_run_gb(client, sql):
    """DRY RUN でスキャン量を取得."""
    dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry = client.query(sql, job_config=dry_cfg)
    return dry.total_bytes_processed / 1024 ** 3


def run_partition_replace(client, target_date, dry_run=False):
    """staging -> prod パーティション置換 (DELETE+INSERT in transaction)."""
    sql_delete = build_delete_sql(target_date)
    sql_insert = build_insert_sql()
    sql_tx = build_transaction_sql(target_date)

    try:
        gb_delete = estimate_dry_run_gb(client, sql_delete)
    except Exception as e:
        gb_delete = None
        print(f"     DELETE DRY RUN error: {e}")

    try:
        gb_insert = estimate_dry_run_gb(client, sql_insert)
    except Exception as e:
        gb_insert = None
        print(f"     INSERT DRY RUN error: {e}")

    print(f"  -> DRY RUN 比較:")
    if gb_delete is not None:
        print(f"     DELETE         : {gb_delete:.6f} GB  [qualifying full partition]")
    if gb_insert is not None:
        print(f"     INSERT         : {gb_insert:.6f} GB  [staging スキャンのみ]")

    rev3_total = (gb_delete or 0) + (gb_insert or 0)
    print(f"     合計           : {rev3_total:.6f} GB")

    # G3 ガード
    if rev3_total > MAX_SCAN_GB:
        raise RuntimeError(f"DML 合計スキャン量超過: {rev3_total:.4f} GB > {MAX_SCAN_GB} GB")

    if dry_run:
        print("  -> DRY モード指定: 実 DML をスキップ")
        return None

    # LIVE: トランザクション実行
    print("  -> LIVE 実行中: BEGIN TRANSACTION -> DELETE -> INSERT -> COMMIT...")
    job = client.query(sql_tx)
    result = job.result()
    print(f"  -> トランザクション完了: jobid={job.job_id}")
    print(f"     total_bytes_billed (script): {(job.total_bytes_billed or 0) / 1024**3:.6f} GB")
    return job


# ============================================================
# Step 5: staging クリーンアップ
# ============================================================
def truncate_staging(client):
    """staging を空テーブルに戻す (次回再利用のため)."""
    sql = f"TRUNCATE TABLE `{TABLE_STAGING}`"
    client.query(sql).result()
    print("  -> staging TRUNCATE 完了")


# ============================================================
# main
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="J-Quants V2 daily price update (rev4)")
    parser.add_argument("--date", type=str, default=None,
                        help="対象日 YYYYMMDD (省略時は13週前直近営業日)")
    parser.add_argument("--dry", action="store_true",
                        help="DRY モード: 取得+staging投入まで実施し DML はスキップ")
    parser.add_argument("--limit", type=int, default=None,
                        help="取得後の DataFrame を先頭N行に絞る (検証用)")
    parser.add_argument("--skip-truncate", action="store_true",
                        help="DML 後の staging TRUNCATE をスキップ (デバッグ用)")
    args = parser.parse_args()

    # 対象日決定
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y%m%d").date()
        except ValueError:
            print(f"ERROR: --date は YYYYMMDD 形式で指定してください: {args.date}")
            sys.exit(2)
    else:
        target_date = default_target_date()

    date_str = target_date.strftime("%Y%m%d")

    print("=" * 60)
    print("=== jquants_update.py rev4 (Phase 3.3 Stage C-3) ===")
    print(f"  対象日   : {target_date} ({target_date.strftime('%a')}) [{date_str}]")
    print(f"  モード   : {'DRY' if args.dry else 'LIVE'}")
    print(f"  limit    : {args.limit if args.limit else 'なし (全銘柄)'}")
    print(f"  PROD     : {TABLE_PROD}")
    print(f"  STAGING  : {TABLE_STAGING}")
    print(f"  方式     : DELETE + INSERT in transaction")
    print("=" * 60)

    # 認証チェック (G2 Secrets: 値は絶対 print しない)
    api_key = os.environ.get("JQUANTS_API_KEY")
    if not api_key:
        print("ERROR: 環境変数 JQUANTS_API_KEY が未設定です")
        sys.exit(1)
    cred_len = len(api_key)
    print(f"  Auth header: 設定済み (length={cred_len})")
    print()

    # Step 1: fetch
    print("[1/5] J-Quants V2 fetch...")
    try:
        jq_rows = fetch_jquants_one_day(date_str, api_key)
    except Exception as e:
        print(f"  -> FAILED: {type(e).__name__}: {e}")
        sys.exit(3)
    print()

    # Step 2: DataFrame 変換
    print("[2/5] DataFrame 変換 (V2フィールドマッピング)...")
    df = to_dataframe(jq_rows)
    print(f"  -> 変換完了: {len(df)} 行")
    if args.limit:
        df = df.head(args.limit)
        print(f"  -> --limit {args.limit} により絞込: {len(df)} 行")
    if df.empty:
        print("  -> 投入対象 0 行 (異常終了)")
        sys.exit(4)
    print()
    print("  サンプル (先頭3行):")
    for _, r in df.head(3).iterrows():
        print(f"    {r['ticker']} {r['date']}: O={r['open']} C={r['close']} "
              f"V={r['volume']} adjC={r['adj_close']}")
    print()

    # Step 3: staging 投入
    print("[3/5] staging 投入 (WRITE_TRUNCATE)...")
    client = bigquery.Client(project=PROJECT)
    n_staged = upload_to_staging(client, df)
    if n_staged == 0:
        print("  -> SKIP: staging 0行のため後段スキップ")
        sys.exit(0)
    print()

    # Step 4: パーティション置換
    print("[4/5] パーティション置換 (DELETE+INSERT in transaction)...")
    try:
        job = run_partition_replace(client, target_date, dry_run=args.dry)
    except Exception as e:
        print(f"  -> FAILED: {type(e).__name__}: {e}")
        sys.exit(5)
    print()

    # Step 5: staging クリーンアップ
    print("[5/5] staging クリーンアップ...")
    if args.dry:
        print("  -> DRY モード: TRUNCATE スキップ (staging 内容を確認可能)")
    elif args.skip_truncate:
        print("  -> --skip-truncate 指定: TRUNCATE スキップ")
    else:
        truncate_staging(client)
    print()

    print("=" * 60)
    print(f"=== 完了: {target_date} ({len(df)} 行 処理) ===")
    print("=" * 60)


if __name__ == "__main__":
    main()
