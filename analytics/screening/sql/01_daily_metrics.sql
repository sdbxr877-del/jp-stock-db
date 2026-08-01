-- 01_daily_metrics.sql - idempotent single-day update for @target_date (v70)
--
-- Design:
--   * MERGE is avoided: WHEN NOT MATCHED INSERT blocks partition pruning
--     -> BEGIN TRANSACTION / DELETE / INSERT / COMMIT
--   * partition-filter-required: explicit date range on raw.prices, date= on daily_metrics
--   * no-select-star: every column is listed explicitly
--   * trend / return / 52w / volatility use adj_close, normalised in the base CTE
--     to drop the jquants retroactive adjustment (see the v71 note below);
--     turnover uses the actual traded price close
--   * lookback of 400 calendar days covers the widest window (378 days)
--
-- v70 change: every window is date-based (RANGE over UNIX_DATE(date)) instead of
--   row-based (ROWS n PRECEDING / LAG n). Row-based windows shift whenever rows are
--   inserted into or deleted from history, so past values were not reproducible.
--   Calendar offsets below were measured on 2026-07-31 over 4,169 tickers
--   (median calendar gap; p10 = p50 = p90 because TSE shares one calendar):
--     LAG  21 -> 30 days     LAG  63 -> 94 days     LAG 126 -> 186 days
--     ROWS 19 -> 28 days     ROWS 24 -> 35 days     ROWS  74 -> 109 days
--     ROWS 199 -> 298 days   ROWS 251 -> 378 days
--   ret_1d keeps LAG(1): "previous trading day" is row-based by definition.
--
-- v71 change: adj_close is normalised in the base CTE. raw.prices holds two
--   sources whose adj_close definitions differ. jquants rows carry a retroactive
--   split and dividend adjustment (2,331 of 202,852 rows), while yfinance rows
--   store the traded price unchanged (853,716 rows, adj_close = close with zero
--   exceptions). Reading the column as-is made the series discontinuous by up to
--   50x on the 88 affected tickers, because the source alternates day by day.
--   Measured on 2026-07-31 over 2025-08-01..2026-07-31: ret_1m > 10 falls from
--   73 rows / 6 tickers to 36 rows / 5 tickers. The remaining tickers are truly
--   unadjusted splits and are handled separately.
--
-- Note: this is a script (DECLARE / BEGIN TRANSACTION). A dry-run may report scan=0.
--       The real cost is the raw.prices date-range read for the window functions.
DECLARE target_date DATE DEFAULT @target_date;
BEGIN TRANSACTION;
DELETE FROM `{{PROJECT}}.analytics.daily_metrics`
WHERE date = target_date;
INSERT INTO `{{PROJECT}}.analytics.daily_metrics`
( ticker, date, close, adj_close, volume,
  sma25, sma75, sma200,
  ret_1m, ret_3m, ret_6m,
  high_52w, low_52w, pct_from_52w_high,
  turnover_20d, vol_20d, computed_at )
WITH base AS (
  -- Universe guard: exclude macro series (market='INDEX') and keep single stocks only.
  -- Macro series carry values on weekends and holidays. If they are mixed in, MAX(date)
  -- in 03 moves to a TSE holiday and screening_candidates becomes empty.
  -- Macro series are read directly from raw.prices on the C05 / C06 side.
  SELECT
    p.ticker, p.date, p.close,
    -- Fall back to the traded price for jquants rows so that a single, uniform
    -- price definition flows into every window below. yfinance rows already
    -- satisfy adj_close = close, so this touches only the 2,331 jquants rows.
    IF(p.source = 'jquants', p.close, p.adj_close) AS adj_close,
    p.volume
  FROM `{{PROJECT}}.raw.prices` p
  WHERE p.date BETWEEN DATE_SUB(target_date, INTERVAL 400 DAY) AND target_date
    AND NOT EXISTS (
      SELECT 1
      FROM `{{PROJECT}}.raw.tickers` t
      WHERE t.ticker = p.ticker
        AND t.market = 'INDEX'
    )
),
with_ret AS (
  SELECT
    ticker, date, close, adj_close, volume,
    UNIX_DATE(date) AS dnum,
    SAFE_DIVIDE(adj_close, LAG(adj_close) OVER (PARTITION BY ticker ORDER BY date)) - 1 AS ret_1d
  FROM base
),
calc AS (
  SELECT
    ticker, date, close, adj_close, volume,
    AVG(adj_close) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN  35 PRECEDING AND CURRENT ROW) AS sma25,
    AVG(adj_close) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN 109 PRECEDING AND CURRENT ROW) AS sma75,
    AVG(adj_close) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN 298 PRECEDING AND CURRENT ROW) AS sma200,
    SAFE_DIVIDE(adj_close, LAST_VALUE(adj_close IGNORE NULLS) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN UNBOUNDED PRECEDING AND  30 PRECEDING)) - 1 AS ret_1m,
    SAFE_DIVIDE(adj_close, LAST_VALUE(adj_close IGNORE NULLS) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN UNBOUNDED PRECEDING AND  94 PRECEDING)) - 1 AS ret_3m,
    SAFE_DIVIDE(adj_close, LAST_VALUE(adj_close IGNORE NULLS) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN UNBOUNDED PRECEDING AND 186 PRECEDING)) - 1 AS ret_6m,
    MAX(adj_close)      OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN 378 PRECEDING AND CURRENT ROW) AS high_52w,
    MIN(adj_close)      OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN 378 PRECEDING AND CURRENT ROW) AS low_52w,
    AVG(close * volume) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN  28 PRECEDING AND CURRENT ROW) AS turnover_20d,
    STDDEV_SAMP(ret_1d) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN  28 PRECEDING AND CURRENT ROW) AS vol_20d
  FROM with_ret
)
SELECT
  ticker, date, close, adj_close, volume,
  sma25, sma75, sma200,
  ret_1m, ret_3m, ret_6m,
  high_52w, low_52w,
  SAFE_DIVIDE(adj_close, NULLIF(high_52w, 0)) - 1 AS pct_from_52w_high,
  turnover_20d, vol_20d,
  CURRENT_TIMESTAMP() AS computed_at
FROM calc
WHERE date = target_date;
COMMIT TRANSACTION;
