-- 15_fred_sma_cross.sql — FRED日次利回り系 value×sma_25 クロス=トレンド転換フラグ(VIEW・MVP v1)
--
-- 由来: phase45 / 14_fred_sma の後段。value と sma_25 のクロスでトレンド転換を検出。
--
-- 設計方針:
--   * 入力は analytics.fred_sma を直参照(sma_25 は 14 で SSOT 確定済。再デデュプ不要・単一責任)。
--   * diff = value - sma_25。系列内(PARTITION BY indicator_code)・観測日順で LAG(diff) と符号比較。
--       prev_diff <= 0 かつ diff > 0  → bullish_cross(上抜け=強気転換)
--       prev_diff >= 0 かつ diff < 0  → bearish_cross(下抜け=弱気転換)
--       それ以外                      → none
--   * 境界(diff=0)規約: 「同値→上」は bullish、「同値→下」は bearish に含める。
--     「上/下→同値」は抜けきっていないため none。
--   * diff が NULL(sma_25 未確定=先頭25観測未満 or value 欠測)、または prev_diff が NULL
--     (系列先頭/前行欠落)は判定不能として trend_cross=NULL(不完全値を出さない・07/14 同流儀)。
--   * 14 が返す8系列(日次利回り系)をそのまま継承。系列間は独立完結。
--   * no-select-star: 全列明示。

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.fred_sma_cross` AS
WITH base AS (
  SELECT
    indicator_code,
    indicator_name,
    data_date,
    value,
    sma_25,
    value - sma_25 AS diff
  FROM `{{PROJECT}}.analytics.fred_sma`
),
lagged AS (
  SELECT
    indicator_code,
    indicator_name,
    data_date,
    value,
    sma_25,
    diff,
    LAG(diff) OVER (
      PARTITION BY indicator_code
      ORDER BY data_date
    ) AS prev_diff
  FROM base
)
SELECT
  indicator_code,
  indicator_name,
  data_date,
  value,
  sma_25,
  CASE
    WHEN diff IS NULL OR prev_diff IS NULL THEN NULL
    WHEN prev_diff <= 0 AND diff > 0 THEN 'bullish_cross'
    WHEN prev_diff >= 0 AND diff < 0 THEN 'bearish_cross'
    ELSE 'none'
  END AS trend_cross
FROM lagged;
