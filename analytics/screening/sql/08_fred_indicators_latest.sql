-- 08_fred_indicators_latest.sql — FRED指標 銘柄(系列)ごと最新1件を抽出(MVP v1)
--
-- 由来: 01_fred_indicators.sql の「latest 抽出は別ビューで実施」を実体化。
-- 設計方針:
--   * VIEW(常に raw.fred_indicators を参照。日次取込の前進に自動追従)
--   * デデュプ: indicator_code ごとに最新 data_date、同一 data_date 再ロードは updated_at 最大
--     (DDL 記載の重複解決規則に一致)
--   * no-select-star: 全列明示
--   * fred_indicators は require_partition_filter 未設定だが、SR-1 流儀で data_date 下限を明示
--     (全履歴を含む no-op 下限。将来 filter 必須化されても安全)

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.fred_indicators_latest` AS
WITH ranked AS (
  SELECT
    indicator_code, indicator_name, data_date, value, updated_at,
    ROW_NUMBER() OVER (
      PARTITION BY indicator_code
      ORDER BY data_date DESC, updated_at DESC
    ) AS rn
  FROM `{{PROJECT}}.raw.fred_indicators`
  WHERE data_date >= DATE '1990-01-01'
)
SELECT
  indicator_code,
  indicator_name,
  data_date,
  value,
  updated_at
FROM ranked
WHERE rn = 1;
