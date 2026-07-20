-- 18_avg_salary_yoy.sql — EDINET 平均年間給与 前年比(VIEW・MVP v1)
--
-- 由来: v49 で raw.financials に追加した avg_salary の後段。
--       銘柄ごと時系列で前年比(賃上げ率)を算出し、スクリーニング指標の素材とする。
--
-- 設計方針:
--   * 入力は raw.financials を直参照(source='edinet' 限定)。avg_salary の派生 VIEW は未存在のため。
--     raw.financials は非 partition のため partition filter は不要(16 と同じ扱い)。
--   * avg_salary は円単位・整数・提出会社ベース(ctx=CurrentYearInstant_NonConsolidatedMember 単一)。
--     連結/単体の混在リスクが無く、単位換算も不要。実測 71/71 で NULL ゼロ。
--   * fiscal_year は文字列 'YY/M' / 'YY/MM' の2書式。辞書順は '21/12' < '21/3' となり誤るため、
--     SPLIT で年・月を数値化した fy_key = 年*100 + 月 で昇順に並べる(17 と同一ロジック)。
--   * LAG の直前行は必ずしも「1年前」ではない。fy_key の差がちょうど 100(=同月・1年差)の
--     場合のみ YoY を成立させ、決算期変更・期間飛び・系列先頭は NULL とする
--     (不完全値を出さない・07/14/15/16/17 と同流儀)。
--     実測(v50): gap は 100 が 55件 / NULL 16件(各社先頭)のみ。飛びはゼロだが将来混入への防御。
--   * prev_salary も同一条件で NULL 化する。「直前行」を「前年」と誤読させないため。
--   * lag_salary <= 0 はゼロ除算・符号反転を避けるため NULL。
--   * no-select-star: 全列明示。
--
-- 期待値(v50 時点の実測前提): 71行 / salary_yoy_pct 非NULL 55行 / NULL 16行(各社先頭期)。
--
-- 列: ticker / fiscal_year / period_type / avg_salary / prev_salary / salary_yoy_pct
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.avg_salary_yoy` AS
WITH keyed AS (
  SELECT
    ticker,
    fiscal_year,
    period_type,
    avg_salary,
    CAST(SPLIT(fiscal_year, '/')[OFFSET(0)] AS INT64) * 100
      + CAST(SPLIT(fiscal_year, '/')[OFFSET(1)] AS INT64) AS fy_key
  FROM `{{PROJECT}}.raw.financials`
  WHERE source = 'edinet'
    AND avg_salary IS NOT NULL
),
lagged AS (
  SELECT
    ticker,
    fiscal_year,
    period_type,
    avg_salary,
    fy_key,
    LAG(avg_salary) OVER w AS lag_salary,
    LAG(fy_key)     OVER w AS lag_fy_key
  FROM keyed
  WINDOW w AS (PARTITION BY ticker ORDER BY fy_key)
)
SELECT
  ticker,
  fiscal_year,
  period_type,
  avg_salary,
  IF(fy_key - lag_fy_key = 100, lag_salary, NULL) AS prev_salary,
  CASE
    WHEN lag_salary IS NULL         THEN NULL
    WHEN fy_key - lag_fy_key <> 100 THEN NULL
    WHEN lag_salary <= 0            THEN NULL
    ELSE ROUND((avg_salary - lag_salary) / lag_salary * 100, 4)
  END AS salary_yoy_pct
FROM lagged;
