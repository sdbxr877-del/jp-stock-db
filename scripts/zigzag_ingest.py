#!/usr/bin/env python3
"""ZigZag + RSI divergence ingest (C17 third wave, part B).

Why a Python script and not a SQL view (contrast with 37/38): ZigZag is a
state machine -- each day's pivot state depends on the entire preceding
path, not a fixed lookback window -- so it does not fit BigQuery's
declarative window-function model the way 37/38 do. This script computes it
in Python and loads the result into a BigQuery table.

Full-refresh discipline (the mixed-parameter-rows problem). Because this
writes into a stored table rather than a view, changing ATR_MULTIPLIER and
re-running must never leave old-parameter rows next to new-parameter rows.
This script always recomputes the FULL history (2022-05-24 onward, matching
34/37/38) and loads with WRITE_TRUNCATE, replacing the entire table every
run. It never appends. Each row also carries atr_multiplier_used so any row
can be traced to the setting that produced it, even from a saved export.

Parameters (edit here to change behaviour; effective on the next run):
  ATR_MULTIPLIER = 2.0   reversal threshold = atr14_wilder * ATR_MULTIPLIER
                         on the day of the potential reversal. Using ATR
                         rather than a fixed percentage means the threshold
                         auto-scales to each ticker's own volatility.

Divergence definition: comparing a pivot high/low to the PRECEDING pivot of
the same type (skipping over the intermediate opposite-type pivot), using
rsi14_wilder (from analytics.technicals_wilder) sampled on the pivot date.
  bearish: price makes a higher high, RSI makes a lower high (or equal)
  bullish: price makes a lower low, RSI makes a higher low (or equal)
No industry-standard RSI divergence threshold is assumed beyond this
higher/lower comparison; this is intentionally the simplest form.

Usage:
  python scripts/zigzag_ingest.py --dry-run              # BQ dry run + pivot
                                                           # counts, no write
  python scripts/zigzag_ingest.py --dry-run --limit-tickers 25
  python scripts/zigzag_ingest.py                         # full run, WRITE_TRUNCATE
"""

import argparse
import datetime as dt

PROJECT = "project-3eaadce9-f852-40e1-932"
DATASET = "analytics"
TABLE = "zigzag_divergence"
MAX_SCAN_GB = 1.5

ATR_MULTIPLIER = 2.0


def fetch_source_sql(limit_tickers=None):
    ticker_filter = ""
    if limit_tickers:
        ticker_filter = f"""
    AND p.ticker IN (
      SELECT DISTINCT ticker FROM `{PROJECT}.raw.prices`
      WHERE date >= DATE '2022-05-24' AND source = 'yfinance'
      ORDER BY ticker LIMIT {int(limit_tickers)}
    )"""
    return f"""
SELECT
  p.ticker AS ticker,
  p.date AS date,
  p.close AS close,
  w.atr14_wilder AS atr,
  w.rsi14_wilder AS rsi
FROM `{PROJECT}.raw.prices` AS p
JOIN `{PROJECT}.analytics.technicals_wilder` AS w
  ON w.ticker = p.ticker AND w.date = p.date
WHERE p.date >= DATE '2022-05-24'
  AND p.source = 'yfinance'{ticker_filter}
ORDER BY p.ticker, p.date
"""


def compute_pivots(rows):
    """rows: list of dicts sorted by (ticker, date) for ONE ticker.

    Returns list of pivot dicts: date, price_type(high/low), price, rsi.
    """
    pivots = []
    direction = None
    ext_price = None
    ext_date = None
    ext_rsi = None

    for r in rows:
        close, atr, rsi, date = r["close"], r["atr"], r["rsi"], r["date"]
        if close is None or atr is None:
            continue
        if ext_price is None:
            ext_price, ext_date, ext_rsi = close, date, rsi
            continue

        threshold = atr * ATR_MULTIPLIER

        if direction is None:
            if close - ext_price >= threshold:
                pivots.append({"date": ext_date, "type": "low", "price": ext_price, "rsi": ext_rsi})
                direction = "up"
                ext_price, ext_date, ext_rsi = close, date, rsi
            elif ext_price - close >= threshold:
                pivots.append({"date": ext_date, "type": "high", "price": ext_price, "rsi": ext_rsi})
                direction = "down"
                ext_price, ext_date, ext_rsi = close, date, rsi
            else:
                if close > ext_price:
                    ext_price, ext_date, ext_rsi = close, date, rsi
                elif close < ext_price:
                    pass
            continue

        if direction == "up":
            if close >= ext_price:
                ext_price, ext_date, ext_rsi = close, date, rsi
            elif ext_price - close >= threshold:
                pivots.append({"date": ext_date, "type": "high", "price": ext_price, "rsi": ext_rsi})
                direction = "down"
                ext_price, ext_date, ext_rsi = close, date, rsi
        else:
            if close <= ext_price:
                ext_price, ext_date, ext_rsi = close, date, rsi
            elif close - ext_price >= threshold:
                pivots.append({"date": ext_date, "type": "low", "price": ext_price, "rsi": ext_rsi})
                direction = "up"
                ext_price, ext_date, ext_rsi = close, date, rsi

    return pivots


