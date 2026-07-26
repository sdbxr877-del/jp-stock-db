"""
financial_import_staging.py (db_v57 / P3 A12-A16)
Purpose: full re-fetch of yfinance annual financials into raw.financials_staging,
extended with equity / shares_outstanding / dividend_paid for PBR / DOE / market-cap.

Design notes:
  - Writes to raw.financials_staging (NOT raw.financials). The production table is
    replaced from staging only after verification (separate approval step).
  - write_disposition = WRITE_APPEND with a dedicated checkpoint so runs are
    resumable. Initialize staging (drop) and start with a fresh checkpoint before
    a full re-fetch. get_existing_tickers() syncs already-loaded tickers from
    staging into the checkpoint on resume.
  - New columns are read from the SAME yfinance objects already fetched:
      equity             <- balance_sheet (EQUITY_KEYS, reused from calc_roe)
      shares_outstanding <- balance_sheet (SHARES_KEYS)
      dividend_paid      <- cash_flow      (DIV_KEYS); raw value (Cash Dividends
                            Paid is negative = cash outflow). ABS is applied in
                            the downstream VIEW, not here.
  - Non-ASCII free (English comments/prints), UTF-8 / LF / no BOM.
"""
import os
import json
import time
import argparse
import warnings
import yfinance as yf
import pandas as pd
from google.cloud import bigquery
from datetime import datetime, timezone
from dotenv import load_dotenv
warnings.filterwarnings("ignore", category=FutureWarning)
load_dotenv(dotenv_path=r"C:\jp-stock-db\.env")
PROJECT          = "project-3eaadce9-f852-40e1-932"
TABLE_FIN        = f"{PROJECT}.raw.financials_staging"
TABLE_TICKERS    = f"{PROJECT}.raw.tickers"
CHECKPOINT       = "checkpoint_financials_staging.json"
ERROR_LIST       = "error_list_financials_staging.json"
CHUNK_SIZE       = 50
SLEEP_PER_TICKER = 1.5
MAX_CONSECUTIVE_TIMEOUTS = 5
TEST5_TICKERS = ["7203", "6758", "4385", "3687", "4382"]
client = bigquery.Client(project=PROJECT)
REVENUE_KEYS = ["Total Revenue", "Revenue", "Operating Revenue"]
OPINC_KEYS   = ["Operating Income", "Operating Revenue - Operating Expense"]
NETINC_KEYS  = ["Net Income", "Net Income Common Stockholders",
                "Net Income Continuous Operations",
                "Net Income From Continuing Operation Net Minority Interest"]
EPS_KEYS     = ["Diluted EPS", "Basic EPS"]
EQUITY_KEYS  = ["Stockholders Equity", "Common Stock Equity",
                "Total Equity Gross Minority Interest"]
SHARES_KEYS  = ["Ordinary Shares Number", "Share Issued"]
DIV_KEYS     = ["Cash Dividends Paid", "Common Stock Dividend Paid"]
def get_all_tickers():
    sql = f"SELECT ticker FROM `{TABLE_TICKERS}` WHERE is_active = TRUE ORDER BY ticker"
    return [row.ticker for row in client.query(sql).result()]
def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            return json.load(f)
    return {"done": []}
def save_checkpoint(done):
    with open(CHECKPOINT, "w") as f:
        json.dump({"done": done}, f)
def load_error_list():
    if os.path.exists(ERROR_LIST):
        with open(ERROR_LIST) as f:
            return json.load(f)
    return {"errors": []}
def save_error_list(errors):
    with open(ERROR_LIST, "w") as f:
        json.dump({"errors": errors}, f)
def safe_get(df, keys, col):
    if df is None or df.empty:
        return None
    for k in keys:
        if k in df.index:
            try:
                v = df.loc[k, col]
                if pd.isna(v):
                    continue
                return float(v)
            except (KeyError, ValueError, TypeError):
                continue
    return None
def calc_roe(fin, bs, col):
    if fin is None or bs is None:
        return None
    ni = safe_get(fin, NETINC_KEYS, col)
    eq = safe_get(bs, EQUITY_KEYS, col)
    if ni is None or eq is None or eq == 0:
        return None
    try:
        return round((ni / eq) * 100, 2)
    except (ZeroDivisionError, ValueError):
        return None
def fetch_yfinance_fin(code):
    """Fetch financials / balance_sheet / cash_flow; let yfinance manage session."""
    try:
        t = yf.Ticker(f"{code}.T")
        fin = t.financials
        bs  = t.balance_sheet
        cf  = t.cashflow
    except Exception as e:
        msg = str(e).lower()
        if "timeout" in msg or "timed out" in msg:
            return "TIMEOUT"
        print(f"  [{code}] fetch error: {e.__class__.__name__}")
        return None
    if fin is None or fin.empty:
        return None
    records = []
    for col_date in fin.columns:
        try:
            py_date = pd.Timestamp(col_date).to_pydatetime()
            fiscal_year = f"{py_date.year}/{py_date.month}"
            rec = {
                "ticker":             code,
                "fiscal_year":        fiscal_year,
                "period_type":        "annual",
                "revenue":            safe_get(fin, REVENUE_KEYS, col_date),
                "op_profit":          safe_get(fin, OPINC_KEYS,   col_date),
                "net_income":         safe_get(fin, NETINC_KEYS,  col_date),
                "eps":                safe_get(fin, EPS_KEYS,     col_date),
                "roe":                calc_roe(fin, bs, col_date),
                "equity":             safe_get(bs, EQUITY_KEYS,   col_date),
                "shares_outstanding": safe_get(bs, SHARES_KEYS,   col_date),
                "dividend_paid":      safe_get(cf, DIV_KEYS,      col_date),
                "reported_at":        py_date.date(),
                "source":             "yfinance",
                "fetched_at":         datetime.now(timezone.utc),
            }
            records.append(rec)
        except Exception as e:
            print(f"  [{code}] record build error: {e.__class__.__name__}")
            continue
    if not records:
        return None
    return pd.DataFrame(records)
