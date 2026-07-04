-- 14_fred_sma.sql — FRED日次利回り系 SMA25 + UI可変算出用SSOT系列(VIEW・MVP v1)
--
-- 由来: phase45 / FRED SMA(latest と分離)。履歴約5年で移動平均が意味を持つ段階。
--
-- 設計方針:
--   * VIEW(raw.fred_indicators を直参照。日次取込の前進に自動追従。latest ビューは使わない)
--   * 対象は日次利回り系8本のみ。週次系列(NFCI/WALCL)は公表頻度が異なり
--     行数ベース窓の意味が割れるため本 VIEW から除外(必要なら別 VIEW)。
--   * 追記式テーブルのため、窓計算前に (indicator_code, data_date) を updated_at 最大でデデュプ
--     (09_bull_steepening と同型)。
--   * SMA は系列内(PARTITION BY indicator_code)・観測日順の行数ベース窓
--     ROWS BETWEEN 24 PRECEDING AND CURRENT ROW = 25営業日換算。系列間で独立完結。
--   * 25観測未満の先頭期間は sma_25=NULL(不完全値を出さない・07 と同流儀)。
--   * メイン窓は 25 に固定。UI での可変 N(5/10/25 等)は本 VIEW が返す
--     日次系列(indicator_code/data_date/value)から UI 側で算出(BQ 再スキャンゼロ)。
--   * HY(BAMLH0A0HYM2)は FRED 提供下限 2023-07-04。系列内完結のため他系列に影響せず、
--     立ち上がり(先頭25観測)が他系列より遅い点のみ留意。
--   * no-select-star: 全列明示。
--   * fred_indicators は require_partition_filter 未設定だが SR-1 流儀で data_date 下限を明示。

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.fred_sma` AS
WITH src AS (
  SELECT indicator_code, indicator_name, data_date, value, updated_at
  FROM `{{PROJECT}}.raw.fred_indicators`
  WHERE data_date >= DATE '1990-01-01'
    AND indicator_code IN (
      'DGS2', 'DGS10', 'DGS3MO', 'DFII10',
      'T10Y2Y', 'T10Y3M', 'T10YIE', 'BAMLH0A0HYM2'
    )
),
dedup AS (
  SELECT indicator_code, indicator_name, data_date, value
  FROM (
    SELECT
      indicator_code, indicator_name, data_date, value,
      ROW_NUMBER() OVER (
        PARTITION BY indicator_code, data_date
        ORDER BY updated_at DESC
      ) AS rn
    FROM src
  )
  WHERE rn = 1
),
rolling AS (
  SELECT
    indicator_code, indicator_name, data_date, value,
    COUNT(*)   OVER w AS win_n,
    AVG(value) OVER w AS avg_25
  FROM dedup
  WINDOW w AS (
    PARTITION BY indicator_code
    ORDER BY data_date
    ROWS BETWEEN 24 PRECEDING AND CURRENT ROW
  )
)
SELECT
  indicator_code,
  indicator_name,
  data_date,
  value,
  CASE
    WHEN win_n < 25 THEN NULL
    ELSE ROUND(avg_25, 4)
  END AS sma_25
FROM rolling;