def compute_divergence(ticker, pivots, ingested_at):
    """Compare each pivot to the PRECEDING pivot of the same type."""
    records = []
    last_of_type = {"high": None, "low": None}
    for piv in pivots:
        prior = last_of_type[piv["type"]]
        divergence = "none"
        if prior is not None and piv["rsi"] is not None and prior["rsi"] is not None:
            if piv["type"] == "high":
                if piv["price"] > prior["price"] and piv["rsi"] <= prior["rsi"]:
                    divergence = "bearish"
            else:
                if piv["price"] < prior["price"] and piv["rsi"] >= prior["rsi"]:
                    divergence = "bullish"
        records.append({
            "ticker": ticker,
            "pivot_date": piv["date"].isoformat(),
            "pivot_type": piv["type"],
            "pivot_price": piv["price"],
            "rsi_at_pivot": piv["rsi"],
            "prior_pivot_date": prior["date"].isoformat() if prior else None,
            "prior_pivot_price": prior["price"] if prior else None,
            "prior_rsi": prior["rsi"] if prior else None,
            "divergence_type": divergence,
            "atr_multiplier_used": ATR_MULTIPLIER,
            "computed_at": ingested_at,
        })
        last_of_type[piv["type"]] = piv
    return records


def load_rows(client, records):
    from google.cloud import bigquery

    table_id = f"{PROJECT}.{DATASET}.{TABLE}"
    schema = [
        bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("pivot_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("pivot_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("pivot_price", "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("rsi_at_pivot", "FLOAT64"),
        bigquery.SchemaField("prior_pivot_date", "DATE"),
        bigquery.SchemaField("prior_pivot_price", "FLOAT64"),
        bigquery.SchemaField("prior_rsi", "FLOAT64"),
        bigquery.SchemaField("divergence_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("atr_multiplier_used", "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("computed_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        clustering_fields=["ticker"],
    )
    job = client.load_table_from_json(records, table_id, job_config=job_config)
    job.result()
    return client.get_table(table_id).num_rows


def main():
    parser = argparse.ArgumentParser(description="ZigZag + RSI divergence ingest")
    parser.add_argument("--dry-run", action="store_true",
                        help="BQ dry run + pivot counts only; no BigQuery write")
    parser.add_argument("--limit-tickers", type=int, default=None,
                        help="restrict to N tickers (testing only; omit for full run)")
    args = parser.parse_args()

    from google.cloud import bigquery
    client = bigquery.Client(project=PROJECT)
    sql = fetch_source_sql(args.limit_tickers)

    cfg_dry = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    job = client.query(sql, job_config=cfg_dry)
    gb = (job.total_bytes_processed or 0) / (1024 ** 3)
    print(f"[DRY RUN] source scan: {gb:.6f} GB (MAX_SCAN_GB={MAX_SCAN_GB})")
    if gb > MAX_SCAN_GB:
        raise SystemExit(f"DRY RUN over MAX_SCAN_GB: {gb:.6f} > {MAX_SCAN_GB}")

    print("[FETCH] running source query ...")
    source_rows = list(client.query(sql).result())
    print(f"[FETCH] {len(source_rows)} rows")

    by_ticker = {}
    for r in source_rows:
        by_ticker.setdefault(r["ticker"], []).append(dict(r))

    ingested_at = dt.datetime.now(dt.timezone.utc).isoformat()
    all_records = []
    n_bearish = 0
    n_bullish = 0
    for ticker, rows in by_ticker.items():
        pivots = compute_pivots(rows)
        recs = compute_divergence(ticker, pivots, ingested_at)
        all_records.extend(recs)
        n_bearish += sum(1 for x in recs if x["divergence_type"] == "bearish")
        n_bullish += sum(1 for x in recs if x["divergence_type"] == "bullish")

    print(f"[COMPUTE] tickers={len(by_ticker)} pivots={len(all_records)} "
          f"bearish_div={n_bearish} bullish_div={n_bullish} "
          f"atr_multiplier={ATR_MULTIPLIER}")

    if args.dry_run:
        print("[DRY RUN] skipping BigQuery write")
        return

    print(f"[LOAD] WRITE_TRUNCATE into {PROJECT}.{DATASET}.{TABLE} ...")
    n = load_rows(client, all_records)
    print(f"[LOAD] done: {n} rows now in table")


if __name__ == "__main__":
    main()
