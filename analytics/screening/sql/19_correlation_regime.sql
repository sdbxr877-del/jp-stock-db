-- 19_correlation_regime.sql
-- C05 相関レジーム / C06 VIX 閾値の入力
--
-- 設計 [v52 確定・ラグ版]:
--   基準カレンダー = raw.prices の ticker='1306' すなわち東証営業日。
--   マクロ9系列を基準日に INNER JOIN し、9系列すべてが揃う日のみを採用する。欠損補完はしない。
--   時差ラグ: ^N225 のみ t、他8系列は t-1。非日本の系列は東証引け後に確定するため。
--   窓長 = 60営業日。ROWS BETWEEN 59 PRECEDING AND CURRENT ROW の完全窓のみ出力する。
--
-- ラグ導入の根拠 [v52 実測]:
--   ^N225 対 ^GSPC の60日相関は同日結合で min -0.4608 / med 0.145 / max 0.572。
--   1日ラグでは min 0.0873 / med 0.5115 / max 0.7899。同日版は時差ノイズを測っていた。
--
-- 閾値の根拠 [v52 実測]:
--   ラグ版 corr_n225_gspc の分布は n=1113 / min 0.0695 / p30 0.4227 / p50 0.5073 / p70 0.5816 / max 0.783。
--   0.42 と 0.58 は p30 / p70 アンカー。データ期間が伸びたら再計測して見直すこと。
--
-- SR-1: raw.prices 直参照には下限フィルタ date >= '2021-01-01' を明示。
-- SR-2: SELECT * は使用しない。

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.correlation_regime` AS
WITH base_cal AS (
  SELECT DISTINCT date
  FROM `{{PROJECT}}.raw.prices`
  WHERE date >= '2021-01-01'
    AND ticker = '1306'
),
px AS (
  SELECT p.ticker, p.date, p.adj_close
  FROM `{{PROJECT}}.raw.prices` AS p
  INNER JOIN base_cal AS c
    ON c.date = p.date
  WHERE p.date >= '2021-01-01'
    AND p.ticker IN ('^N225','^SOX','^GSPC','^IXIC','^VIX','JPY=X','BTC-USD','HG=F','GC=F')
    AND p.adj_close IS NOT NULL
    AND p.adj_close > 0
),
full_days AS (
  SELECT date
  FROM px
  GROUP BY date
  HAVING COUNT(DISTINCT ticker) = 9
),
px9 AS (
  SELECT p.ticker, p.date, p.adj_close
  FROM px AS p
  INNER JOIN full_days AS f
    ON f.date = p.date
),
ret AS (
  SELECT
    ticker,
    date,
    LN(adj_close / LAG(adj_close) OVER (PARTITION BY ticker ORDER BY date)) AS r
  FROM px9
),
wide AS (
  SELECT
    date,
    MAX(IF(ticker = '^N225',   r, NULL)) AS r_n225,
    MAX(IF(ticker = '^GSPC',   r, NULL)) AS r_gspc,
    MAX(IF(ticker = '^SOX',    r, NULL)) AS r_sox,
    MAX(IF(ticker = '^IXIC',   r, NULL)) AS r_ixic,
    MAX(IF(ticker = '^VIX',    r, NULL)) AS r_vix,
    MAX(IF(ticker = 'JPY=X',   r, NULL)) AS r_jpy,
    MAX(IF(ticker = 'BTC-USD', r, NULL)) AS r_btc,
    MAX(IF(ticker = 'HG=F',    r, NULL)) AS r_hg,
    MAX(IF(ticker = 'GC=F',    r, NULL)) AS r_gc
  FROM ret
  GROUP BY date
),
lagged AS (
  SELECT
    date,
    r_n225,
    LAG(r_gspc) OVER (ORDER BY date) AS l_gspc,
    LAG(r_sox)  OVER (ORDER BY date) AS l_sox,
    LAG(r_ixic) OVER (ORDER BY date) AS l_ixic,
    LAG(r_vix)  OVER (ORDER BY date) AS l_vix,
    LAG(r_jpy)  OVER (ORDER BY date) AS l_jpy,
    LAG(r_btc)  OVER (ORDER BY date) AS l_btc,
    LAG(r_hg)   OVER (ORDER BY date) AS l_hg,
    LAG(r_gc)   OVER (ORDER BY date) AS l_gc
  FROM wide
),
lagged_ok AS (
  SELECT date, r_n225, l_gspc, l_sox, l_ixic, l_vix, l_jpy, l_btc, l_hg, l_gc
  FROM lagged
  WHERE r_n225 IS NOT NULL
    AND l_gspc IS NOT NULL
    AND l_sox  IS NOT NULL
    AND l_ixic IS NOT NULL
    AND l_vix  IS NOT NULL
    AND l_jpy  IS NOT NULL
    AND l_btc  IS NOT NULL
    AND l_hg   IS NOT NULL
    AND l_gc   IS NOT NULL
),
rolled AS (
  SELECT
    date,
    COUNT(1)                OVER w AS win_n,
    CORR(r_n225, l_gspc)    OVER w AS corr_n225_gspc,
    CORR(r_n225, l_sox)     OVER w AS corr_n225_sox,
    CORR(r_n225, l_jpy)     OVER w AS corr_n225_jpy,
    CORR(r_n225, l_vix)     OVER w AS corr_n225_vix,
    CORR(l_gspc, l_vix)     OVER w AS corr_gspc_vix,
    CORR(l_hg,   l_gc)      OVER w AS corr_hg_gc,
    CORR(l_btc,  l_ixic)    OVER w AS corr_btc_ixic
  FROM lagged_ok
  WINDOW w AS (ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
)
SELECT
  date,
  win_n,
  corr_n225_gspc,
  corr_n225_sox,
  corr_n225_jpy,
  corr_n225_vix,
  corr_gspc_vix,
  corr_hg_gc,
  corr_btc_ixic,
  CASE
    WHEN corr_n225_gspc IS NULL THEN NULL
    WHEN corr_n225_gspc >= 0.58 THEN 'us_sync_high'
    WHEN corr_n225_gspc >= 0.42 THEN 'us_sync_mid'
    ELSE 'us_sync_low'
  END AS regime
FROM rolled
WHERE win_n = 60
