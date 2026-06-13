-- 01_daily_metrics.sql — 対象日(@target_date)1日分を冪等更新(MVP v1)
--
-- 設計方針:
--   * MERGE は WHEN NOT MATCHED INSERT で partition pruning を阻害するため不使用
--     → BEGIN TRANSACTION / DELETE / INSERT / COMMIT(memory 既定)
--   * partition-filter-required: raw.prices は date 範囲を、daily_metrics は date= を明示
--   * no-select-star: 全列を明示列挙
--   * トレンド/リターン/52w高安/ボラは adj_close ベース(分割・配当の不連続を回避)
--     売買代金のみ実取引価格 close を使用
--   * SMA200 / 52w(252営業日)算出のため過去 400 暦日を読み、対象日だけ書き込む
--
-- 注: 本クエリはスクリプト(DECLARE/BEGIN TRANSACTION)。dry-run はスクリプト扱いで
--     scan=0 と表示される場合がある。実コストは raw.prices の date 範囲 read(window 計算)。

DECLARE target_date DATE DEFAULT @target_date;

BEGIN TRANSACTION;

DELETE FROM `{{PROJECT}}.analytics.daily_metrics`
WHERE date = target_date;

INSERT INTO `{{PROJECT}}.analytics.daily_metrics`
( ticker, date, close, adj_close, volume,
  sma25, sma75, sma200,
  ret_1m, ret_3m, ret_6m,
  high_52w, low_52w, pct_from_52w_high,
  turnover_20d, vol_20d, computed_at )
WITH base AS (
  SELECT
    ticker, date, close, adj_close, volume
  FROM `{{PROJECT}}.raw.prices`
  WHERE date BETWEEN DATE_SUB(target_date, INTERVAL 400 DAY) AND target_date
),
with_ret AS (
  SELECT
    ticker, date, close, adj_close, volume,
    SAFE_DIVIDE(adj_close, LAG(adj_close) OVER (PARTITION BY ticker ORDER BY date)) - 1 AS ret_1d
  FROM base
),
calc AS (
  SELECT
    ticker, date, close, adj_close, volume,
    AVG(adj_close) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN  24 PRECEDING AND CURRENT ROW) AS sma25,
    AVG(adj_close) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN  74 PRECEDING AND CURRENT ROW) AS sma75,
    AVG(adj_close) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS sma200,
    SAFE_DIVIDE(adj_close, LAG(adj_close,  21) OVER (PARTITION BY ticker ORDER BY date)) - 1 AS ret_1m,
    SAFE_DIVIDE(adj_close, LAG(adj_close,  63) OVER (PARTITION BY ticker ORDER BY date)) - 1 AS ret_3m,
    SAFE_DIVIDE(adj_close, LAG(adj_close, 126) OVER (PARTITION BY ticker ORDER BY date)) - 1 AS ret_6m,
    MAX(adj_close)     OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS high_52w,
    MIN(adj_close)     OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS low_52w,
    AVG(close * volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS turnover_20d,
    STDDEV_SAMP(ret_1d) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS vol_20d
  FROM with_ret
)
SELECT
  ticker, date, close, adj_close, volume,
  sma25, sma75, sma200,
  ret_1m, ret_3m, ret_6m,
  high_52w, low_52w,
  SAFE_DIVIDE(adj_close, NULLIF(high_52w, 0)) - 1 AS pct_from_52w_high,
  turnover_20d, vol_20d,
  CURRENT_TIMESTAMP() AS computed_at
FROM calc
WHERE date = target_date;

COMMIT TRANSACTION;
