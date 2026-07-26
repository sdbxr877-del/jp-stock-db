-- 25_capital_metrics.sql
-- capital_metrics VIEW: per-ticker capital and valuation snapshot.
-- Source: raw.fins_summary latest FY disclosure (company-reported), joined to latest close.
-- Rationale: replaces yfinance-derived fundamentals_latest to fix share-count noise
-- and DOE false-negatives (dividend_paid NULL). PBR uses company-reported bps directly
-- because equity may include non-controlling interests.
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.capital_metrics` AS
WITH latest_fin AS (
  SELECT
    ticker,
    cur_fy_end,
    disc_date,
    eps,
    equity,
    bps,
    shares_out_fy,
    treasury_shares_fy,
    div_total_ann
  FROM `{{PROJECT}}.raw.fins_summary`
  WHERE cur_per_type = 'FY'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ticker
    ORDER BY disc_date DESC, fetched_at DESC
  ) = 1
),
latest_px AS (
  SELECT
    ticker,
    close
  FROM `{{PROJECT}}.raw.prices`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) = 1
)
SELECT
  f.ticker,
  f.cur_fy_end                                                  AS fiscal_year,
  f.disc_date                                                   AS reported_at,
  p.close,
  f.eps,
  f.equity,
  f.shares_out_fy - COALESCE(f.treasury_shares_fy, 0)           AS shares_outstanding,
  f.div_total_ann                                               AS dividend_paid,
  p.close * (f.shares_out_fy - COALESCE(f.treasury_shares_fy, 0)) AS market_cap,
  f.bps,
  SAFE_DIVIDE(p.close, NULLIF(f.eps, 0))                        AS per,
  SAFE_DIVIDE(p.close, NULLIF(f.bps, 0))                        AS pbr,
  SAFE_DIVIDE(f.div_total_ann, NULLIF(f.equity, 0)) * 100       AS doe_pct
FROM latest_fin f
LEFT JOIN latest_px p USING (ticker);