def get_existing_tickers(codes):
    if not codes:
        return set()
    codes_sql = ",".join([f"'{c}'" for c in codes])
    sql = f"""
        SELECT DISTINCT ticker FROM `{TABLE_FIN}`
        WHERE ticker IN ({codes_sql})
    """
    try:
        return {row.ticker for row in client.query(sql).result()}
    except Exception as e:
        print(f"  (existing-check query: {e.__class__.__name__})")
        return set()
def upload_chunk(dfs):
    dfs_clean = [d for d in dfs if d is not None and not d.empty]
    if not dfs_clean:
        return 0
    combined = pd.concat(dfs_clean, ignore_index=True)
    combined["reported_at"] = pd.to_datetime(combined["reported_at"]).dt.date
    job = client.load_table_from_dataframe(
        combined, TABLE_FIN,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
    )
    job.result()
    return len(combined)
def main(tickers, label=""):
    checkpoint = load_checkpoint()
    done       = set(checkpoint["done"])
    errs       = load_error_list()["errors"]
    errs_set   = set(errs)
    remaining  = [t for t in tickers if t not in done]
    print(f"=== Financial Import (staging) {label} (chunk={CHUNK_SIZE}, sleep={SLEEP_PER_TICKER}s) ===")
    print(f"  target: {len(tickers)} / done: {len(done & set(tickers))} / remaining: {len(remaining)}")
    chunk_targets = []
    chunk_dfs     = []
    consecutive_timeouts = 0
    for i, code in enumerate(tickers):
        if code in done:
            continue
        if len(chunk_targets) == 0:
            next_chunk = [c for c in tickers[i:i+CHUNK_SIZE] if c not in done]
            existing   = get_existing_tickers(next_chunk)
            if existing:
                print(f"  [existing] {len(existing)} tickers already in staging; sync checkpoint")
                for c in existing:
                    done.add(c)
                save_checkpoint(list(done))
                if code in existing:
                    continue
        print(f"  [{code}] fetching...", end=" ", flush=True)
        df = fetch_yfinance_fin(code)
        # type check first to avoid DataFrame-vs-str comparison error
        if isinstance(df, str) and df == "TIMEOUT":
            print("TIMEOUT")
            consecutive_timeouts += 1
            if code not in errs_set:
                errs.append(code)
                errs_set.add(code)
                save_error_list(errs)
            done.add(code)
            save_checkpoint(list(done))
            if consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                print(f"\n!!! {MAX_CONSECUTIVE_TIMEOUTS} consecutive TIMEOUTs -> auto stop !!!")
                if chunk_dfs:
                    rows = upload_chunk(chunk_dfs)
                    for c in chunk_targets:
                        done.add(c)
                    save_checkpoint(list(done))
                    print(f"  >>> BQ load (preserve): {len(chunk_targets)} tickers / {rows} rows")
                return
            time.sleep(SLEEP_PER_TICKER)
            continue
        consecutive_timeouts = 0
        if df is None:
            print("skip (empty)")
            if code not in errs_set:
                errs.append(code)
                errs_set.add(code)
                save_error_list(errs)
            done.add(code)
            save_checkpoint(list(done))
        elif isinstance(df, pd.DataFrame) and not df.empty:
            chunk_dfs.append(df)
            chunk_targets.append(code)
            print(f"{len(df)} periods")
        else:
            print("skip (unexpected return)")
            if code not in errs_set:
                errs.append(code)
                errs_set.add(code)
                save_error_list(errs)
            done.add(code)
            save_checkpoint(list(done))
        if len(chunk_dfs) >= CHUNK_SIZE:
            rows = upload_chunk(chunk_dfs)
            for c in chunk_targets:
                done.add(c)
            save_checkpoint(list(done))
            print(f"  >>> BQ load: {len(chunk_targets)} tickers / {rows} rows (cumulative done: {len(done)})")
            chunk_dfs     = []
            chunk_targets = []
            time.sleep(2)
        else:
            time.sleep(SLEEP_PER_TICKER)
    if chunk_dfs:
        rows = upload_chunk(chunk_dfs)
        for c in chunk_targets:
            done.add(c)
        save_checkpoint(list(done))
        print(f"  >>> BQ load (tail): {len(chunk_targets)} tickers / {rows} rows")
    print(f"\n=== Done: completed={len(done)} / errors={len(errs)} ===")
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test5",  action="store_true")
    parser.add_argument("--limit",  type=int, default=None)
    parser.add_argument("--ticker", type=str, default=None)
    args = parser.parse_args()
    if args.test5:
        main(TEST5_TICKERS, label="[TEST5]")
    elif args.ticker:
        main([args.ticker], label=f"[single:{args.ticker}]")
    else:
        tickers = get_all_tickers()
        if args.limit:
            tickers = tickers[:args.limit]
        main(tickers, label="[FULL]")
