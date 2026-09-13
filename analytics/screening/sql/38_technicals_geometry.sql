-- 38_technicals_geometry.sql
-- C17 third wave, part A. Price-bin volume aggregation (Point of Control /
-- High Volume Node), a Volume-Profile-style view. Out of scope of
-- 37_technicals_wilder.sql on purpose: bin aggregation is a different
-- implementation shape from the recursive indicators there (see that file's
-- header). ZigZag+divergence (state machine) is out of scope of this file
-- too and is implemented separately in scripts/zigzag_ingest.py, because a
-- state machine cannot be expressed as a single declarative SQL view.
--
-- Parameters (edit here to change behaviour). This is a VIEW: a redeploy
-- (CREATE OR REPLACE VIEW) recomputes the ENTIRE history from raw.prices
-- under the new value on the very next query. There is no stored
-- old-parameter output sitting anywhere, so changing a parameter can never
-- leave old- and new-parameter rows mixed together.
--   LOOKBACK_DAYS = 60   rolling window, trading days. Hardcoded in the
--                        ROWS BETWEEN clause below -- BigQuery window frame
--                        bounds must be literals, so this cannot be pulled
--                        out into a CTE variable.
--   BIN_COUNT     = 24   number of equal-width price bins. Hardcoded in
--                        GENERATE_ARRAY(0, 23) below, same reason as above.
--   HVN_THRESHOLD = 0.70 a bin counts as HVN if its volume >= this fraction
--                        of the PoC bin's volume. Hardcoded in two places
--                        below (both literal 0.70).
--
-- Definition. For each ticker/date, take the trailing LOOKBACK_DAYS window,
-- split its [min(low), max(high)] range into BIN_COUNT equal-width price
-- bins, and allocate each day's volume across bins in proportion to how much
-- of that day's [low, high] range overlaps each bin (a day with high = low
-- allocates its full volume to the single bin containing that price). PoC
-- (Point of Control) is the bin with the most allocated volume. HVN (High
-- Volume Node) bins are those at or above HVN_THRESHOLD of the PoC bin's
-- volume. This is a simplified, custom, per-bin-threshold definition, not
-- the "cumulative value area" definition used by some charting platforms --
-- no such industry-standard threshold is assumed or claimed here.
--
-- Population. Source fixed to yfinance, lower date bound 2022-05-24,
-- matching 34_technicals.sql / 37_technicals_wilder.sql so the population
-- stays identical across all three files.
--
-- Warm up. Rows with fewer than LOOKBACK_DAYS preceding rows still emit a
-- value over the shorter window actually available; warmup_ok reports
-- whether the full 60-day window was available for that row.
--
-- Degenerate range. If every high/low in the window is identical (flat
-- range), all bins collapse to the same price and range_degenerate is set;
-- poc/hvn values are still emitted but are not meaningful in that case.

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.technicals_geometry` AS
WITH px AS (
  SELECT
    ticker,
    date,
    high,
    low,
    close,
    volume
  FROM `{{PROJECT}}.raw.prices`
  WHERE date >= DATE '2022-05-24'
    AND source = 'yfinance'
),
win AS (
  SELECT
    ticker,
    date,
    close,
    COUNT(*) OVER w60 AS window_rows,
    ARRAY_AGG(STRUCT(high AS h, low AS l, volume AS v)) OVER w60 AS w
  FROM px
  WINDOW w60 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
),
ranged AS (
  SELECT
    ticker,
    date,
    close,
    window_rows,
    w,
    (SELECT MIN(l) FROM UNNEST(w)) AS range_low,
    (SELECT MAX(h) FROM UNNEST(w)) AS range_high
  FROM win
),
bins AS (
  SELECT
    ticker,
    date,
    close,
    window_rows,
    range_high - range_low AS range_span,
    ARRAY(
      SELECT AS STRUCT
        b AS bin_idx,
        range_low + (range_high - range_low) * b / 24.0 AS bin_lo,
        range_low + (range_high - range_low) * (b + 1) / 24.0 AS bin_hi,
        (
          SELECT SUM(
            IF(e.h = e.l,
              IF(e.l >= range_low + (range_high - range_low) * b / 24.0
                 AND (e.l < range_low + (range_high - range_low) * (b + 1) / 24.0 OR b = 23),
                e.v, 0),
              e.v * SAFE_DIVIDE(
                GREATEST(0.0, LEAST(e.h, range_low + (range_high - range_low) * (b + 1) / 24.0)
                             - GREATEST(e.l, range_low + (range_high - range_low) * b / 24.0)),
                e.h - e.l)
            ))
          FROM UNNEST(w) AS e
        ) AS bin_volume
      FROM UNNEST(GENERATE_ARRAY(0, 23)) AS b
    ) AS bin_arr
  FROM ranged
),
poc AS (
  SELECT
    ticker,
    date,
    close,
    window_rows,
    range_span,
    bin_arr,
    (SELECT AS STRUCT bin_lo, bin_hi, bin_volume
     FROM UNNEST(bin_arr)
     ORDER BY bin_volume DESC
     LIMIT 1) AS poc_bin
  FROM bins
)
SELECT
  ticker,
  date,
  ROUND(poc_bin.bin_lo, 2) AS poc_price_lo,
  ROUND(poc_bin.bin_hi, 2) AS poc_price_hi,
  ROUND((poc_bin.bin_lo + poc_bin.bin_hi) / 2, 2) AS poc_price,
  close >= poc_bin.bin_lo AND close < poc_bin.bin_hi AS close_in_poc_bin,
  (SELECT COUNT(*) FROM UNNEST(bin_arr) WHERE bin_volume >= 0.70 * poc_bin.bin_volume) AS hvn_bin_count,
  EXISTS(
    SELECT 1 FROM UNNEST(bin_arr)
    WHERE bin_volume >= 0.70 * poc_bin.bin_volume
      AND close >= bin_lo AND close < bin_hi
  ) AS close_in_hvn,
  window_rows,
  window_rows >= 60 AS warmup_ok,
  range_span IS NULL OR range_span = 0 AS range_degenerate
FROM poc
