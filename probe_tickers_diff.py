from collections import Counter

import pandas as pd
from google.cloud import bigquery

from fetch_tickers import (
    MAX_SCAN_GB,
    TABLE_TICKERS,
    build_ordinary_rows,
    client,
    fetch_master,
)

SHOW_LIMIT = 40


def load_current():
    sql = f"SELECT ticker, name, market FROM `{TABLE_TICKERS}`"
    dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry = client.query(sql, job_config=dry_cfg)
    scan_gb = dry.total_bytes_processed / (1024**3)
    print(f"current query dry run: {scan_gb:.6f} GB")
    if scan_gb > MAX_SCAN_GB:
        raise SystemExit(f"ABORT: scan {scan_gb:.6f} GB exceeds {MAX_SCAN_GB} GB")
    return client.query(sql).result().to_dataframe()


def main():
    print("=== probe_tickers_diff.py / read only, no write ===")

    records = fetch_master()
    rows, _ = build_ordinary_rows(records)
    df_new = pd.DataFrame(rows)[["ticker", "name", "market"]]
    print(f"payload ordinary rows: {len(df_new)}")

    df_cur_all = load_current()
    print(f"current rows total: {len(df_cur_all)}")
    df_cur = df_cur_all[df_cur_all["market"] != "INDEX"].copy()
    print(f"current rows excluding INDEX: {len(df_cur)}")

    cur = {r.ticker: (r.name, r.market) for r in df_cur.itertuples()}
    new = {r.ticker: (r.name, r.market) for r in df_new.itertuples()}

    added = sorted(set(new) - set(cur))
    removed = sorted(set(cur) - set(new))
    common = sorted(set(cur) & set(new))

    print(f"\nadded: {len(added)}")
    print(f"removed: {len(removed)}")
    print(f"common: {len(common)}")

    print("\n--- added detail ---")
    for t in added[:SHOW_LIMIT]:
        print(f"  {t} market={new[t][1]} name={new[t][0]}")
    if len(added) > SHOW_LIMIT:
        print(f"  ... {len(added) - SHOW_LIMIT} more")

    print("\n--- removed detail ---")
    for t in removed[:SHOW_LIMIT]:
        print(f"  {t} market={cur[t][1]} name={cur[t][0]}")
    if len(removed) > SHOW_LIMIT:
        print(f"  ... {len(removed) - SHOW_LIMIT} more")

    changed = [t for t in common if cur[t][1] != new[t][1]]
    print(f"\nmarket changed: {len(changed)}")

    print("\n--- transition counts, old to new ---")
    trans = Counter((cur[t][1], new[t][1]) for t in changed)
    for (old, nw), c in sorted(trans.items(), key=lambda x: -x[1]):
        print(f"  {old} -> {nw}: {c}")

    print("\n--- market changed detail ---")
    for t in changed[:SHOW_LIMIT]:
        print(f"  {t} {cur[t][1]} -> {new[t][1]} name={new[t][0]}")
    if len(changed) > SHOW_LIMIT:
        print(f"  ... {len(changed) - SHOW_LIMIT} more")

    renamed = [t for t in common if cur[t][0] != new[t][0]]
    print(f"\nname changed: {len(renamed)}")
    for t in renamed[:SHOW_LIMIT]:
        print(f"  {t} old={cur[t][0]} new={new[t][0]}")
    if len(renamed) > SHOW_LIMIT:
        print(f"  ... {len(renamed) - SHOW_LIMIT} more")

    print("\n=== done ===")


if __name__ == "__main__":
    main()
