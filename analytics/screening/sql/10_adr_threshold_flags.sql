-- 10_adr_threshold_flags.sql — 騰落レシオ 60/140 閾値フラグ(VIEW・C06 第1片)
--
-- 由来: phase45 C06(マクロ閾値フラグ群) のうち「騰落 60/140 点灯」/ A21
--   騰落レシオ25日(adr_25d) を過熱(天井)/売られ過ぎ(底値)の点灯判定に変換
--
-- 定義(A21 の 60/140 閾値):
--   * is_overheated = adr_25d >= 140 (過熱・天井圏)
--   * is_oversold   = adr_25d <= 60  (売られ過ぎ・底値圏)
--   * adr_signal    = 'overheated' / 'oversold' / 'neutral'
--   * adr_25d が NULL(先頭25日未満)の行は全フラグ/signal を NULL(誤点灯を出さない)
--     - BOOL は adr_25d IS NULL のとき自動的に NULL に評価される(明示分岐不要)
--
-- 設計方針:
--   * VIEW(analytics.advance_decline_ratio を直参照。前線前進に自動追従)
--   * 新規データ源ゼロ・raw 非参照(既存 analytics VIEW 派生・単一責任)
--   * no-select-star: 全列明示
--   * 入力 VIEW が partition 下限を内包するため本 VIEW では追加フィルタ不要
--
-- 列: date / adr_25d / is_overheated / is_oversold / adr_signal

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.adr_threshold_flags` AS
SELECT
  date,
  adr_25d,
  adr_25d >= 140 AS is_overheated,
  adr_25d <= 60  AS is_oversold,
  CASE
    WHEN adr_25d IS NULL THEN NULL
    WHEN adr_25d >= 140  THEN 'overheated'
    WHEN adr_25d <= 60   THEN 'oversold'
    ELSE 'neutral'
  END AS adr_signal
FROM `{{PROJECT}}.analytics.advance_decline_ratio`;
