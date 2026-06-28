-- 09_bull_steepening.sql — ブル・スティープニング検知フラグ(マクロ・VIEW・MVP v1)
--
-- 由来: phase45 C02 / A02
--   ブル・スティープニング = ΔY2<0 かつ |ΔY2|>|ΔY10|
--   (短期 DGS2 が長期 DGS10 より大きく低下 → 利下げ期待主導のスティープ化)
-- 設計方針:
--   * VIEW(raw.fred_indicators の DGS2/DGS10 時系列を直参照。latest ビューは使わない)
--   * ΔY は「直前観測日」基準の LAG 差分(休業日 '.' 除去による歯抜けに頑健)
--   * 追記式テーブルのため、LAG 前に (indicator_code, data_date) を updated_at 最大でデデュプ
--   * ΔY は各指標の自系列内 LAG で算出してから data_date で突合(系列ごとの前日定義を保つ)
--   * フラグは BOOL。ΔY が NULL(各系列の初観測日等)の日は is_bull_steepening=NULL
--   * no-select-star: 全列明示
--   * fred_indicators は require_partition_filter 未設定だが SR-1 流儀で data_date 下限を明示

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.bull_steepening` AS
WITH src AS (
  SELECT indicator_code, data_date, value, updated_at
  FROM `{{PROJECT}}.raw.fred_indicators`
  WHERE data_date >= DATE '1990-01-01'
    AND indicator_code IN ('DGS2', 'DGS10')
),
dedup AS (
  SELECT indicator_code, data_date, value
  FROM (
    SELECT
      indicator_code, data_date, value,
      ROW_NUMBER() OVER (
        PARTITION BY indicator_code, data_date
        ORDER BY updated_at DESC
      ) AS rn
    FROM src
  )
  WHERE rn = 1
),
delta AS (
  SELECT
    indicator_code, data_date, value,
    value - LAG(value) OVER (PARTITION BY indicator_code ORDER BY data_date) AS d_value
  FROM dedup
),
y2 AS (
  SELECT data_date, value AS dgs2, d_value AS delta_y2
  FROM delta WHERE indicator_code = 'DGS2'
),
y10 AS (
  SELECT data_date, value AS dgs10, d_value AS delta_y10
  FROM delta WHERE indicator_code = 'DGS10'
)
SELECT
  y2.data_date,
  y2.dgs2,
  y10.dgs10,
  y2.delta_y2,
  y10.delta_y10,
  (y2.delta_y2 < 0 AND ABS(y2.delta_y2) > ABS(y10.delta_y10)) AS is_bull_steepening
FROM y2
INNER JOIN y10 USING (data_date);
