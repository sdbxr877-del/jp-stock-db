-- 12_macro_signals.sql — マクロ環境シグナル統合VIEW(UI前段・VIEW・MVP v1)
--
-- 由来: phase45 C06 系の集約(統合ビュー)。UI で「今のマクロ環境」を一覧するための前段。
--   既存 analytics VIEW 3本の signal を最新1件ずつ縦持ち(long)で束ねる。
--
-- 設計方針:
--   * VIEW(analytics 派生・raw 非参照。入力VIEW側がフィルタを内包するため本VIEWに下限フィルタ不要)
--   * 新規データ源ゼロ(adr_threshold_flags / bull_steepening / fred_threshold_flags のみ参照)
--   * 粒度不整合の吸収: 各入力を「最新1行」に正規化してから縦持ち UNION ALL で束ねる
--     - adr / bull は日次時系列 → data 基準日 DESC の ROW_NUMBER で最新1行を抽出
--     - fred は indicator×latest が既に1行/系列 → HY / NFCI をそのまま行展開
--   * signal は原文保持(3値/bool を文字列化)。severity 合成は本VIEWでは行わない(単一責任)
--   * is_active: 平常状態(neutral / calm / inactive)以外を TRUE(UI 点灯抽出用)
--     - 入力 signal が NULL の行は「判定不能」→ 該当入力を出力しない(誤点灯ゼロ)
--   * no-select-star: 全列明示
--
-- 出力列: signal_key / category / as_of_date / signal / metric_value / is_active

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.macro_signals` AS
WITH adr_latest AS (
  SELECT date AS as_of_date, adr_signal, adr_25d
  FROM (
    SELECT
      date, adr_signal, adr_25d,
      ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
    FROM `{{PROJECT}}.analytics.adr_threshold_flags`
    WHERE adr_signal IS NOT NULL
  )
  WHERE rn = 1
),
bull_latest AS (
  SELECT data_date AS as_of_date, is_bull_steepening, delta_y2
  FROM (
    SELECT
      data_date, is_bull_steepening, delta_y2,
      ROW_NUMBER() OVER (ORDER BY data_date DESC) AS rn
    FROM `{{PROJECT}}.analytics.bull_steepening`
    WHERE is_bull_steepening IS NOT NULL
  )
  WHERE rn = 1
),
fred_latest AS (
  SELECT indicator_code, data_date AS as_of_date, signal, value
  FROM `{{PROJECT}}.analytics.fred_threshold_flags`
  WHERE signal IS NOT NULL
),
unified AS (
  -- 騰落レシオ(breadth)
  SELECT
    'adr_25d'   AS signal_key,
    'breadth'   AS category,
    as_of_date,
    adr_signal  AS signal,
    adr_25d     AS metric_value,
    (adr_signal <> 'neutral') AS is_active
  FROM adr_latest

  UNION ALL

  -- ブル・スティープニング(yield_curve)
  SELECT
    'bull_steepening' AS signal_key,
    'yield_curve'     AS category,
    as_of_date,
    CASE WHEN is_bull_steepening THEN 'active' ELSE 'inactive' END AS signal,
    delta_y2          AS metric_value,
    is_bull_steepening AS is_active
  FROM bull_latest

  UNION ALL

  -- FRED信用(HY) / 流動性(NFCI)
  SELECT
    CASE indicator_code
      WHEN 'BAMLH0A0HYM2' THEN 'credit_hy'
      WHEN 'NFCI'         THEN 'liquidity_nfci'
      ELSE LOWER(indicator_code)
    END AS signal_key,
    CASE indicator_code
      WHEN 'BAMLH0A0HYM2' THEN 'credit'
      WHEN 'NFCI'         THEN 'liquidity'
      ELSE 'macro'
    END AS category,
    as_of_date,
    signal,
    value AS metric_value,
    (signal <> 'calm') AS is_active
  FROM fred_latest
)
SELECT
  signal_key,
  category,
  as_of_date,
  signal,
  metric_value,
  is_active
FROM unified
ORDER BY category, signal_key;
