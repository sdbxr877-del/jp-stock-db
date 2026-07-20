-- 17_rd_revenue_ratio_latest.sql — EDINET R&D費/売上高比率 銘柄別最新期(VIEW・MVP v1)
--
-- 由来: 16_rd_revenue_ratio の後段。ticker×fiscal_year 粒度の比率系列を
--       「銘柄ごと最新1期」に正規化し、UI 一覧・銘柄横断比較の前段とする。
--
-- 設計方針:
--   * 入力は analytics.rd_revenue_ratio のみを直参照(新規データ源ゼロ・単一責任派生)。
--     raw.financials は再参照しない(16 が SSOT。母集団条件の二重定義を避ける)。
--   * fiscal_year は文字列 'YY/M' / 'YY/MM' の2書式(実測: len4=60件 / len5=11件・区切りは '/' 単一)。
--     辞書順ソートは '21/12' < '21/3' となり誤るため、SPLIT で年・月を数値化した
--     fy_key = 年*100 + 月 で降順ソートする。
--   * rd_ratio_pct IS NOT NULL を先に適用してから最新1期を選ぶ。
--     比率不定(revenue NULL / <=0)の期を最新値として出さない(07/14/15/16 と同流儀)。
--   * ROUND(rd_ratio_pct, 4): 本VIEWは表示前段のため桁を揃える。16 の生値は無改変で保持。
--   * 同一 ticker に同一 fy_key が並ぶ可能性は 16 の母集団(ticker×fiscal_year 一意)により無い。
--   * no-select-star: 全列明示。入力が VIEW のため本VIEWでの partition 下限は不要。
--
-- 期待値(v50 時点の実測前提): 13行 / ticker 重複ゼロ。
--
-- 列: ticker / fiscal_year / period_type / revenue / rd_expenses / rd_ratio_pct
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.rd_revenue_ratio_latest` AS
WITH keyed AS (
  SELECT
    ticker,
    fiscal_year,
    period_type,
    revenue,
    rd_expenses,
    rd_ratio_pct,
    CAST(SPLIT(fiscal_year, '/')[OFFSET(0)] AS INT64) * 100
      + CAST(SPLIT(fiscal_year, '/')[OFFSET(1)] AS INT64) AS fy_key
  FROM `{{PROJECT}}.analytics.rd_revenue_ratio`
  WHERE rd_ratio_pct IS NOT NULL
),
ranked AS (
  SELECT
    ticker,
    fiscal_year,
    period_type,
    revenue,
    rd_expenses,
    rd_ratio_pct,
    fy_key,
    ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY fy_key DESC) AS rn
  FROM keyed
)
SELECT
  ticker,
  fiscal_year,
  period_type,
  revenue,
  rd_expenses,
  ROUND(rd_ratio_pct, 4) AS rd_ratio_pct
FROM ranked
WHERE rn = 1;
