-- 02_fundamentals_latest.sql -- latest single annual financial row per ticker
--
-- Pick one latest row per ticker from raw.financials (non-partitioned).
-- period_type is confirmed all 'annual'; the WHERE clause is a defensive guard
-- against future quarterly rows.
-- v57 (P3): add equity / shares_outstanding / dividend_paid so downstream
-- capital metrics (market cap / BPS / PBR / DOE) read from the same latest
-- annual row. dividend_paid is the raw Cash Dividends Paid value (negative =
-- cash outflow); ABS is applied downstream, not here.
--
-- no-select-star: columns are explicit. financials is non-partitioned so no
-- partition filter is required.
CREATE OR REPLACE TABLE `{{PROJECT}}.analytics.fundamentals_latest` AS
WITH ranked AS (
  SELECT
    ticker, fiscal_year, period_type,
    revenue, op_profit, net_income, eps, roe, reported_at,
    equity, shares_outstanding, dividend_paid,
    ROW_NUMBER() OVER (
      PARTITION BY ticker
      ORDER BY
        CASE WHEN source = 'yfinance' THEN 0 ELSE 1 END,  -- prefer yfinance, edinet fallback (dual-source)
        reported_at DESC,
        fiscal_year DESC
    ) AS rn
  FROM `{{PROJECT}}.raw.financials`
  WHERE eps IS NOT NULL
    AND period_type = 'annual'
)
SELECT
  ticker, fiscal_year,
  revenue, op_profit, net_income, eps, roe, reported_at,
  equity, shares_outstanding, dividend_paid,
  SAFE_DIVIDE(op_profit, NULLIF(revenue, 0)) AS op_margin
FROM ranked
WHERE rn = 1;
