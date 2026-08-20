-- 03_screening_candidates.sql - screening result for the latest business day (v61 linked)
--
-- Joins daily_metrics (latest date) + fundamentals_latest + tickers, applies hard gates
-- and screening conditions, then assigns intra-sector relative ranks.
-- All thresholds are query parameters (run_screening.py injects them from screening_config.yaml).
--
-- v61 change: the gate / rank / composite_score logic is untouched. A final "enriched" stage
-- LEFT JOINs four ticker-unique sources so no row fan-out is possible:
--   capital_metrics            (company-disclosed FY capital layer, v60 rebuild)
--   quarterly_progress_latest  (C08, one latest Q disclosure per ticker)
--   earnings_surprise_latest   (C12, one latest FY surprise per ticker)
--   forecast_revisions_latest  (C13, one latest revision per ticker)
-- Real PBR is computed here as close / bps using the SAME close as the rest of the row
-- (daily_metrics base date), so no mixed price base date is introduced. The legacy
-- pbr_approx column is kept for regression comparison.
--
-- no-select-star: every column is listed explicitly, CTEs included (SR-2).
-- partition-filter-required: daily_metrics is read for the latest date only.
-- PER = close / eps (eps > 0)
-- pbr_approx = PER * clip(roe) * @roe_scale (identity PBR = PER * ROE; roe is a percentage,
--   so @roe_scale = 0.01 converts it; @roe_cap clips outliers seen at +/-13000% level)
--
-- v83 change: the gate / rank / composite_score logic is untouched. One more ticker-unique
-- source is LEFT JOINed in the same "enriched" stage, so no row fan-out is possible:
--   technicals_wilder (C17 second wave, 37_technicals_wilder.sql)
-- Six columns are appended: rsi14_wilder, atr14_wilder_pct, macd, macd_signal, macd_hist,
-- tw_warmup_ok. 37 columns -> 43 columns.
-- Scope note: 34_technicals (mfi14 / stoch / vol_spike20), 35_financial_distortion and
-- 36_supply_demand are deliberately NOT joined here. They are a separate decision and each
-- adds its own scan; this change is the first wire-up only.
-- Quality note: tw_warmup_ok travels with the values because a ticker with fewer than 250
-- rows of history still produces a number, but that number is not warmed up yet.
-- Window note: technicals_wilder uses a 250 business-day ROWS window, which is NOT the
-- calendar-day RANGE window behind turnover_20d / vol_20d in 01_daily_metrics.
CREATE OR REPLACE TABLE `{{PROJECT}}.analytics.screening_candidates` AS
WITH latest AS (
  SELECT MAX(date) AS d FROM `{{PROJECT}}.analytics.daily_metrics`
),
m AS (
  SELECT
    ticker, date, close, adj_close,
    sma25, sma75, ret_1m, ret_3m, ret_6m,
    pct_from_52w_high, turnover_20d, vol_20d
  FROM `{{PROJECT}}.analytics.daily_metrics`
  WHERE date = (SELECT d FROM latest)
),
joined AS (
  SELECT
    m.ticker, m.date, m.close, m.adj_close,
    m.sma25, m.sma75, m.ret_1m, m.ret_3m, m.ret_6m,
    m.pct_from_52w_high, m.turnover_20d, m.vol_20d,
    t.name, t.market, t.sector_name, t.is_active,
    f.eps, f.roe, f.op_margin, f.reported_at AS fin_reported_at,
    SAFE_DIVIDE(m.close, NULLIF(f.eps, 0)) AS per,
    -- clip roe to [-@roe_cap, @roe_cap] before scaling (outlier guard)
    SAFE_DIVIDE(m.close, NULLIF(f.eps, 0))
      * LEAST(GREATEST(f.roe, -@roe_cap), @roe_cap) * @roe_scale AS pbr_approx
  FROM m
  JOIN `{{PROJECT}}.raw.tickers` t USING (ticker)
  LEFT JOIN `{{PROJECT}}.analytics.fundamentals_latest` f USING (ticker)
),
gated AS (
  SELECT
    ticker, date, name, market, sector_name,
    close, per, pbr_approx, roe, op_margin,
    ret_1m, ret_3m, ret_6m, pct_from_52w_high, turnover_20d, vol_20d, fin_reported_at
  FROM joined
  WHERE is_active = TRUE
    AND turnover_20d >= @min_turnover_yen
    AND market IN UNNEST(@allowed_markets)
    AND adj_close > sma75
    AND sma25 > sma75
    AND per > 0 AND per <= @per_max
    AND roe BETWEEN @roe_min AND @roe_cap        -- lower bound + outlier upper guard
    AND ret_3m > @mom_3m_min
),
ranked AS (
  SELECT
    ticker, date, name, market, sector_name,
    close, per, pbr_approx, roe, op_margin,
    ret_1m, ret_3m, ret_6m, pct_from_52w_high, turnover_20d, vol_20d, fin_reported_at,
    PERCENT_RANK() OVER (PARTITION BY sector_name ORDER BY per     ASC)  AS rk_per,
    PERCENT_RANK() OVER (PARTITION BY sector_name ORDER BY roe     DESC) AS rk_roe,
    PERCENT_RANK() OVER (PARTITION BY sector_name ORDER BY ret_3m  DESC) AS rk_mom
  FROM gated
),
cap AS (
  SELECT
    ticker,
    bps, doe_pct,
    eps AS fy_eps,
    equity AS fy_equity,
    reported_at AS fy_reported_at
  FROM `{{PROJECT}}.analytics.capital_metrics`
),
qp AS (
  SELECT
    ticker,
    disc_date AS qp_disc_date,
    cur_per_type AS qp_per_type,
    op_progress_pct,
    op_progress_status
  FROM `{{PROJECT}}.analytics.quarterly_progress_latest`
),
es AS (
  SELECT
    ticker,
    fy_disc_date AS es_disc_date,
    op_surprise_pct,
    op_surprise_status
  FROM `{{PROJECT}}.analytics.earnings_surprise_latest`
),
fr AS (
  SELECT
    ticker,
    disc_date AS fr_disc_date,
    op_revision_pct,
    op_revision_status
  FROM `{{PROJECT}}.analytics.forecast_revisions_latest`
),
tw AS (
  -- One row per ticker on the daily_metrics base date. Verified 2026-08-20: for every date
  -- in technicals_wilder, COUNT(*) equals COUNT(DISTINCT ticker), so this CTE is ticker-unique.
  SELECT
    ticker,
    rsi14_wilder,
    atr14_wilder_pct,
    macd,
    macd_signal,
    macd_hist,
    warmup_ok AS tw_warmup_ok
  FROM `{{PROJECT}}.analytics.technicals_wilder`
  WHERE date = (SELECT d FROM latest)
),
enriched AS (
  SELECT
    r.ticker, r.date, r.name, r.market, r.sector_name,
    r.close, r.per, r.pbr_approx, r.roe, r.op_margin,
    r.ret_1m, r.ret_3m, r.ret_6m, r.pct_from_52w_high, r.turnover_20d, r.vol_20d,
    r.fin_reported_at, r.rk_per, r.rk_roe, r.rk_mom,
    ROUND((r.rk_per + r.rk_roe + r.rk_mom) / 3, 4) AS composite_score,  -- lower is better
    cap.bps, cap.doe_pct, cap.fy_eps, cap.fy_equity, cap.fy_reported_at,
    SAFE_DIVIDE(r.close, NULLIF(cap.bps, 0)) AS pbr,
    qp.qp_disc_date, qp.qp_per_type, qp.op_progress_pct, qp.op_progress_status,
    es.es_disc_date, es.op_surprise_pct, es.op_surprise_status,
    fr.fr_disc_date, fr.op_revision_pct, fr.op_revision_status,
    tw.rsi14_wilder, tw.atr14_wilder_pct,
    tw.macd, tw.macd_signal, tw.macd_hist, tw.tw_warmup_ok
  FROM ranked r
  LEFT JOIN cap USING (ticker)
  LEFT JOIN qp  USING (ticker)
  LEFT JOIN es  USING (ticker)
  LEFT JOIN fr  USING (ticker)
  LEFT JOIN tw  USING (ticker)
)
SELECT
  ticker, date, name, market, sector_name,
  close, per, pbr_approx, pbr, roe, op_margin,
  ret_1m, ret_3m, ret_6m, pct_from_52w_high, turnover_20d, vol_20d, fin_reported_at,
  rk_per, rk_roe, rk_mom, composite_score,
  bps, doe_pct, fy_eps, fy_equity, fy_reported_at,
  qp_disc_date, qp_per_type, op_progress_pct, op_progress_status,
  es_disc_date, op_surprise_pct, op_surprise_status,
  fr_disc_date, op_revision_pct, op_revision_status,
  rsi14_wilder, atr14_wilder_pct, macd, macd_signal, macd_hist, tw_warmup_ok
FROM enriched
ORDER BY composite_score ASC;
