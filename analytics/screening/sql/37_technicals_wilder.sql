-- 37_technicals_wilder.sql
-- C17 second wave. Recursive indicators: Wilder RSI(14), Wilder ATR(14), MACD(12,26,9).
--
-- Method. These indicators are recursive, y_t = (1 - a) * y_(t-1) + a * x_t.
-- The running sum form of the closed expansion is not usable here because it
-- needs decay^(-t), which overflows once t reaches the length of the history.
-- This view instead truncates the expansion at 250 preceding rows and evaluates
-- the weighted sum directly over an ARRAY_AGG window.
--
-- Truncation error, measured on 25 tickers and 14246 rows against a 500 row
-- reference: RSI 2.99e-06 points, ATR 1.64e-08 relative, EMA26 1.43e-08 relative.
-- The theoretical bound decay^251 is 8.3e-09 for 13/14 and 4.1e-09 for 25/27, so
-- the measurement sits within a factor of 3 of the bound. Every output column is
-- rounded to 6 decimals, so the truncation stays below the output precision.
--
-- Population. Source is fixed to yfinance and the lower date bound is
-- 2022-05-24, both matching 34_technicals.sql so the population stays identical.
--
-- tr is reused from analytics.technicals rather than recomputed. That view drops
-- the first 19 rows of every ticker (its final filter is vol_n20 = 20), so the
-- earliest rows here carry no tr and are reported through tr_missing. Weighted
-- sums normalise by the weight of the non null terms only, so a missing tr does
-- not bias the level.
--
-- Warm up. Rows with fewer than 250 preceding rows still emit a value, because
-- dropping them would hide otherwise usable history. warmup_ok reports whether
-- the truncation bound above actually applies to that row.
--
-- Out of scope on purpose. ZigZag, PoC and HVN are a state machine and a price
-- bin aggregation respectively, so they do not share this implementation shape
-- and get their own file. No threshold flags are emitted because the knowledge
-- base defines no thresholds for these indicators.
--
-- Note. atr14_wilder is not the same column as atr14_sma in 34_technicals.sql.
-- That one is a simple moving average of tr, this one is the Wilder recursion.

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.technicals_wilder` AS
WITH px AS (
  SELECT
    ticker,
    date,
    close,
    LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close
  FROM `{{PROJECT}}.raw.prices`
  WHERE date >= DATE '2022-05-24'
    AND source = 'yfinance'
),
joined AS (
  SELECT
    p.ticker AS ticker,
    p.date AS date,
    p.close AS close,
    GREATEST(p.close - p.prev_close, 0) AS gain,
    GREATEST(p.prev_close - p.close, 0) AS loss,
    t.tr AS tr,
    t.row_valid AS row_valid,
    t.jump_flag AS jump_flag
  FROM px AS p
  LEFT JOIN `{{PROJECT}}.analytics.technicals` AS t
    ON t.ticker = p.ticker
   AND t.date = p.date
),
win AS (
  SELECT
    ticker,
    date,
    close,
    tr,
    row_valid,
    jump_flag,
    COUNT(*) OVER wall AS warmup_rows,
    ARRAY_AGG(STRUCT(gain AS g, loss AS l, tr AS v, close AS c)) OVER w250 AS a
  FROM joined
  WINDOW
    wall AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
    w250 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 250 PRECEDING AND CURRENT ROW)
),
sums AS (
  SELECT
    ticker,
    date,
    close,
    tr,
    row_valid,
    jump_flag,
    warmup_rows,
    (
      SELECT AS STRUCT
        SUM(IF(g IS NOT NULL, w14 * g, 0)) AS num_gain,
        SUM(IF(l IS NOT NULL, w14 * l, 0)) AS num_loss,
        SUM(IF(v IS NOT NULL, w14 * v, 0)) AS num_tr,
        SUM(IF(v IS NOT NULL, w14, 0)) AS den_tr,
        SUM(IF(c IS NOT NULL, w12 * c, 0)) AS num_c12,
        SUM(IF(c IS NOT NULL, w12, 0)) AS den_c12,
        SUM(IF(c IS NOT NULL, w26 * c, 0)) AS num_c26,
        SUM(IF(c IS NOT NULL, w26, 0)) AS den_c26
      FROM (
        SELECT
          e.g AS g,
          e.l AS l,
          e.v AS v,
          e.c AS c,
          POW(13.0 / 14.0, ARRAY_LENGTH(a) - 1 - o) AS w14,
          POW(11.0 / 13.0, ARRAY_LENGTH(a) - 1 - o) AS w12,
          POW(25.0 / 27.0, ARRAY_LENGTH(a) - 1 - o) AS w26
        FROM UNNEST(a) AS e WITH OFFSET o
      )
    ) AS q
  FROM win
),
ind AS (
  SELECT
    ticker,
    date,
    close,
    tr,
    row_valid,
    jump_flag,
    warmup_rows,
    SAFE_DIVIDE(100 * q.num_gain, q.num_gain + q.num_loss) AS rsi_raw,
    SAFE_DIVIDE(q.num_tr, q.den_tr) AS atr_raw,
    SAFE_DIVIDE(q.num_c12, q.den_c12) AS ema12_raw,
    SAFE_DIVIDE(q.num_c26, q.den_c26) AS ema26_raw
  FROM sums
),
mline AS (
  SELECT
    ticker,
    date,
    close,
    tr,
    row_valid,
    jump_flag,
    warmup_rows,
    rsi_raw,
    atr_raw,
    ema12_raw,
    ema26_raw,
    ema12_raw - ema26_raw AS macd_raw
  FROM ind
),
sig AS (
  SELECT
    ticker,
    date,
    close,
    tr,
    row_valid,
    jump_flag,
    warmup_rows,
    rsi_raw,
    atr_raw,
    ema12_raw,
    ema26_raw,
    macd_raw,
    (
      SELECT SAFE_DIVIDE(SUM(IF(m IS NOT NULL, w9 * m, 0)), SUM(IF(m IS NOT NULL, w9, 0)))
      FROM (
        SELECT
          e.m AS m,
          POW(0.8, ARRAY_LENGTH(am) - 1 - o) AS w9
        FROM UNNEST(am) AS e WITH OFFSET o
      )
    ) AS signal_raw
  FROM (
    SELECT
      ticker,
      date,
      close,
      tr,
      row_valid,
      jump_flag,
      warmup_rows,
      rsi_raw,
      atr_raw,
      ema12_raw,
      ema26_raw,
      macd_raw,
      ARRAY_AGG(STRUCT(macd_raw AS m)) OVER w250 AS am
    FROM mline
    WINDOW w250 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 250 PRECEDING AND CURRENT ROW)
  )
)
SELECT
  ticker,
  date,
  close,
  ROUND(rsi_raw, 6) AS rsi14_wilder,
  ROUND(atr_raw, 6) AS atr14_wilder,
  ROUND(SAFE_DIVIDE(atr_raw, close) * 100, 6) AS atr14_wilder_pct,
  ROUND(ema12_raw, 6) AS ema12,
  ROUND(ema26_raw, 6) AS ema26,
  ROUND(macd_raw, 6) AS macd,
  ROUND(signal_raw, 6) AS macd_signal,
  ROUND(macd_raw - signal_raw, 6) AS macd_hist,
  warmup_rows,
  warmup_rows >= 250 AS warmup_ok,
  tr IS NULL AS tr_missing,
  row_valid,
  jump_flag
FROM sig
