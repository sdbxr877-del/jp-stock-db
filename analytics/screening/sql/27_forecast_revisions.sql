-- C13: company full-year forecast revision detection (A19).
-- Source: raw.fins_summary (J-Quants /v2/fins/summary, Free).
-- Grain: one row per Q disclosure (1Q/2Q/3Q) carrying a current full-year
--   company forecast (F* fields). FY/4Q disclosures have empty F* and are excluded.
-- Method: within each (ticker, cur_fy_end) series ordered by disclosure date,
--   compare the current F* snapshot to the previous disclosure's F* via LAG.
--   amount = current - previous; rate = amount / ABS(previous) * 100.
-- Status per metric: no_forecast (current F* NULL), initial (first forecast of the
--   fiscal year, no prior), unchanged (amount = 0), upward (> 0), downward (< 0).
--   Rate is emitted only when the prior forecast is present and non-zero.
-- Series VIEW: retains every revision step. A _latest projection is added
--   separately at screening join time.
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.forecast_revisions` AS
WITH q_disc AS (
  SELECT
    ticker,
    code5,
    cur_fy_end,
    disc_no,
    disc_date,
    disc_time,
    cur_per_type,
    f_sales,
    f_op,
    f_np,
    source
  FROM `{{PROJECT}}.raw.fins_summary`
  WHERE cur_per_type IN ('1Q', '2Q', '3Q')
),
lagged AS (
  SELECT
    ticker,
    code5,
    cur_fy_end,
    disc_no,
    disc_date,
    disc_time,
    cur_per_type,
    f_sales,
    f_op,
    f_np,
    source,
    LAG(f_sales)      OVER w AS prev_f_sales,
    LAG(f_op)         OVER w AS prev_f_op,
    LAG(f_np)         OVER w AS prev_f_np,
    LAG(cur_per_type) OVER w AS prev_per_type,
    LAG(disc_date)    OVER w AS prev_disc_date
  FROM q_disc
  WINDOW w AS (
    PARTITION BY ticker, cur_fy_end
    ORDER BY disc_date, disc_time
  )
)
SELECT
  ticker,
  code5,
  cur_fy_end,
  disc_no,
  disc_date,
  disc_time,
  cur_per_type,
  prev_per_type,
  prev_disc_date,
  f_sales,
  f_op,
  f_np,
  prev_f_sales,
  prev_f_op,
  prev_f_np,
  (f_sales - prev_f_sales) AS sales_revision_amt,
  (f_op    - prev_f_op)    AS op_revision_amt,
  (f_np    - prev_f_np)    AS np_revision_amt,
  CASE WHEN prev_f_sales IS NOT NULL AND prev_f_sales != 0
       THEN ROUND((f_sales - prev_f_sales) / ABS(prev_f_sales) * 100, 2) END AS sales_revision_pct,
  CASE WHEN prev_f_op IS NOT NULL AND prev_f_op != 0
       THEN ROUND((f_op - prev_f_op) / ABS(prev_f_op) * 100, 2) END AS op_revision_pct,
  CASE WHEN prev_f_np IS NOT NULL AND prev_f_np != 0
       THEN ROUND((f_np - prev_f_np) / ABS(prev_f_np) * 100, 2) END AS np_revision_pct,
  CASE
    WHEN f_sales IS NULL THEN 'no_forecast'
    WHEN prev_f_sales IS NULL THEN 'initial'
    WHEN f_sales - prev_f_sales > 0 THEN 'upward'
    WHEN f_sales - prev_f_sales < 0 THEN 'downward'
    ELSE 'unchanged'
  END AS sales_revision_status,
  CASE
    WHEN f_op IS NULL THEN 'no_forecast'
    WHEN prev_f_op IS NULL THEN 'initial'
    WHEN f_op - prev_f_op > 0 THEN 'upward'
    WHEN f_op - prev_f_op < 0 THEN 'downward'
    ELSE 'unchanged'
  END AS op_revision_status,
  CASE
    WHEN f_np IS NULL THEN 'no_forecast'
    WHEN prev_f_np IS NULL THEN 'initial'
    WHEN f_np - prev_f_np > 0 THEN 'upward'
    WHEN f_np - prev_f_np < 0 THEN 'downward'
    ELSE 'unchanged'
  END AS np_revision_status,
  source
FROM lagged
