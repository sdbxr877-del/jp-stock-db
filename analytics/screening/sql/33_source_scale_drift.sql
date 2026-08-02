-- 33_source_scale_drift.sql - detect stale price scale across mixed sources
--
-- Why this exists (v74):
--   raw.prices mixes yfinance and jquants rows. Rows captured before a corporate
--   action keep the scale that was in effect at fetch time and are never
--   re-adjusted, so a split silently leaves the older rows on a stale scale.
--   3612 (2:1) and 8273 (3:1) were repaired in v74; the same failure recurs on
--   every future split while jquants rows are being appended.
--
-- Method:
--   Look only at rows where the source changes between adjacent trading days.
--   Orient every ratio as jquants / yfinance so a healthy column sits near 1.0
--   no matter which side comes first. Take the median per ticker per month: a
--   stale scale holds a constant offset for a whole month, while ordinary price
--   moves average out. Counting deviations instead of averaging them is what
--   made v73 fail on minority corruption, so the month bucket is the unit here.
--
-- Reading the output:
--   drift_col = 'both'  -> close and adj_close are both stale. 01's per-ticker
--                          pick cannot repair this. Requires a raw fix.
--   drift_col = 'close' -> close is stale. 01 picks adj_close automatically.
--   drift_col = 'adj'   -> adj_close is stale. 01 picks close automatically.
--
-- Daily check:
--   SELECT COUNT(*) FROM analytics.source_scale_drift WHERE drift_col = 'both'
--   Anything above zero needs a human decision before the next backfill.
--
-- Notes:
--   * 400-day window matches 01_daily_metrics.sql so both agree on which rows exist.
--   * Emits only flagged rows, so an empty result means no drift was found.
--   * No ticker is hard-coded.

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.source_scale_drift` AS
WITH bd AS (
  SELECT
    p.ticker,
    p.date,
    p.source,
    p.close,
    p.adj_close,
    LAG(p.source)    OVER (PARTITION BY p.ticker ORDER BY p.date) AS ps,
    LAG(p.close)     OVER (PARTITION BY p.ticker ORDER BY p.date) AS pc,
    LAG(p.adj_close) OVER (PARTITION BY p.ticker ORDER BY p.date) AS pa
  FROM `{{PROJECT}}.raw.prices` p
  WHERE p.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 400 DAY)
),
ratios AS (
  SELECT
    ticker,
    DATE_TRUNC(date, MONTH) AS ym,
    IF(source = 'jquants', SAFE_DIVIDE(close, pc), SAFE_DIVIDE(pc, close))         AS rc,
    IF(source = 'jquants', SAFE_DIVIDE(adj_close, pa), SAFE_DIVIDE(pa, adj_close)) AS ra
  FROM bd
  WHERE ps IS NOT NULL AND ps <> source
),
monthly AS (
  SELECT
    ticker,
    ym,
    COUNT(*) AS n_boundary,
    APPROX_QUANTILES(rc, 2)[OFFSET(1)] AS med_close,
    APPROX_QUANTILES(ra, 2)[OFFSET(1)] AS med_adj
  FROM ratios
  GROUP BY ticker, ym
),
flagged AS (
  SELECT
    ticker,
    ym,
    n_boundary,
    med_close,
    med_adj,
    COALESCE(med_close > 1.2 OR med_close < 0.833, FALSE) AS bad_close,
    COALESCE(med_adj   > 1.2 OR med_adj   < 0.833, FALSE) AS bad_adj
  FROM monthly
  WHERE n_boundary >= 3
)
SELECT
  ticker,
  ym,
  n_boundary,
  ROUND(med_close, 4) AS med_close,
  ROUND(med_adj, 4)   AS med_adj,
  CASE
    WHEN bad_close AND bad_adj THEN 'both'
    WHEN bad_close            THEN 'close'
    ELSE 'adj'
  END AS drift_col
FROM flagged
WHERE bad_close OR bad_adj;
