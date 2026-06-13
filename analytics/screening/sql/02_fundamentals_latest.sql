-- 02_fundamentals_latest.sql — 銘柄ごと最新財務1件を抽出(MVP v1)
--
-- raw.financials(16,835行・partition なし)から ticker ごと最新を1件選ぶ。
-- ★確認1: period_type の実値が不明。四半期と通期が混在すると net_income 等が歪むため、
--   下の helper で実値を確認し、annual 相当値に確定したら WHERE 句を有効化すること。
--
--   helper(実値確認・コピペ用):
--     SELECT period_type, COUNT(*) c
--     FROM `{{PROJECT}}.raw.financials`
--     GROUP BY period_type ORDER BY c DESC;
--
-- no-select-star: 列を明示。financials は非 partition のため partition filter は不要。

CREATE OR REPLACE TABLE `{{PROJECT}}.analytics.fundamentals_latest` AS
WITH ranked AS (
  SELECT
    ticker, fiscal_year, period_type,
    revenue, op_profit, net_income, eps, roe, reported_at,
    ROW_NUMBER() OVER (
      PARTITION BY ticker
      ORDER BY reported_at DESC, fiscal_year DESC
    ) AS rn
  FROM `{{PROJECT}}.raw.financials`
  WHERE eps IS NOT NULL
    AND period_type = 'annual'   -- 確認1 実測: 全件 annual。将来 quarterly 混入を防ぐ防御的記述
)
SELECT
  ticker, fiscal_year,
  revenue, op_profit, net_income, eps, roe, reported_at,
  SAFE_DIVIDE(op_profit, NULLIF(revenue, 0)) AS op_margin
FROM ranked
WHERE rn = 1;
