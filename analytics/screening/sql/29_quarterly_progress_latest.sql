-- 29_quarterly_progress_latest.sql - one latest disclosure per ticker (C08 _latest)
--
-- Purpose: expose exactly one row per ticker from analytics.quarterly_progress
--   so that screening_candidates can join on ticker without row fan-out.
-- Note: _latest (single newest point) is NOT the same as a dedup series.
-- Source uniqueness is (ticker, disc_no); tie-break by disc_no DESC.
-- quarterly_progress holds Q disclosures only (cur_per_type='FY' is zero rows).
-- no-select-star: every column is listed explicitly (SR-2).

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.quarterly_progress_latest` AS
WITH ranked AS (
  SELECT
    ticker, disc_no, disc_date, doc_type, cur_per_type, cur_per_end,
    sales, f_sales, op, f_op, np, f_np,
    pace_pct, sales_progress_pct, op_progress_pct, np_progress_pct,
    op_progress_status
  FROM `{{PROJECT}}.analytics.quarterly_progress`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY disc_date DESC, disc_no DESC) = 1
)
SELECT
  ticker, disc_no, disc_date, doc_type, cur_per_type, cur_per_end,
  sales, f_sales, op, f_op, np, f_np,
  pace_pct, sales_progress_pct, op_progress_pct, np_progress_pct,
  op_progress_status
FROM ranked;
