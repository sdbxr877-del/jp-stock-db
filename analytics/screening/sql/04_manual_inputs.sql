-- 04_manual_inputs.sql — analytics.manual_inputs の永続テーブル定義(MVP v1)
--
-- 無料APIで自動取得できない項目を、ユーザーがスプレッドシート等で手入力し蓄積する独立テーブル。
-- screening の日次 CREATE OR REPLACE で消えないよう raw/analytics の自動生成テーブルとは分離する。
--
-- 設計方針(db_v0.21 確定):
--   (A) 独立テーブル: 日次再走から保護。表示時に ticker(+必要なら as_of_date)で JOIN。
--   (B) 追記式: 同一 ticker x field を再入力したら上書きせず履歴として積む。
--       「最新値」は entered_at の最大で1件取る(fundamentals_latest と同じ ROW_NUMBER 方式)。
--       履歴全体も残るため、目標株価やレーティングの推移を後から追える。
--   (C) 汎用 category/field: 取得元の増減に強い縦持ち(EAV)構造。列追加なしで項目を増やせる。
--       数値は value_num、テキスト(レーティング等)は value_text に分けて格納。
--
-- 収容対象(db_v0.21 時点):
--   [諦め4項目] consensus_eps / target_price / rating / company_eps(予想未開示時の手入力)
--   [①6項目]   free_float / option_iv / trading_by_investor_type /
--               outside_director_ratio / patent_metric / govt_subsidy
--   ※ 上記は例示。category/field は自由に追加可(列変更不要)。
--
-- no-select-star: 読み出し側クエリでも列を明示すること(SR-2)。
-- 非 partition 運用も可だが、将来の件数増と as_of_date 範囲読みに備え entered_at で月次 partition。

CREATE SCHEMA IF NOT EXISTS `{{PROJECT}}.analytics`;

CREATE TABLE IF NOT EXISTS `{{PROJECT}}.analytics.manual_inputs`
(
  ticker        STRING     NOT NULL,            -- 銘柄コード(4桁)。raw.tickers.ticker と整合
  category      STRING     NOT NULL,            -- 大分類: 'valuation'/'consensus'/'supply_demand'/'governance'/'ip' 等
  field         STRING     NOT NULL,            -- 項目名: 'consensus_eps'/'target_price'/'rating'/'company_eps'/
                                                --         'free_float'/'option_iv'/'trading_by_investor_type'/
                                                --         'outside_director_ratio'/'patent_metric'/'govt_subsidy' 等
  value_num     FLOAT64,                        -- 数値項目(EPS・目標株価・比率・建玉 等)。テキスト項目では NULL
  value_text    STRING,                         -- テキスト項目(レーティング 'buy'/'hold'/'sell' 等)。数値項目では NULL
  unit          STRING,                         -- 任意: 単位明示('JPY'/'%'/'shares'/'count' 等)。解釈ブレ防止
  as_of_date    DATE,                           -- 任意: その値が「いつ時点」か(レポート基準日・四半期末 等)。鮮度判別用
  source_note   STRING,                         -- 任意: 出典・根拠メモ(例「○○証券 2026-06-14 レポート」)
  entered_at    TIMESTAMP  NOT NULL,            -- 入力時刻。これで履歴が時系列に積まれる(追記式の要)
  entered_by    STRING                          -- 任意: 入力者。今は固定でよいが将来の多人数化に備える
)
PARTITION BY TIMESTAMP_TRUNC(entered_at, MONTH)
CLUSTER BY ticker, field;
