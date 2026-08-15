-- 34_technicals.sql
-- C17 technical indicators: TR / ATR14 (simple average) / MFI14 /
-- slow stochastic (%K, %D) / 20 day volume spike.
-- Source is fixed to yfinance on purpose: window based indicators require a
-- consistent price scale inside the lookback window, and jquants rows have
-- adj_close different from close. jquants covers only 48 frozen days
-- (2026-01-30 to 2026-05-01) and never affects recent dates.
-- ATR here is a simple 14 day mean of TR, not the Wilder recursive average.
-- The column name says so explicitly. The Wilder variant is a later step.
--
-- Flag design. row_valid and jump_flag describe the CURRENT row only, so they
-- cannot express that a window is contaminated by a bad row or a split gap
-- that happened a few days earlier. win_valid14 and win_jump14 aggregate those
-- two flags over the same 14 day window used by ATR / MFI / stochastic, so a
-- consumer can discard contaminated windows. The indicator values themselves
-- are left untouched: they are correct with respect to their input.

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.technicals` AS
WITH base AS (
  SELECT
    ticker,
    date,
    open,
    high,
    low,
    close,
    volume
  FROM `{{PROJECT}}.raw.prices`
  WHERE date >= DATE '2022-05-24'
    AND source = 'yfinance'
    AND close IS NOT NULL
    AND close > 0
),
lagged AS (
  SELECT
    ticker,
    date,
    open,
    high,
    low,
    close,
    volume,
    (high + low + close) / 3 AS tp,
    LAG(close) OVER w AS prev_close,
    LAG((high + low + close) / 3) OVER w AS prev_tp
  FROM base
  WINDOW w AS (PARTITION BY ticker ORDER BY date)
),
flow AS (
  SELECT
    ticker,
    date,
    open,
    high,
    low,
    close,
    volume,
    prev_close,
    CASE
      WHEN prev_close IS NULL THEN high - low
      ELSE GREATEST(high - low, ABS(high - prev_close), ABS(low - prev_close))
    END AS tr,
    CASE WHEN prev_tp IS NOT NULL AND tp > prev_tp THEN tp * volume ELSE 0 END AS pos_mf,
    CASE WHEN prev_tp IS NOT NULL AND tp < prev_tp THEN tp * volume ELSE 0 END AS neg_mf
  FROM lagged
),
win AS (
  SELECT
    ticker,
    date,
    open,
    high,
    low,
    close,
    volume,
    prev_close,
    tr,
    AVG(tr) OVER w14 AS atr14_sma,
    COUNT(tr) OVER w14 AS tr_n,
    SUM(pos_mf) OVER w14 AS pos_mf_14,
    SUM(neg_mf) OVER w14 AS neg_mf_14,
    MAX(high) OVER w14 AS hh14,
    MIN(low) OVER w14 AS ll14,
    AVG(volume) OVER w20 AS vol_avg20,
    COUNT(volume) OVER w20 AS vol_n20
  FROM flow
  WINDOW
    w14 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW),
    w20 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
),
kfast AS (
  SELECT
    ticker,
    date,
    open,
    high,
    low,
    close,
    volume,
    prev_close,
    tr,
    atr14_sma,
    tr_n,
    pos_mf_14,
    neg_mf_14,
    vol_avg20,
    vol_n20,
    SAFE_DIVIDE(close - ll14, NULLIF(hh14 - ll14, 0)) * 100 AS k_fast
  FROM win
),
kslow AS (
  SELECT
    ticker,
    date,
    open,
    high,
    low,
    close,
    volume,
    prev_close,
    tr,
    atr14_sma,
    tr_n,
    pos_mf_14,
    neg_mf_14,
    vol_avg20,
    vol_n20,
    AVG(k_fast) OVER w3 AS k_slow
  FROM kfast
  WINDOW w3 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
),
dslow AS (
  SELECT
    ticker,
    date,
    open,
    high,
    low,
    close,
    volume,
    prev_close,
    tr,
    atr14_sma,
    tr_n,
    pos_mf_14,
    neg_mf_14,
    vol_avg20,
    vol_n20,
    k_slow,
    AVG(k_slow) OVER w3 AS d_slow
  FROM kslow
  WINDOW w3 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
),
flagged AS (
  SELECT
    ticker,
    date,
    close,
    volume,
    tr,
    atr14_sma,
    tr_n,
    pos_mf_14,
    neg_mf_14,
    vol_avg20,
    vol_n20,
    k_slow,
    d_slow,
    COALESCE(
      high IS NOT NULL
        AND low IS NOT NULL
        AND open IS NOT NULL
        AND high >= low
        AND close <= high
        AND close >= low
        AND open <= high
        AND open >= low,
      FALSE
    ) AS row_valid,
    COALESCE(
      SAFE_DIVIDE(close, NULLIF(prev_close, 0)) >= 1.9
        OR SAFE_DIVIDE(close, NULLIF(prev_close, 0)) <= 0.55,
      FALSE
    ) AS jump_flag
  FROM dslow
),
windowed AS (
  SELECT
    ticker,
    date,
    close,
    volume,
    tr,
    atr14_sma,
    tr_n,
    pos_mf_14,
    neg_mf_14,
    vol_avg20,
    vol_n20,
    k_slow,
    d_slow,
    row_valid,
    jump_flag,
    COUNTIF(NOT row_valid) OVER w14 = 0 AS win_valid14,
    COUNTIF(jump_flag) OVER w14 > 0 AS win_jump14
  FROM flagged
  WINDOW w14 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)
)
SELECT
  ticker,
  date,
  ROUND(tr, 6) AS tr,
  ROUND(atr14_sma, 6) AS atr14_sma,
  ROUND(SAFE_DIVIDE(atr14_sma, close) * 100, 6) AS atr14_pct,
  ROUND(
    CASE
      WHEN neg_mf_14 = 0 AND pos_mf_14 > 0 THEN 100.0
      WHEN neg_mf_14 = 0 AND pos_mf_14 = 0 THEN NULL
      ELSE 100 - SAFE_DIVIDE(100, 1 + SAFE_DIVIDE(pos_mf_14, neg_mf_14))
    END,
    6
  ) AS mfi14,
  ROUND(k_slow, 6) AS stoch_k_slow,
  ROUND(d_slow, 6) AS stoch_d,
  ROUND(SAFE_DIVIDE(volume, NULLIF(vol_avg20, 0)), 6) AS vol_spike20,
  row_valid,
  jump_flag,
  win_valid14,
  win_jump14
FROM windowed
WHERE vol_n20 = 20
  AND tr_n = 14
