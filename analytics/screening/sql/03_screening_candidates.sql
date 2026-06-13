-- 03_screening_candidates.sql — 最新営業日のスクリーニング結果(MVP v1)
--
-- daily_metrics(最新日)+ fundamentals_latest + tickers を結合し、
-- ハードゲート + スクリーニング条件で絞り、業種(sector_name)内相対ランクを付与する。
-- 閾値は全てクエリパラメータ(run_screening.py が screening_config.yaml から注入)。
--
-- no-select-star: CTE 含め全列を明示列挙(SELECT * 不使用)。
-- partition-filter-required: daily_metrics は最新日(date=)のみ参照。
-- PER  = close / eps(eps>0)
-- PBR近似 = PER * clip(roe) * @roe_scale(恒等式 PBR=PER*ROE。roe は百分率→@roe_scale=0.01 で小数換算)
--   ※ 確認3 で roe に ±13000% 級の外れ値を確認 → clip(@roe_cap) で異常値を抑制し PBR の発散を防ぐ

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
    -- ROE を [-@roe_cap, @roe_cap] にクリップしてから小数換算(外れ値ガード)
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
    AND roe BETWEEN @roe_min AND @roe_cap        -- 下限 + 外れ値上限ガード(確認3)
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
)
SELECT
  ticker, date, name, market, sector_name,
  close, per, pbr_approx, roe, op_margin,
  ret_1m, ret_3m, ret_6m, pct_from_52w_high, turnover_20d, vol_20d, fin_reported_at,
  rk_per, rk_roe, rk_mom,
  ROUND((rk_per + rk_roe + rk_mom) / 3, 4) AS composite_score   -- 小さいほど上位
FROM ranked
ORDER BY composite_score ASC;
