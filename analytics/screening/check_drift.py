"""Gate: fail when analytics.source_scale_drift reports drift_col='both'.

A 'both' row means close and adj_close are both stale for a ticker-month,
so 01_daily_metrics cannot recover the correct scale by picking a column.
The raw rows must be repaired before the metrics are recomputed.
"""
from __future__ import annotations

import pathlib
import sys

import yaml
from google.cloud import bigquery

BASE_DIR = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "screening_config.yaml"

QUERY = """
SELECT ticker, ym, n_boundary, med_close, med_adj
FROM `{project}.analytics.source_scale_drift`
WHERE drift_col = 'both'
ORDER BY ticker, ym
"""


def load_config(path: pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    cfg = load_config(CONFIG_PATH)
    project = cfg["project"]
    client = bigquery.Client(project=project, location=cfg.get("location"))
    rows = list(client.query(QUERY.format(project=project)).result())
    print("drift_both_rows={}".format(len(rows)))
    for r in rows:
        print(
            "ticker={} ym={} n_boundary={} med_close={} med_adj={}".format(
                r["ticker"], r["ym"], r["n_boundary"], r["med_close"], r["med_adj"]
            )
        )
    if rows:
        print("G3 FAIL: stale scale detected in both close and adj_close")
        return 1
    print("G3 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
