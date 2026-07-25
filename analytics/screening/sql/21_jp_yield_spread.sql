-- 21_jp_yield_spread.sql - JP earnings yield minus 10Y JGB spread (C04)
-- Daily median of (eps/close) over active Prime tickers vs JGB 10Y yield.
-- no-select-star / SR-1: explicit lower-bound filter on prices.date and jgb data_date.
-- period_type is 'annual' for all rows (probe-verified); defensive filter kept.
-- Median via APPROX_QUANTILES only (not mixed with PERCENTILE_CONT OVER).
-- Market label (katakana 'Prime') is built via CODE_POINTS_TO_STRING to keep this file ASCII-only.
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.jp_yield_spread` AS
WITH prime AS (
  SELECT ticker
  FROM `{{PROJECT}}.raw.tickers`
  WHERE is_active = TRUE AND market = CODE_POINTS_TO_STRING([12503, 12521, 12452, 12512])  -- Prime (katakana)
),
fin AS (
  SELECT
    ticker, eps, reported_at,
    ROW_NUMBER() OVER (PARTITION BY ticker, reported_at ORDER BY fiscal_year DESC) AS rn
  FROM `{{PROJECT}}.raw.financials`
  WHERE period_type = 'annual' AND eps IS NOT NULL AND eps > 0
),
iv AS (
  SELECT
    ticker, eps, reported_at AS valid_from,
    LEAD(reported_at) OVER (PARTITION BY ticker ORDER BY reported_at) AS valid_to
  FROM fin
  WHERE rn = 1
),
px AS (
  SELECT ticker, date, close
  FROM `{{PROJECT}}.raw.prices`
  WHERE date >= '1900-01-01' AND close > 0
),
ey AS (
  SELECT
    p.date,
    100.0 * i.eps / p.close AS earnings_yield_pct
  FROM px p
  JOIN prime pr ON p.ticker = pr.ticker
  JOIN iv i
    ON p.ticker = i.ticker
   AND p.date >= i.valid_from
   AND (i.valid_to IS NULL OR p.date < i.valid_to)
),
ey_daily AS (
  SELECT
    date,
    APPROX_QUANTILES(earnings_yield_pct, 2)[OFFSET(1)] AS prime_earnings_yield_pct,
    COUNT(*) AS n_constituents
  FROM ey
  GROUP BY date
),
jgb AS (
  SELECT data_date, value AS jgb10y_pct
  FROM `{{PROJECT}}.analytics.jgb_yields_dedup`
  WHERE tenor = '10Y' AND data_date >= '1900-01-01'
)
SELECT
  e.date,
  e.prime_earnings_yield_pct,
  j.jgb10y_pct,
  e.prime_earnings_yield_pct - j.jgb10y_pct AS yield_spread_pct,
  e.n_constituents
FROM ey_daily e
JOIN jgb j ON e.date = j.data_date;
