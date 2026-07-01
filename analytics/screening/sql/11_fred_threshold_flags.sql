-- 11_fred_threshold_flags.sql — FRED マクロ閾値フラグ(昇順ストレス型・VIEW・C06 第2片)
--
-- 由来: phase45 C06(マクロ閾値フラグ群) のうち FRED 系点灯 / A03・A05
--   信用収縮(HYスプレッド)・流動性危機(NFCI) を calm/warning/stress に変換
--
-- 定義(いずれも「値が大きいほどストレス」の昇順型・2閾値):
--   * BAMLH0A0HYM2 (HYスプレッド,%): lower=4.5 / upper=6.0  (A03 信用収縮)
--   * NFCI         (金融活動指数):   lower=0.0 / upper=0.5  (A05 流動性危機)
--   * signal: value>=upper→'stress' / value>=lower→'warning' / else→'calm'
--   * value が NULL の行は signal=NULL(誤点灯を出さない)
--
-- 設計方針:
--   * VIEW(analytics.fred_indicators_latest を直参照。前線前進に自動追従)
--   * 新規データ源ゼロ・raw 非参照(既存 analytics VIEW 派生・単一責任)
--   * 閾値は indicator 別に thresholds CTE で明示。INNER JOIN で対象指標のみ出力
--     (将来 indicator を増やす場合は UNION 行追加のみ・昇順ストレス型に限る)
--   * 重大度は順序尺度のため bool ではなく 3 値 signal で表現
--   * no-select-star: 全列明示
--   * 入力が VIEW のため partition 下限は入力側が内包(本 VIEW で追加不要)
--
-- 列: indicator_code / indicator_name / data_date / value / lower_threshold / upper_threshold / signal

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.fred_threshold_flags` AS
WITH thresholds AS (
  SELECT 'BAMLH0A0HYM2' AS indicator_code, 4.5 AS lower_threshold, 6.0 AS upper_threshold
  UNION ALL
  SELECT 'NFCI'         AS indicator_code, 0.0 AS lower_threshold, 0.5 AS upper_threshold
)
SELECT
  l.indicator_code,
  l.indicator_name,
  l.data_date,
  l.value,
  t.lower_threshold,
  t.upper_threshold,
  CASE
    WHEN l.value IS NULL              THEN NULL
    WHEN l.value >= t.upper_threshold THEN 'stress'
    WHEN l.value >= t.lower_threshold THEN 'warning'
    ELSE 'calm'
  END AS signal
FROM `{{PROJECT}}.analytics.fred_indicators_latest` AS l
JOIN thresholds AS t USING (indicator_code);
