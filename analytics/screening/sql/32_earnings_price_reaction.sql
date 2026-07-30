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
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.earnings_price_reaction` AS
WITH px AS (
  SELECT
    p.ticker,
    p.date,
    p.adj_close,
    p.volume,
    ROW_NUMBER() OVER (PARTITION BY p.ticker ORDER BY p.date) AS seq,
    AVG(p.volume) OVER (
      PARTITION BY p.ticker ORDER BY p.date
      ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS avg_volume_20d
  FROM `{{PROJECT}}.raw.prices` p
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
