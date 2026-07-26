# -*- coding: utf-8 -*-
"""financial_summary_import.py
Fetch J-Quants V2 /fins/summary by disclosure date and load into raw.fins_summary_staging.
Auth: reads the API credential from an env var and sends it as the x-api-key header.
Staging only; MERGE into raw.fins_summary is a separate step.

Usage:
  python financial_summary_import.py --date 20250508 --limit 5 --dry   # inspect mapping, no load
  python financial_summary_import.py --date 20250508                    # load one day to staging
  python financial_summary_import.py --from 20230401 --to 20250501      # backfill range (resumable)
  python financial_summary_import.py --from 20230401 --to 20250501 --reset  # ignore checkpoint
"""
import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
import requests
from google.cloud import bigquery

PROJECT = "project-3eaadce9-f852-40e1-932"
DATASET = "raw"
TABLE_STAGING = f"{PROJECT}.{DATASET}.fins_summary_staging"
API_URL = "https://api.jquants.com/v2/fins/summary"
THROTTLE_SEC = 12
RETRY_429_WAIT = 60
CHECKPOINT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".fins_summary_checkpoint.json")
FLUSH_ROWS = 2000

# API field -> (staging column, kind); kind in {num, flt, int, date, str}
FIELD_MAP = [
    ("DiscNo", "disc_no", "str"),
    ("DiscDate", "disc_date", "date"),
    ("DiscTime", "disc_time", "str"),
    ("DocType", "doc_type", "str"),
    ("CurPerType", "cur_per_type", "str"),
    ("CurPerSt", "cur_per_start", "date"),
    ("CurPerEn", "cur_per_end", "date"),
    ("CurFYSt", "cur_fy_start", "date"),
    ("CurFYEn", "cur_fy_end", "date"),
    ("NxtFYSt", "nxt_fy_start", "date"),
    ("NxtFYEn", "nxt_fy_end", "date"),
    ("Sales", "sales", "num"),
    ("OP", "op", "num"),
    ("OdP", "odp", "num"),
    ("NP", "np", "num"),
    ("EPS", "eps", "flt"),
    ("DEPS", "deps", "flt"),
    ("TA", "total_assets", "num"),
    ("Eq", "equity", "num"),
    ("EqAR", "equity_ratio", "flt"),
    ("BPS", "bps", "flt"),
    ("CFO", "cfo", "num"),
    ("CFI", "cfi", "num"),
    ("CFF", "cff", "num"),
    ("CashEq", "cash_eq", "num"),
    ("DivAnn", "div_ann", "flt"),
    ("DivTotalAnn", "div_total_ann", "num"),
    ("PayoutRatioAnn", "payout_ratio_ann", "flt"),
    ("FSales", "f_sales", "num"),
    ("FOP", "f_op", "num"),
    ("FOdP", "f_odp", "num"),
    ("FNP", "f_np", "num"),
    ("FEPS", "f_eps", "flt"),
    ("FDivAnn", "f_div_ann", "flt"),
    ("NxFSales", "nxf_sales", "num"),
    ("NxFOP", "nxf_op", "num"),
    ("NxFOdP", "nxf_odp", "num"),
    ("NxFNp", "nxf_np", "num"),
    ("NxFEPS", "nxf_eps", "flt"),
    ("NxFDivAnn", "nxf_div_ann", "flt"),
    ("ShOutFY", "shares_out_fy", "int"),
    ("TrShFY", "treasury_shares_fy", "int"),
    ("AvgSh", "avg_shares", "int"),
]

def _clean(v):
    return v.strip() if isinstance(v, str) else v

def cast(value, kind):
    v = _clean(value)
    if v in ("", None):
        return None
    try:
        if kind == "num":
            return str(v)
        if kind == "flt":
            return float(v)
        if kind == "int":
            return int(float(v))
        return v
    except (ValueError, TypeError):
        return None

def map_record(rec, fetched_iso):
    code5 = _clean(rec.get("Code"))
    if not code5:
        return None
    out = {"code5": code5, "ticker": code5[:4], "source": "jquants", "fetched_at": fetched_iso}
    for api_key, col, kind in FIELD_MAP:
        out[col] = cast(rec.get(api_key), kind)
    if not out.get("disc_no"):
        return None
    return out

