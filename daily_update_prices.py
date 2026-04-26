"""
daily_update_prices.py - yfinance 譌･谺｡譬ｪ萓｡蟾ｮ蛻・峩譁ｰ (db_v0.7 / Phase 3.1)
                        v2 / 螟ｱ謨・1 蟇ｾ蠢・
讖溯・:
  raw.prices 縺ｫ蟄伜惠縺励↑縺・(ticker, date) 繧・yfinance 縺九ｉ蜿門ｾ励＠霑ｽ險倥☆繧九・  豈取律 16:30 JST 諠ｳ螳・(譚ｱ險ｼ螟ｧ蠑輔￠ 15:30 + 蜿肴丐繝槭・繧ｸ繝ｳ1h)縲・
險ｭ險亥次蜑・
  - 螳悟・辟｡譁・(BigQuery 辟｡譁呎棧邯ｭ謖・
  - 繝代・繝・ぅ繧ｷ繝ｧ繝ｳ繝輔ぅ繝ｫ繧ｿ蠢・・(ﾂｧ4)
  - SELECT * 遖∵ｭ｢ (ﾂｧ4)
  - 繧ｹ繝医Μ繝ｼ繝溘Φ繧ｰ謖ｿ蜈･遖∵ｭ｢ / load_table_from_dataframe 菴ｿ逕ｨ (ﾂｧ4)
  - DRY RUN 縺ｯ BQ 譖ｸ縺崎ｾｼ縺ｿ繧定｡後ｏ縺ｪ縺・・    譛ｬ繧ｹ繧ｯ繝ｪ繝励ヨ縺ｯ checkpoint 繧剃ｽｿ繧上↑縺・◆繧・SR-10 閾ｪ蜍墓ｺ匁侠縲・
縲迅2 螟画峩蜀・ｮｹ / 螟ｱ謨・1 蟇ｾ蠢懊・  v1 縺ｧ縺ｯ SCAN_DAYS=30 / NEW_TICKER_DAYS=60 縺ｮ繝溘せ繝槭ャ繝√〒縲・  raw.prices 縺ｮ譛邨ゅョ繝ｼ繧ｿ縺・30譌･莉･荳雁燕縺ｮ驫俶氛縺ｫ蟇ｾ縺励・  no_baseline_fallback 邨瑚ｷｯ縺ｧ 60譌･蜑阪°繧牙・蜿門ｾ励＠縲∵里蟄倥ョ繝ｼ繧ｿ縺ｨ驥崎､・＠縺溘・
  v2 菫ｮ豁｣:
  (a) SCAN_DAYS 繧・30 竊・400 縺ｫ諡｡螟ｧ (5蟷ｴ髢薙・縺・■譛霑・蟷ｴ蠑ｷ繧偵き繝舌・)縲・      縺薙ｌ縺ｫ繧医ｊ縲√＠縺ｰ繧峨￥繝・・繧ｿ譖ｴ譁ｰ縺後↑縺・釜譟・ｂ latest_date 繧貞叙繧後ｋ縲・  (b) no_baseline_fallback 邨瑚ｷｯ繧貞ｻ・ｭ｢縲Ｍatest_date=None 縺ｮ驫俶氛縺ｯ
      reason='no_baseline_skip' 縺ｧ繧ｹ繧ｭ繝・・縺吶ｋ (驥崎､・・蜿ｯ閭ｽ諤ｧ繧堤ｵｶ縺､)縲・      譛ｬ蠖薙・譁ｰ隕城釜譟・・蛻晏屓謚募・縺ｯ initial_import.py 縺ｮ雋ｬ蜍吶→縺吶ｋ縲・
萓晏ｭ・ initial_import.py 縺ｮ謚募・邨先棡 (raw.prices, raw.tickers)

CLI:
  python daily_update_prices.py --ticker 7203 --dry    # 蜊倅ｽ・DRY
  python daily_update_prices.py --ticker 7203          # 蜊倅ｽ捺悽逡ｪ
  python daily_update_prices.py --limit 10 --dry       # 10驫俶氛 DRY
  python daily_update_prices.py --dry                  # 蜈ｨ驫俶氛 DRY
  python daily_update_prices.py                        # 蜈ｨ驫俶氛譛ｬ逡ｪ
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

CHUNK_SIZE      = 50    # 繝√Ε繝ｳ繧ｯ謚募・繧ｵ繧､繧ｺ (驫俶氛)
SCAN_DAYS       = 400   # MAX(date) 蜿門ｾ玲凾縺ｮ繝代・繝・ぅ繧ｷ繝ｧ繝ｳ遽・峇 (譌･) 竊・v2: 30竊・00
MAX_SCAN_GB     = 1.5   # 繧ｹ繧ｭ繝｣繝ｳ驥丈ｸ企剞 (v2: 1.0竊・.5 縺ｫ諡｡螟ｧ縲ヾCAN_DAYS諡｡螟ｧ縺ｫ蟇ｾ蠢・
SLEEP_FETCH     = 0.5   # yfinance 蜻ｼ縺ｳ蜃ｺ縺鈴俣髫・(遘・
SLEEP_CHUNK     = 1.0   # 繝√Ε繝ｳ繧ｯ謚募・髢馴囈 (遘・
# NEW_TICKER_DAYS 蟒・ｭ｢ (v2 / 螟ｱ謨・1蟇ｾ蠢・

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
    蜷・ticker 縺ｮ迴ｾ蝨ｨ縺ｮ MAX(date) 繧剃ｸ諡ｬ蜿門ｾ励・    繝代・繝・ぅ繧ｷ繝ｧ繝ｳ繝輔ぅ繝ｫ繧ｿ繧貞ｿ・★縺九￠縲．RY RUN 縺ｧ繧ｹ繧ｭ繝｣繝ｳ驥上ｒ遒ｺ隱阪☆繧・(ﾂｧ4 / G3)縲・    """
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
            f"繧ｹ繧ｭ繝｣繝ｳ驥上′荳企剞雜・℃: {gb:.2f} GB > {MAX_SCAN_GB} GB. "
            "SQL 繧定ｦ狗峩縺励※縺上□縺輔＞"
        )

    # 譛ｬ螳溯｡・    return {row.ticker: row.max_date for row in client.query(sql).result()}


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
    latest_date 縺ｮ鄙梧律莉･髯阪・繝・・繧ｿ繧・yfinance 縺九ｉ蜿門ｾ励・
    v2 螟画峩: latest_date=None 縺ｮ驫俶氛縺ｯ繝輔か繝ｼ繝ｫ繝舌ャ繧ｯ縺帙★繧ｹ繧ｭ繝・・縺吶ｋ
            (驥崎､・・蜿ｯ閭ｽ諤ｧ繧堤ｵｶ縺､縲ょ､ｱ謨・1蟇ｾ蠢・
            逵溘・譁ｰ隕城釜譟・・蛻晏屓謚募・縺ｯ initial_import.py 縺ｮ雋ｬ蜍吶・
    霑斐ｊ蛟､: (DataFrame or None, reason_str)
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
        # 萓句､悶Γ繝・そ繝ｼ繧ｸ縺ｯ type 縺ｮ縺ｿ. secret 貍乗ｴｩ髦ｲ豁｢縺ｮ縺溘ａ隧ｳ邏ｰ縺ｯ蜃ｺ蜉帙＠縺ｪ縺・        return None, f"fetch_error:{type(e).__name__}"

    if df.empty:
        return None, "empty_response"

    df = df.reset_index()
    df["date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.date

    # 螳牙・遲・ latest_date 莉･蜑阪・陦後ｒ遒ｺ螳溘↓髯､螟・    df = df[df["date"] > latest_date]
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
    print(f"  螳溯｡梧凾蛻ｻ (JST): {datetime.now().isoformat(timespec='seconds')}")

    tickers = get_active_tickers()
    if limit:
        tickers = tickers[:limit]
    print(f"  蟇ｾ雎｡驫俶氛: {len(tickers):,}")

    print(f"  譌｢蟄俶怙螟ｧ譌･莉倥ｒ蜿門ｾ嶺ｸｭ (繝代・繝・ぅ繧ｷ繝ｧ繝ｳ {SCAN_DAYS} 譌･)...")
    latest_dates = get_latest_dates()
    new_count = sum(1 for t in tickers if t not in latest_dates)
    print(f"  譌｢蟄倬釜譟・ {len(latest_dates):,} / "
          f"raw.prices 縺ｫ辟｡縺・ {new_count:,}")

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

        # 騾ｲ謐励ワ繝ｼ繝医ン繝ｼ繝・(500莉ｶ豈・
        if i % 500 == 0:
            print(f"  [progress] {i:>4}/{len(tickers)} processed, "
                  f"chunk_pending={len(chunk_dfs)}, new_rows={new_rows:,}")

        # 繝√Ε繝ｳ繧ｯ謚募・
        if len(chunk_dfs) >= CHUNK_SIZE:
            rows = upload_chunk(chunk_dfs, dry_run=dry_run)
            new_rows += rows
            tag = "DRY-謚募・" if dry_run else "謚募・"
            print(f"  >>> {tag}: {len(chunk_codes)}驫俶氛 / {rows}陦・"
                  f"(邏ｯ險郁｡・ {new_rows:,}, 騾ｲ謐・ {i}/{len(tickers)})")
            chunk_dfs   = []
            chunk_codes = []
            time.sleep(SLEEP_CHUNK)
        else:
            time.sleep(SLEEP_FETCH)

    # 遶ｯ謨ｰ
    if chunk_dfs:
        rows = upload_chunk(chunk_dfs, dry_run=dry_run)
        new_rows += rows
        tag = "DRY-謚募・" if dry_run else "謚募・"
        print(f"  >>> {tag}(遶ｯ謨ｰ): {len(chunk_codes)}驫俶氛 / {rows}陦・)

    # 繧ｵ繝槭Μ
    print()
    print(f"=== 螳御ｺ・[{mode}] ===")
    print(f"  蟇ｾ雎｡驫俶氛謨ｰ: {len(tickers):,}")
    print(f"  霑ｽ蜉陦梧焚  : {new_rows:,}")
    print(f"  蜀・ｨｳ:")
    for reason, cnt in reason_count.most_common():
        print(f"    {reason:<28} {cnt:>6,}")
    if dry_run:
        print(f"\n  窶ｻ DRY RUN 窶・BigQuery 縺ｸ縺ｮ謚募・縺ｯ縺励※縺・∪縺帙ｓ")


def run_single(ticker, dry_run=False):
    mode = "DRY" if dry_run else "LIVE"
    print(f"=== Single Test: {ticker} [{mode}] ===")

    print(f"  譌｢蟄俶怙螟ｧ譌･莉倥ｒ蜿門ｾ嶺ｸｭ...")
    latest_dates = get_latest_dates()
    latest = latest_dates.get(ticker)
    print(f"  {ticker} 縺ｮ迴ｾ蝨ｨ縺ｮ MAX(date): {latest}")

    df, reason = fetch_yfinance(ticker, latest)
    if df is None or df.empty:
        print(f"  邨先棡: 繧ｹ繧ｭ繝・・ (reason={reason})")
        return

    print(f"  蜿門ｾ苓｡梧焚: {len(df)} (reason={reason})")
    print(df.to_string(index=False))

    if not dry_run:
        rows = upload_chunk([df])
        print(f"  -> BQ 謚募・: {rows} 陦・)
    else:
        print(f"  -> DRY RUN: 謚募・縺励※縺・∪縺帙ｓ")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry",    action="store_true",
                        help="DRY RUN (BQ 譖ｸ縺崎ｾｼ縺ｿ縺ｪ縺・")
    parser.add_argument("--limit",  type=int, default=None,
                        help="蜈磯ｭN驫俶氛縺ｮ縺ｿ蜃ｦ逅・(蜍穂ｽ懃｢ｺ隱咲畑)")
    parser.add_argument("--ticker", type=str, default=None,
                        help="蜊倅ｸ驫俶氛繝・せ繝・(萓・ 7203)")
    args = parser.parse_args()

    if args.ticker:
        run_single(args.ticker, dry_run=args.dry)
    else:
        run(dry_run=args.dry, limit=args.limit)
