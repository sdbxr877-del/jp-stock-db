-- 07_advance_decline_ratio.sql — 騰落レシオ25日(全市場・VIEW・MVP v1)
--
-- 由来: phase45 A21 / C01
--   騰落レシオ25日 = 25日合計(上昇銘柄数) / 25日合計(下落銘柄数) × 100
--
-- 設計方針:
--   * VIEW(常に raw.prices を参照。J-Quants 前線前進に自動追従)
--   * 上昇/下落判定は adj_close 前日比(分割・配当の不連続を回避)
--   * source 統合: 各 date で J-Quants(補正済)を優先、無ければ yfinance を採用
--     - 二重計上回避のため source ごとに breadth を算出してから date 単位で1ソース選択
--     - 前日比 LAG は同一 source 系列内で取る(境界日の符号混在を回避)
--     - 一部銘柄欠損日も「その date の J-Quants 全体」を採用(個別 yfinance 補填はしない)
--   * 25日未満の先頭期間は adr_25d=NULL(不完全値を出さない)
--   * 分母(下落数)ゼロは SAFE_DIVIDE でガード
--   * partition-filter-required: WHERE date >= '2000-01-01' で充足(全履歴を含む下限)
--   * no-select-star: 全列明示
--
-- 注: flat(前日比=0)は分母分子いずれにも算入しない。
--     上場初日等で前日比が NULL の行は dir IS NULL として除外。

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.advance_decline_ratio` AS
WITH px AS (
  SELECT source, ticker, date, adj_close
  FROM `{{PROJECT}}.raw.prices`
  WHERE date >= DATE '2000-01-01'
    AND source IN ('yfinance', 'jquants')
    AND adj_close IS NOT NULL
),
chg AS (
  SELECT
    source, date,
    SIGN(adj_close - LAG(adj_close) OVER (PARTITION BY source, ticker ORDER BY date)) AS dir
  FROM px
),
breadth_src AS (
  SELECT
    source, date,
    COUNTIF(dir > 0) AS advances,
    COUNTIF(dir < 0) AS declines,
    COUNTIF(dir = 0) AS flats
  FROM chg
  WHERE dir IS NOT NULL
  GROUP BY source, date
),
breadth AS (
  SELECT date, advances, declines, flats
  FROM (
    SELECT
      date, advances, declines, flats,
      ROW_NUMBER() OVER (
        PARTITION BY date
        ORDER BY CASE source WHEN 'jquants' THEN 0 ELSE 1 END
      ) AS rn
    FROM breadth_src
  )
  WHERE rn = 1
),
rolling AS (
  SELECT
    date, advances, declines, flats,
    COUNT(*)      OVER w AS win_n,
    SUM(advances) OVER w AS sum_adv_25d,
    SUM(declines) OVER w AS sum_dec_25d
  FROM breadth
  WINDOW w AS (ORDER BY date ROWS BETWEEN 24 PRECEDING AND CURRENT ROW)
)
SELECT
  date,
  advances,
  declines,
  flats,
  CASE
    WHEN win_n < 25 THEN NULL
    ELSE ROUND(SAFE_DIVIDE(sum_adv_25d, sum_dec_25d) * 100, 2)
  END AS adr_25d
FROM rolling;
