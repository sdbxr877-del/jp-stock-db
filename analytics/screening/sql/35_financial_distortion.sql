-- 35_financial_distortion.sql - C20 J-curve distortion flags from cash flow
--
-- Why this exists (v80):
--   C20 asks for companies whose investing outflow exceeds operating cash flow
--   while equity is held up by outside money. raw.fins_summary carries cfo,
--   cfi, cff, cash_eq, equity and equity_ratio, but it carries no column that
--   identifies a government subsidy or a policy loan, so that half of the C20
--   wording cannot be tested directly. cff > 0 stands in for "the hole was
--   filled from outside" and the flag is named for the proxy, not for C20.
--
-- Method:
--   One row per ticker: the latest FY disclosure. LAG over the FY series keeps
--   the prior period equity so "equity was maintained" can be evaluated at all.
--   Flags widen to narrow in four stages instead of collapsing into one boolean,
--   because the raw condition alone matches 26% of the population and is not a
--   signal by itself.
--
-- Reading the output:
--   flag_jcurve_core   -> investing outflow exceeds operating cash flow
--   flag_ext_funded    -> core, and financing cash flow is positive
--   flag_equity_kept   -> ext_funded, and equity is at or above the prior FY
--                         NULL when no prior FY exists - see has_prev_fy
--   flag_jcurve_strict -> equity_kept, and the period ended in a net loss
--
-- Notes:
--   * cf_missing marks rows where cfo or cfi is NULL. Those rows cannot be
--     judged, so every flag is NULL there rather than FALSE.
--   * has_prev_fy is emitted so a NULL flag_equity_kept is never read as FALSE.
--   * v80 measured on the same population: n 4095 / cf_missing 831 /
--     has_prev 2792 / core 1074 / ext 637 / kept 329 / strict 36.
--   * Amount columns are NUMERIC and are left unrounded. Ratios are ROUND 4.
--   * No ticker is hard-coded.

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.financial_distortion` AS
WITH fy AS (
  SELECT
    s.ticker,
    s.disc_no,
    s.disc_date,
    s.cur_fy_end,
    s.sales,
    s.op,
    s.np,
    s.cfo,
    s.cfi,
    s.cff,
    s.cash_eq,
    s.equity,
    s.equity_ratio
  FROM `{{PROJECT}}.raw.fins_summary` s
  WHERE s.disc_date >= DATE '2000-01-01'
    AND s.cur_per_type = 'FY'
),
seq AS (
  SELECT
    f.ticker,
    f.disc_no,
    f.disc_date,
    f.cur_fy_end,
    f.sales,
    f.op,
    f.np,
    f.cfo,
    f.cfi,
    f.cff,
    f.cash_eq,
    f.equity,
    f.equity_ratio,
    LAG(f.equity)       OVER (PARTITION BY f.ticker ORDER BY f.disc_date, f.disc_no) AS prev_equity,
    LAG(f.equity_ratio) OVER (PARTITION BY f.ticker ORDER BY f.disc_date, f.disc_no) AS prev_equity_ratio,
    ROW_NUMBER()        OVER (PARTITION BY f.ticker ORDER BY f.disc_date DESC, f.disc_no DESC) AS rn
  FROM fy f
),
latest AS (
  SELECT
    ticker,
    disc_no,
    disc_date,
    cur_fy_end,
    sales,
    op,
    np,
    cfo,
    cfi,
    cff,
    cash_eq,
    equity,
    equity_ratio,
    prev_equity,
    prev_equity_ratio,
    (cfo IS NULL OR cfi IS NULL) AS cf_missing,
    (prev_equity IS NOT NULL)    AS has_prev_fy
  FROM seq
  WHERE rn = 1
)
SELECT
  ticker,
  disc_no,
  disc_date,
  cur_fy_end,
  sales,
  op,
  np,
  cfo,
  cfi,
  cff,
  cash_eq,
  equity,
  ROUND(equity_ratio, 4)      AS equity_ratio,
  prev_equity,
  ROUND(prev_equity_ratio, 4) AS prev_equity_ratio,
  cf_missing,
  has_prev_fy,
  IF(cf_missing, NULL, -cfi - cfo)                   AS jcurve_gap,
  IF(cf_missing, NULL, cfo + cfi)                    AS fcf_proxy,
  equity - prev_equity                               AS equity_delta,
  ROUND(equity_ratio - prev_equity_ratio, 4)         AS equity_ratio_delta,
  ROUND(SAFE_DIVIDE(cash_eq, NULLIF(-cfi, 0)), 4)    AS cash_cover,
  ROUND(SAFE_DIVIDE(cfo, NULLIF(sales, 0)), 4)       AS cfo_margin,
  IF(cf_missing, NULL,
     cfi < 0 AND -cfi > cfo)                         AS flag_jcurve_core,
  IF(cf_missing, NULL,
     cfi < 0 AND -cfi > cfo AND cff > 0)             AS flag_ext_funded,
  IF(cf_missing, NULL,
     cfi < 0 AND -cfi > cfo AND cff > 0
     AND equity >= prev_equity)                      AS flag_equity_kept,
  IF(cf_missing, NULL,
     cfi < 0 AND -cfi > cfo AND cff > 0
     AND equity >= prev_equity AND np < 0)           AS flag_jcurve_strict
FROM latest;
