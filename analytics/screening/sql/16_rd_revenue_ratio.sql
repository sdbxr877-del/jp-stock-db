-- 16_rd_revenue_ratio.sql — EDINET R&D費/売上高比率(VIEW・MVP v1)
--
-- 由来: phase45 / edinet rd_expenses backfill(v35・8ab5c0c)の後段。
--       rd_expenses と revenue は同一行・同一単位(百万円)。比率は無次元のため単位換算不要。
--
-- 設計方針:
--   * 入力は raw.financials を直参照。source='edinet' かつ rd_expenses IS NOT NULL に限定
--     (rd_expenses は現状 edinet のみ充填。yfinance revenue=円 とは結合しない=単位差回避)。
--   * rd_ratio_pct = rd_expenses / revenue * 100(両者 百万円・無次元)。
--   * revenue が NULL/0以下 は比率不定として rd_ratio_pct=NULL(不完全値を出さない・07/14/15 同流儀)。
--   * キーは ticker×fiscal_year。period_type は probe実測で annual のみだが将来差異に備え列出力。
--   * 母集団: 6銘柄×4年=24行(4080/5191/5476/6312/7817/9776)。非計上8件は rd_expenses=NULL で自然除外。
--   * no-select-star: 全列明示。
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.rd_revenue_ratio` AS
SELECT
  ticker,
  fiscal_year,
  period_type,
  revenue,
  rd_expenses,
  CASE
    WHEN revenue IS NULL OR revenue <= 0 THEN NULL
    ELSE rd_expenses / revenue * 100
  END AS rd_ratio_pct
FROM `{{PROJECT}}.raw.financials`
WHERE source = 'edinet'
  AND rd_expenses IS NOT NULL;
