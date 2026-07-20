import os
import sys

import pandas as pd
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv(dotenv_path=r"C:\jp-stock-db\.env")

PROJECT = "project-3eaadce9-f852-40e1-932"
TABLE_TICKERS = f"{PROJECT}.raw.tickers"
MAX_SCAN_GB = 1.5
ORDINARY_SUFFIX = "0"
PRESERVED_MARKET = "INDEX"
SHOW_LIMIT = 40

client = bigquery.Client(project=PROJECT)


def fetch_master():
    cred = os.environ["JQUANTS_API_KEY"]
    r = requests.get(
        "https://api.jquants.com/v2/equities/master",
        headers={"x-api-key": cred},
    )
    if r.status_code != 200:
        raise RuntimeError(f"J-Quants error {r.status_code}: {r.text}")
    return r.json().get("data", [])


def build_ordinary_rows(records):
    rows = []
    skipped = []
    now = datetime.now(timezone.utc)
    for r in records:
        code = str(r.get("Code", "")).strip()
        if len(code) != 5:
            skipped.append((code, "bad_length"))
            continue
        if code[-1] != ORDINARY_SUFFIX:
            skipped.append((code, "non_ordinary"))
            continue
        rows.append(
            {
                "ticker": code[:4],
                "name": r.get("CoName", ""),
                "market": r.get("MktNm", ""),
                "sector_code": str(r.get("S33", "")),
                "sector_name": r.get("S33Nm", ""),
                "fiscal_month": None,
                "is_active": True,
                "updated_at": now,
            }
        )
    return rows, skipped


def guard_unique(df, label):
    n = len(df)
    pop = df["ticker"].nunique()
    print(f"  {label}: n={n} pop={pop}")
    if n != pop:
        dups = df[df["ticker"].duplicated(keep=False)].sort_values("ticker")
        print("  duplicated tickers:")
        for t in sorted(dups["ticker"].unique()):
            print(f"    {t}")
        raise SystemExit(f"ABORT: duplicate ticker detected in {label}")


def fetch_current_rows(table):
    cols = [f.name for f in table.schema]
    sql = f"SELECT {', '.join(cols)} FROM `{TABLE_TICKERS}`"

    dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry = client.query(sql, job_config=dry_cfg)
    scan_gb = dry.total_bytes_processed / (1024**3)
    print(f"  current query dry run: {scan_gb:.6f} GB")
    if scan_gb > MAX_SCAN_GB:
        raise SystemExit(f"ABORT: scan {scan_gb:.6f} GB exceeds {MAX_SCAN_GB} GB")

    df = client.query(sql).result().to_dataframe()
    print(f"  current rows fetched: {len(df)}")
    if len(df) == 0:
        raise SystemExit("ABORT: current raw.tickers is empty. Refusing to proceed.")
    return df


def guard_code_reuse(df_current_noindex, new_tickers):
    inactive = df_current_noindex[df_current_noindex["is_active"] != True]
    reused = sorted(set(inactive["ticker"]) & new_tickers)
    print(f"  currently inactive tickers: {len(inactive)}")
    print(f"  reused delisted codes: {len(reused)}")
    if reused:
        lookup = {r.ticker: r.name for r in inactive.itertuples()}
        for t in reused:
            print(f"    {t} old_name={lookup.get(t)}")
        raise SystemExit(
            "ABORT: a delisted 4 digit code reappeared in the master. "
            "Price history in raw.prices may mix two different companies. "
            "Resolve manually before loading."
        )


def normalize_dtypes(df, table):
    for f in table.schema:
        if f.name not in df.columns:
            raise SystemExit(f"ABORT: column {f.name} missing from payload")
        if f.field_type == "INTEGER":
            df[f.name] = pd.to_numeric(df[f.name], errors="coerce").astype("Int64")
        elif f.field_type == "BOOLEAN":
            df[f.name] = df[f.name].astype("boolean")
        elif f.field_type == "TIMESTAMP":
            df[f.name] = pd.to_datetime(df[f.name], utc=True)
        elif f.field_type == "STRING":
            df[f.name] = df[f.name].astype("object")
    return df[[f.name for f in table.schema]]


def main():
    apply_mode = "--apply" in sys.argv
    print("=== fetch_tickers.py ===")
    print(f"mode: {'APPLY' if apply_mode else 'DRY RUN, no write'}")

    records = fetch_master()
    print(f"master records: {len(records)}")

    rows, skipped = build_ordinary_rows(records)
    print(f"ordinary rows: {len(rows)}")
    print(f"skipped rows: {len(skipped)}")
    for code, reason in skipped:
        print(f"  skip code={code} reason={reason}")

    df_new = pd.DataFrame(rows)
    guard_unique(df_new, "ordinary")
    new_tickers = set(df_new["ticker"])

    table = client.get_table(TABLE_TICKERS)
    print(f"target schema columns: {[f.name for f in table.schema]}")
    print(f"target current rows: {table.num_rows}")

    df_cur = fetch_current_rows(table)
    df_index = df_cur[df_cur["market"] == PRESERVED_MARKET].copy()
    df_noidx = df_cur[df_cur["market"] != PRESERVED_MARKET].copy()
    print(f"  current INDEX rows: {len(df_index)}")
    print(f"  current non INDEX rows: {len(df_noidx)}")
    if len(df_index) == 0:
        raise SystemExit(
            f"ABORT: no rows with market={PRESERVED_MARKET}. "
            "Refusing to truncate and lose macro series."
        )

    guard_code_reuse(df_noidx, new_tickers)

    df_retire = df_noidx[~df_noidx["ticker"].isin(new_tickers)].copy()
    df_retire["is_active"] = False
    df_retire["updated_at"] = datetime.now(timezone.utc)
    print(f"  retired to is_active FALSE: {len(df_retire)}")
    for t in sorted(df_retire["ticker"])[:SHOW_LIMIT]:
        print(f"    {t}")
    if len(df_retire) > SHOW_LIMIT:
        print(f"    ... {len(df_retire) - SHOW_LIMIT} more")

    df_all = pd.concat([df_new, df_index, df_retire], ignore_index=True)
    guard_unique(df_all, "combined")
    df_all = normalize_dtypes(df_all, table)

    print("market breakdown of payload:")
    print(df_all["market"].value_counts().to_string())
    print("is_active breakdown of payload:")
    print(df_all["is_active"].value_counts().to_string())
    print(f"payload total: {len(df_all)}")

    if not apply_mode:
        print("DRY RUN complete. Re-run with --apply to write.")
        print("=== done ===")
        return

    print("loading into raw.tickers with WRITE_TRUNCATE ...")
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=table.schema,
    )
    job = client.load_table_from_dataframe(df_all, TABLE_TICKERS, job_config=job_config)
    job.result()
    print(f"loaded: {len(df_all)}")

    verify_sql = (
        f"SELECT market, is_active, COUNT(1) AS cnt FROM `{TABLE_TICKERS}` "
        "GROUP BY market, is_active ORDER BY cnt DESC"
    )
    dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry = client.query(verify_sql, job_config=dry_cfg)
    scan_gb = dry.total_bytes_processed / (1024**3)
    print(f"verify query dry run: {scan_gb:.6f} GB")
    if scan_gb > MAX_SCAN_GB:
        raise SystemExit(f"ABORT: scan {scan_gb:.6f} GB exceeds {MAX_SCAN_GB} GB")

    print("--- verify ---")
    for row in client.query(verify_sql).result():
        print(f"  {row.market} active={row.is_active}: {row.cnt}")
    print("=== done ===")


if __name__ == "__main__":
    main()
