-- 13_macro_severity.sql — マクロ総合ストレス度 合成VIEW(MVP v1)
--
-- 由来: macro_signals(adr_25d/bull_steepening/credit_hy/liquidity_nfci の各シグナル)を
--   唯一の入力に、is_active を集約して「総合ストレス度」を1行で返す。
--   UI 一目表示の次段(何本中何本が点灯しているか / 総合3値 / 点灯キー)。
-- 設計方針:
--   * VIEW(analytics.macro_signals を直参照。新規データ源ゼロ・単一責任派生)
--   * stress_score = active/total(比率ベース)。将来シグナルが増えても閾値破綻しない
--   * overall_severity(3値):
--       active=0             -> 'calm'
--       0 < 比率 <= 0.5       -> 'elevated'
--       比率 > 0.5            -> 'stress'
--   * active_keys: 点灯シグナルの signal_key を昇順連結(平穏時 NULL)
--   * 鮮度両持ち: as_of_date=MAX(最新評価時点) / oldest_signal_date=MIN(鮮度下限)
--   * 出力は全体集約の1行
--   * no-select-star: 全列明示
--   * macro_signals は VIEW(内部で下限フィルタ済)のため本VIEWでの partition 下限は不要
--
-- 平穏時の期待出力(現状 全 is_active=false):
--   as_of_date=最新 / oldest_signal_date=最古 / total_signals=4 / active_signals=0 /
--   stress_score=0.0 / overall_severity='calm' / active_keys=NULL

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.macro_severity` AS
WITH agg AS (
  SELECT
    MAX(as_of_date)                                          AS as_of_date,
    MIN(as_of_date)                                          AS oldest_signal_date,
    COUNT(*)                                                 AS total_signals,
    COUNTIF(is_active)                                       AS active_signals,
    STRING_AGG(IF(is_active, signal_key, NULL), ', ' ORDER BY signal_key) AS active_keys
  FROM `{{PROJECT}}.analytics.macro_signals`
)
SELECT
  as_of_date,
  oldest_signal_date,
  total_signals,
  active_signals,
  ROUND(SAFE_DIVIDE(active_signals, total_signals), 4)       AS stress_score,
  CASE
    WHEN active_signals = 0 THEN 'calm'
    WHEN SAFE_DIVIDE(active_signals, total_signals) <= 0.5 THEN 'elevated'
    ELSE 'stress'
  END                                                        AS overall_severity,
  active_keys
FROM agg;