def fetch_one_day(date_str, api_key):
    headers = {"x-api-key": api_key}
    rows = []
    next_page = None
    while True:
        params = {"date": date_str}
        if next_page:
            params["pagination_key"] = next_page
        r = requests.get(API_URL, headers=headers, params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(RETRY_429_WAIT)
            r = requests.get(API_URL, headers=headers, params=params, timeout=30)
        if r.status_code != 200:
            return None, r.status_code, r.text[:300]
        body = r.json()
        rows.extend(body.get("data", []))
        next_page = body.get("pagination_key")
        if not next_page:
            break
        time.sleep(THROTTLE_SEC)
    return rows, 200, ""

def load_rows(client, rows):
    if not rows:
        return 0
    table = client.get_table(TABLE_STAGING)
    cfg = bigquery.LoadJobConfig(
        schema=table.schema,
        write_disposition="WRITE_APPEND",
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    job = client.load_table_from_json(rows, TABLE_STAGING, job_config=cfg)
    job.result()
    return len(rows)

def daterange(d0, d1):
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)

def read_checkpoint():
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def write_checkpoint(obj):
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f)

def parse_date(s):
    return datetime.strptime(s, "%Y%m%d").date()

def main():
    ap = argparse.ArgumentParser(description="J-Quants V2 /fins/summary by-date staging loader")
    ap.add_argument("--date", type=str, default=None, help="single day YYYYMMDD")
    ap.add_argument("--from", dest="from_", type=str, default=None, help="range start YYYYMMDD")
    ap.add_argument("--to", dest="to", type=str, default=None, help="range end YYYYMMDD")
    ap.add_argument("--limit", type=int, default=None, help="cap mapped rows (inspection)")
    ap.add_argument("--dry", action="store_true", help="fetch + map + print, no load")
    ap.add_argument("--reset", action="store_true", help="ignore existing checkpoint")
    args = ap.parse_args()

    env_label = "JQUANTS_API_KEY"
    api_key = os.environ.get(env_label)
    if not api_key:
        print("ERROR: required auth env var is not set")
        sys.exit(1)

    if args.date:
        days = [parse_date(args.date)]
    elif args.from_ and args.to:
        d0, d1 = parse_date(args.from_), parse_date(args.to)
        ckpt = {} if args.reset else read_checkpoint()
        if ckpt.get("last_date"):
            resume = parse_date(ckpt["last_date"]) + timedelta(days=1)
            if resume > d0:
                d0 = resume
                print(f"resume from checkpoint: {d0}")
        days = list(daterange(d0, d1))
    else:
        print("ERROR: specify --date or (--from and --to)")
        sys.exit(2)

    client = None if args.dry else bigquery.Client(project=PROJECT)
    fetched_iso = datetime.now(timezone.utc).isoformat()
    total_fetched = 0
    total_loaded = 0
    errors = []
    buffer = []
    last_ok = None

    for i, d in enumerate(days):
        ds = d.strftime("%Y%m%d")
        raw_rows, status, body = fetch_one_day(ds, api_key)
        if raw_rows is None:
            errors.append((ds, status, body))
            print(f"{ds} -> HTTP {status} SKIP: {body}")
        else:
            mapped = [m for m in (map_record(r, fetched_iso) for r in raw_rows) if m]
            total_fetched += len(mapped)
            buffer.extend(mapped)
            last_ok = ds
            print(f"{ds} -> raw={len(raw_rows)} mapped={len(mapped)} buffer={len(buffer)}")
        if args.limit and total_fetched >= args.limit:
            buffer = buffer[: args.limit]
            print("limit reached, stopping")
            break
        if not args.dry and len(buffer) >= FLUSH_ROWS:
            total_loaded += load_rows(client, buffer)
            buffer = []
            if args.from_ and last_ok:
                write_checkpoint({"last_date": last_ok, "from": args.from_, "to": args.to})
        if i + 1 < len(days):
            time.sleep(THROTTLE_SEC)

    if args.dry:
        print("=" * 60)
        print(f"DRY: mapped={total_fetched}, no load")
        for m in buffer[:5]:
            print(json.dumps(m, ensure_ascii=False))
        return

    if buffer:
        total_loaded += load_rows(client, buffer)
        if args.from_ and last_ok:
            write_checkpoint({"last_date": last_ok, "from": args.from_, "to": args.to})
    staged = client.get_table(TABLE_STAGING).num_rows
    print("=" * 60)
    print(f"loaded={total_loaded} staging_total={staged} errors={len(errors)}")
    if errors:
        print(f"error days: {[e[0] for e in errors]}")

if __name__ == "__main__":
    main()
