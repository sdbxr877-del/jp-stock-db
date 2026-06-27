-- 05_manual_inputs_latest.sql — 手動入力の「最新値」抽出(MVP v1)
--
-- analytics.manual_inputs(追記式・履歴あり)から ticker x field ごとに最新1件を取る。
-- UI / 分析層はこのテーブルを ticker で JOIN して「自動データ + 手動データ」を統合表示する。
-- 履歴全体は manual_inputs 本体に残るため、推移を見たい場合は本体を直接参照する。
--
-- no-select-star: 列を明示。manual_inputs は entered_at で partition のため、
--   全 field の最新を取る本クエリでは partition filter を付けない(全期間横断が目的)。
--   ※ 件数が大きくなったら、UI 側で対象 ticker を絞ってから JOIN しスキャン量を抑える。

CREATE OR REPLACE TABLE `{{PROJECT}}.analytics.manual_inputs_latest` AS
WITH ranked AS (
  SELECT
    ticker, category, field, value_num, value_text, unit,
    as_of_date, source_note, entered_at, entered_by,
    ROW_NUMBER() OVER (
      PARTITION BY ticker, field
      ORDER BY entered_at DESC
    ) AS rn
  FROM `{{PROJECT}}.analytics.manual_inputs`
)
SELECT
  ticker, category, field, value_num, value_text, unit,
  as_of_date, source_note, entered_at, entered_by
FROM ranked
WHERE rn = 1;
