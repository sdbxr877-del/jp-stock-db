-- raw.fred_indicators : FRED マクロ指標の生データ蓄積テーブル（追記式）
-- 出典: 設計仕様書「債券市場のマクロ数理構造」FRED 取込設計を流儀適用
--   - dataset は仕様の macro_analysis ではなく既存 raw に寄せる
--   - CREATE OR REPLACE（再実行で全消去）ではなく IF NOT EXISTS（冪等・追記安全）
--   - PARTITION BY data_date（DATE列を直接指定。式ネスト無し）/ CLUSTER BY indicator_code
-- 列:
--   data_date      経済データの対象日付（FRED observation date）
--   indicator_code FRED 固有の Series ID（例 T10Y2Y）
--   indicator_name システム上の識別名称（例 US_10Y_2Y_Spread）
--   value          指標の測定値（休業日の "." はロード前に除去済）
--   updated_at     レコードのクラウド挿入日時（UTC）
-- 重複ロード時は (data_date, indicator_code) 内で updated_at 最大を最新とみなす（latest 抽出は別ビューで実施）

CREATE SCHEMA IF NOT EXISTS `{{PROJECT}}.raw`;

CREATE TABLE IF NOT EXISTS `{{PROJECT}}.raw.fred_indicators`
(
  data_date      DATE      NOT NULL,
  indicator_code STRING    NOT NULL,
  indicator_name STRING    NOT NULL,
  value          FLOAT64   NOT NULL,
  updated_at     TIMESTAMP NOT NULL
)
PARTITION BY data_date
CLUSTER BY indicator_code;
