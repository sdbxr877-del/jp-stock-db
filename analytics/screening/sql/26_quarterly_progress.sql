-- 26_quarterly_progress.sql -- C08 quarterly progress = cumulative actual / current-FY company forecast.
-- Grain: one row per quarterly disclosure (1Q/2Q/3Q) in raw.fins_summary. FY rows excluded (no in-year forecast).
-- Progress computed only when forecast > 0 (positive guidance); op_progress_status flags exceptions.
-- Deploy via {{PROJECT}} stdin pipe. No SELECT *; source is clustered (no partition filter needed).

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.quarterly_progress` AS
SELECT
  ticker,
  disc_no,
  disc_date,
  doc_type,
  cur_per_type,
  cur_per_end,
  sales,
  f_sales,
  op,
  f_op,
  np,
  f_np,
  CASE cur_per_type WHEN '1Q' THEN 25.0 WHEN '2Q' THEN 50.0 WHEN '3Q' THEN 75.0 END AS pace_pct,
  CASE WHEN f_sales > 0 THEN ROUND(sales / f_sales * 100, 1) END AS sales_progress_pct,
  CASE WHEN f_op    > 0 THEN ROUND(op    / f_op    * 100, 1) END AS op_progress_pct,
  CASE WHEN f_np    > 0 THEN ROUND(np    / f_np    * 100, 1) END AS np_progress_pct,
  CASE
    WHEN f_op IS NULL THEN 'no_forecast'
    WHEN f_op <= 0 AND op > 0 THEN 'loss_to_profit'
    WHEN f_op <= 0 THEN 'forecast_nonpositive'
    WHEN op < 0 THEN 'profit_forecast_actual_loss'
    ELSE 'normal'
  END AS op_progress_status
FROM `{{PROJECT}}.raw.fins_summary`
WHERE cur_per_type IN ('1Q', '2Q', '3Q');
