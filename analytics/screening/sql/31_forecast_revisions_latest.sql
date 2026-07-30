-- 31_forecast_revisions_latest.sql - one latest revision per ticker (C13 _latest)
--
-- Purpose: expose exactly one row per ticker from analytics.forecast_revisions
--   so that screening_candidates can join on ticker without row fan-out.
-- Note: _latest (single newest point) is NOT the same as a dedup series.
-- Source uniqueness is (ticker, disc_no); tie-break by disc_time then disc_no DESC.
-- no-select-star: every column is listed explicitly (SR-2).

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.forecast_revisions_latest` AS
WITH ranked AS (
  SELECT
    ticker, code5, cur_fy_end, disc_no, disc_date, disc_time,
    cur_per_type, prev_per_type, prev_disc_date,
    f_sales, f_op, f_np,
    prev_f_sales, prev_f_op, prev_f_np,
    sales_revision_amt, op_revision_amt, np_revision_amt,
    sales_revision_pct, op_revision_pct, np_revision_pct,
    sales_revision_status, op_revision_status, np_revision_status,
    source
  FROM `{{PROJECT}}.analytics.forecast_revisions`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY disc_date DESC, disc_time DESC, disc_no DESC) = 1
)
SELECT
  ticker, code5, cur_fy_end, disc_no, disc_date, disc_time,
  cur_per_type, prev_per_type, prev_disc_date,
  f_sales, f_op, f_np,
  prev_f_sales, prev_f_op, prev_f_np,
  sales_revision_amt, op_revision_amt, np_revision_amt,
  sales_revision_pct, op_revision_pct, np_revision_pct,
  sales_revision_status, op_revision_status, np_revision_status,
  source
FROM ranked;
