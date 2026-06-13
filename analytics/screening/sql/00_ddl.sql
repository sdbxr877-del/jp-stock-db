-- 00_ddl.sql — analytics.daily_metrics の永続テーブル定義(MVP v1)
-- analytics データセットは既存(bq ls で確認済・空)。CREATE SCHEMA は安全弁。
-- fundamentals_latest / screening_candidates は各クエリ内 CREATE OR REPLACE のため DDL 不要。
-- daily_metrics のみ日次 append(冪等 DELETE->INSERT)するため事前に存在させる。

CREATE SCHEMA IF NOT EXISTS `{{PROJECT}}.analytics`;

CREATE TABLE IF NOT EXISTS `{{PROJECT}}.analytics.daily_metrics`
(
  ticker            STRING  NOT NULL,
  date              DATE    NOT NULL,
  close             FLOAT64,            -- 実取引価格(売買代金・PER 用)
  adj_close         FLOAT64,            -- 調整後終値(トレンド・リターン用)
  volume            INT64,
  sma25             FLOAT64,            -- adj_close ベース単純移動平均
  sma75             FLOAT64,
  sma200            FLOAT64,
  ret_1m            FLOAT64,            -- 21営業日リターン
  ret_3m            FLOAT64,            -- 63営業日
  ret_6m            FLOAT64,            -- 126営業日
  high_52w          FLOAT64,            -- 直近252営業日 adj_close 最高
  low_52w           FLOAT64,            -- 同 最安
  pct_from_52w_high FLOAT64,            -- adj_close / high_52w - 1(高値からの乖離)
  turnover_20d      FLOAT64,            -- 20日平均売買代金(close * volume)
  vol_20d           FLOAT64,            -- 20日日次リターン標準偏差
  computed_at       TIMESTAMP
)
PARTITION BY date
CLUSTER BY ticker;
