-- 32_earnings_price_reaction.sql - post-earnings price reaction (C14)
--
-- Purpose: measure the price and volume reaction to the latest full-year
--   earnings disclosure for each ticker (sell-the-fact detection).
-- Grain: one row per ticker (mirrors analytics.earnings_surprise_latest).
-- Anchors:
--   d0 = last trading day on or before fy_disc_date
--   d1 = first trading day after fy_disc_date (assumes post-close disclosure)
--   d5 = fifth trading day after d0
-- Notes:
--   * raw.prices is read directly; analytics.daily_metrics holds only a few dates.
--   * Macro series (raw.tickers.market = 'INDEX') are excluded; they carry values
--     on weekends and holidays and would shift the trading-day sequence.
--   * Partition lower bound is explicit (partition-filter-required).
--   * Tickers absent from raw.prices yield NULL metrics and has_price = FALSE.
--   * v76: adj_close is normalised before use. raw.prices mixes yfinance and
--     jquants rows, and the jquants adj_close carries a retroactive adjustment on
--     88 tickers, so a source boundary inside the d0..d5 window would corrupt
--     ret_1d / ret_5d. pk picks the surviving column per ticker (12 tickers
--     resolve to 'close'). The logic mirrors 01_daily_metrics.sql.
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.earnings_price_reaction` AS
WITH bd AS (
  -- Adjacent-row view used only to locate source boundaries. Same lower bound as
  -- px so the two CTEs never disagree about which rows exist.
  SELECT
    p.ticker, p.source, p.close, p.adj_close,
    LAG(p.source)    OVER (PARTITION BY p.ticker ORDER BY p.date) AS ps,
    LAG(p.close)     OVER (PARTITION BY p.ticker ORDER BY p.date) AS pc,
    LAG(p.adj_close) OVER (PARTITION BY p.ticker ORDER BY p.date) AS pa
  FROM `{{PROJECT}}.raw.prices` p
  WHERE p.date >= DATE '2024-01-01'
),
pk AS (
  -- Ratios are oriented jquants / yfinance on every boundary, so a healthy column
  -- sits near 1.0. The column with fewer deviations wins; ties go to 'adj'.
  SELECT
    ticker,
    IF(COUNTIF(ra > 2 OR ra < 0.5) <= COUNTIF(rc > 2 OR rc < 0.5), 'adj', 'close') AS pick
  FROM (
    SELECT
      ticker,
      IF(source = 'jquants', SAFE_DIVIDE(close, pc), SAFE_DIVIDE(pc, close)) AS rc,
      IF(source = 'jquants', SAFE_DIVIDE(adj_close, pa), SAFE_DIVIDE(pa, adj_close)) AS ra
    FROM bd
    WHERE ps IS NOT NULL AND ps <> source
  )
  GROUP BY ticker
),
px AS (
  SELECT
    p.ticker,
    p.date,
    -- Per-ticker fallback: pk decides which column survives the source boundary.
    -- yfinance rows already satisfy adj_close = close, so this only ever changes
    -- jquants rows. A ticker absent from pk falls back to 'close'.
    IF(p.source = 'jquants' AND IFNULL(k.pick, 'close') = 'close', p.close, p.adj_close) AS adj_close,
    p.volume,
    ROW_NUMBER() OVER (PARTITION BY p.ticker ORDER BY p.date) AS seq,
    AVG(p.volume) OVER (
      PARTITION BY p.ticker ORDER BY p.date
      ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS avg_volume_20d
  FROM `{{PROJECT}}.raw.prices` p
  LEFT JOIN pk k
    ON k.ticker = p.ticker
  WHERE p.date >= DATE '2024-01-01'
    AND NOT EXISTS (
      SELECT 1
      FROM `{{PROJECT}}.raw.tickers` t
      WHERE t.ticker = p.ticker
        AND t.market = 'INDEX'
    )
),
anchor AS (
  SELECT
    e.ticker,
    px.date AS d0_date,
    px.seq AS d0_seq,
    px.adj_close AS adj_close_d0,
    px.avg_volume_20d
  FROM `{{PROJECT}}.analytics.earnings_surprise_latest` e
  JOIN px
    ON px.ticker = e.ticker
   AND px.date <= e.fy_disc_date
  QUALIFY ROW_NUMBER() OVER (PARTITION BY e.ticker ORDER BY px.date DESC) = 1
)
SELECT
  e.ticker,
  e.fy_disc_date,
  e.op_surprise_pct,
  e.op_surprise_status,
  a.d0_date,
  p1.date AS d1_date,
  p5.date AS d5_date,
  a.adj_close_d0,
  p1.adj_close AS adj_close_d1,
  p5.adj_close AS adj_close_d5,
  SAFE_DIVIDE(p1.adj_close, NULLIF(a.adj_close_d0, 0)) - 1 AS ret_1d,
  SAFE_DIVIDE(p5.adj_close, NULLIF(a.adj_close_d0, 0)) - 1 AS ret_5d,
  p1.volume AS volume_d1,
  a.avg_volume_20d,
  SAFE_DIVIDE(p1.volume, NULLIF(a.avg_volume_20d, 0)) AS volume_ratio,
  (e.op_surprise_pct > 0
    AND SAFE_DIVIDE(p1.adj_close, NULLIF(a.adj_close_d0, 0)) - 1 < 0) AS sell_the_fact,
  (a.d0_date IS NOT NULL AND p1.date IS NOT NULL) AS has_price
FROM `{{PROJECT}}.analytics.earnings_surprise_latest` e
LEFT JOIN anchor a
  ON a.ticker = e.ticker
LEFT JOIN px p1
  ON p1.ticker = a.ticker
 AND p1.seq = a.d0_seq + 1
LEFT JOIN px p5
  ON p5.ticker = a.ticker
 AND p5.seq = a.d0_seq + 5
;
