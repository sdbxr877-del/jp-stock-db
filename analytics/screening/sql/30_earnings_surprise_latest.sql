-- 30_earnings_surprise_latest.sql - one latest FY surprise per ticker (C12 _latest)
--
-- Purpose: expose exactly one row per ticker from analytics.earnings_surprise
--   so that screening_candidates can join on ticker without row fan-out.
-- Note: _latest (single newest point) is NOT the same as a dedup series.
-- Source uniqueness is (ticker, cur_fy_end); tie-break by cur_fy_end DESC.
-- no-select-star: every column is listed explicitly (SR-2).

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.earnings_surprise_latest` AS
WITH ranked AS (
  SELECT
    ticker, code5, cur_fy_end, fy_disc_no, fy_disc_date,
    fc_per_type, fc_disc_date,
    sales_actual, op_actual, np_actual,
    f_sales, f_op, f_np,
    sales_surprise_pct, op_surprise_pct, np_surprise_pct,
    op_surprise_status, source
  FROM `{{PROJECT}}.analytics.earnings_surprise`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY fy_disc_date DESC, cur_fy_end DESC) = 1
)
SELECT
  ticker, code5, cur_fy_end, fy_disc_no, fy_disc_date,
  fc_per_type, fc_disc_date,
  sales_actual, op_actual, np_actual,
  f_sales, f_op, f_np,
  sales_surprise_pct, op_surprise_pct, np_surprise_pct,
  op_surprise_status, source
FROM ranked;
