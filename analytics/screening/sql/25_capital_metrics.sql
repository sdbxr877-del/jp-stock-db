-- 25_capital_metrics.sql -- per-ticker valuation metrics (VIEW)
--
-- Combines analytics.fundamentals_latest (latest annual equity / shares /
-- dividend / eps) with the latest close from raw.prices to derive:
--   market_cap = close * shares_outstanding
--   bps        = equity / shares_outstanding
--   per        = close / eps
--   pbr        = close / bps   (equivalently market_cap / equity)
--   doe_pct    = ABS(dividend_paid) / equity * 100   (Dividend On Equity, %)
--
-- dividend_paid is negative in source (cash outflow); ABS yields the annual
-- payout. No-dividend names are NULL here and should be treated as 0 by the
-- consumer (COALESCE) rather than excluded.
--
-- prices is PARTITION BY date: latest_px applies an explicit lower-bound date
-- filter (SR-1) before picking the most recent row per ticker via QUALIFY.
-- LEFT JOIN keeps tickers even when a recent price is missing (metrics NULL).
-- no-select-star: columns are explicit.
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.capital_metrics` AS
WITH latest_px AS (
  SELECT
    ticker,
    close,
    date AS price_date
  FROM `{{PROJECT}}.raw.prices`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) = 1
)
SELECT
  f.ticker,
  f.fiscal_year,
  f.reported_at,
  p.price_date,
  p.close,
  f.eps,
  f.equity,
  f.shares_outstanding,
  f.dividend_paid,
  p.close * f.shares_outstanding                                    AS market_cap,
  SAFE_DIVIDE(f.equity, f.shares_outstanding)                       AS bps,
  SAFE_DIVIDE(p.close, NULLIF(f.eps, 0))                            AS per,
  SAFE_DIVIDE(p.close, SAFE_DIVIDE(f.equity, f.shares_outstanding)) AS pbr,
  SAFE_DIVIDE(ABS(f.dividend_paid), NULLIF(f.equity, 0)) * 100      AS doe_pct
FROM `{{PROJECT}}.analytics.fundamentals_latest` f
LEFT JOIN latest_px p USING (ticker);
