-- C12: earnings surprise vs shadow consensus (A15 x B01 free fallback).
-- Source: raw.fins_summary (J-Quants /v2/fins/summary, Free).
-- Shadow consensus: the company's own latest full-year forecast (F*) standing
--   before the annual result, i.e. the most recent Q disclosure (1Q/2Q/3Q) of the
--   same fiscal year. This already embeds every mid-period timely-disclosure
--   revision, so no separate consensus feed is needed.
-- Grain: one row per (ticker, cur_fy_end) that has an FY disclosure (full-year
--   actual). Surprise = (FY actual - last forecast) / ABS(last forecast) * 100
--   for sales / op / np.
-- Status (op headline): no_prior_forecast (no prior Q forecast in window),
--   forecast_nonpositive (last f_op = 0, rate undefined),
--   profit_forecast_actual_loss (f_op > 0 but actual op < 0),
--   loss_to_profit (f_op < 0 but actual op >= 0), normal (pct sign = beat/miss).
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.earnings_surprise` AS
WITH fy_actual AS (
  SELECT
    ticker,
    code5,
    cur_fy_end,
    disc_no,
    disc_date,
    sales,
    op,
    np,
    source
  FROM `{{PROJECT}}.raw.fins_summary`
  WHERE cur_per_type = 'FY'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ticker, cur_fy_end
    ORDER BY disc_date DESC, fetched_at DESC
  ) = 1
),
last_forecast AS (
  SELECT
    ticker,
    cur_fy_end,
    disc_date AS fc_disc_date,
    cur_per_type AS fc_per_type,
    f_sales,
    f_op,
    f_np
  FROM `{{PROJECT}}.raw.fins_summary`
  WHERE cur_per_type IN ('1Q', '2Q', '3Q')
    AND f_op IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ticker, cur_fy_end
    ORDER BY disc_date DESC, fetched_at DESC
  ) = 1
)
SELECT
  a.ticker,
  a.code5,
  a.cur_fy_end,
  a.disc_no AS fy_disc_no,
  a.disc_date AS fy_disc_date,
  f.fc_per_type,
  f.fc_disc_date,
  a.sales AS sales_actual,
  a.op AS op_actual,
  a.np AS np_actual,
  f.f_sales,
  f.f_op,
  f.f_np,
  CASE WHEN f.f_sales IS NOT NULL AND f.f_sales != 0
       THEN ROUND((a.sales - f.f_sales) / ABS(f.f_sales) * 100, 2) END AS sales_surprise_pct,
  CASE WHEN f.f_op IS NOT NULL AND f.f_op != 0
       THEN ROUND((a.op - f.f_op) / ABS(f.f_op) * 100, 2) END AS op_surprise_pct,
  CASE WHEN f.f_np IS NOT NULL AND f.f_np != 0
       THEN ROUND((a.np - f.f_np) / ABS(f.f_np) * 100, 2) END AS np_surprise_pct,
  CASE
    WHEN f.f_op IS NULL THEN 'no_prior_forecast'
    WHEN f.f_op = 0 THEN 'forecast_nonpositive'
    WHEN f.f_op > 0 AND a.op < 0 THEN 'profit_forecast_actual_loss'
    WHEN f.f_op < 0 AND a.op >= 0 THEN 'loss_to_profit'
    ELSE 'normal'
  END AS op_surprise_status,
  a.source
FROM fy_actual AS a
LEFT JOIN last_forecast AS f
  ON a.ticker = f.ticker
 AND a.cur_fy_end = f.cur_fy_end
 AND f.fc_disc_date < a.disc_date
