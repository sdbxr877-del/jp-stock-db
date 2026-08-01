-- 01_daily_metrics.sql - idempotent single-day update for @target_date (v70)
--
-- Design:
--   * MERGE is avoided: WHEN NOT MATCHED INSERT blocks partition pruning
--     -> BEGIN TRANSACTION / DELETE / INSERT / COMMIT
--   * partition-filter-required: explicit date range on raw.prices, date= on daily_metrics
--   * no-select-star: every column is listed explicitly
--   * trend / return / 52w / volatility use adj_close, normalised in the base CTE
--     to drop the jquants retroactive adjustment (see the v71 note below);
--     turnover uses the actual traded price close
--   * lookback of 400 calendar days covers the widest window (378 days)
--
-- v70 change: every window is date-based (RANGE over UNIX_DATE(date)) instead of
--   row-based (ROWS n PRECEDING / LAG n). Row-based windows shift whenever rows are
--   inserted into or deleted from history, so past values were not reproducible.
--   Calendar offsets below were measured on 2026-07-31 over 4,169 tickers
--   (median calendar gap; p10 = p50 = p90 because TSE shares one calendar):
--     LAG  21 -> 30 days     LAG  63 -> 94 days     LAG 126 -> 186 days
--     ROWS 19 -> 28 days     ROWS 24 -> 35 days     ROWS  74 -> 109 days
--     ROWS 199 -> 298 days   ROWS 251 -> 378 days
--   ret_1d keeps LAG(1): "previous trading day" is row-based by definition.
--
-- v71 change: adj_close is normalised in the base CTE. raw.prices holds two
--   sources whose adj_close definitions differ. jquants rows carry a retroactive
--   split and dividend adjustment (2,331 of 202,852 rows), while yfinance rows
--   store the traded price unchanged (853,716 rows, adj_close = close with zero
--   exceptions). Reading the column as-is made the series discontinuous by up to
--   50x on the 88 affected tickers, because the source alternates day by day.
--   Measured on 2026-07-31 over 2025-08-01..2026-07-31: ret_1m > 10 falls from
--   73 rows / 6 tickers to 36 rows / 5 tickers. The remaining tickers are truly
--   unadjusted splits and are handled separately.
--
-- v72 change: isolated zero-volume price spikes are dropped in the clean CTE.
--   A row is dropped when volume = 0 and its close differs by more than 10x from
--   both the previous and the next traded close. Measured on 2026-07-31 over
--   2025-08-01..2026-07-31: 6 rows (1326 x 5, 1349 x 1) leave the window inputs
--   and ret_1m > 10 falls from 36 rows / 5 tickers to 29 rows / 3 tickers.
--   Requiring both sides keeps genuine split regimes intact, because those have a
--   traded price on one side only (7176 and 7691 are zero-volume for 53 and 51
--   consecutive rows yet must be preserved). The spike row itself still enters
--   daily_metrics on its own target_date, because next_traded is unknown then.
--
-- v73 change: the jquants fallback is decided per ticker in the new pk CTE.
--   raw.prices holds two sources and either column can be the broken one.
--   Measured on 2026-07-31 over 2025-08-01..2026-07-31: of the 4,326 tickers that
--   have at least one source boundary, 75 have a close that jumps at the boundary
--   while adj_close stays flat, and 12 have the opposite. The previous uniform
--   rule (always take close for jquants rows) was correct for the latter group
--   only, so the former carried a 2x to 10x sawtooth through every window.
--   pk counts how often each column deviates by more than 2x across source
--   boundaries and keeps the quieter one. 'close' is the default, so a ticker with
--   no boundary behaves exactly as it did in v71. The test is a sign comparison,
--   not a magnitude, so a shorter 400-day window that drops some boundaries does
--   not flip the result. Effect: ret_1m > 1 falls from 2,725 to 1,425 rows and
--   ret_1m > 10 from 29 rows / 3 tickers to 28 rows / 2 tickers (6731 resolved).
--   14 tickers deviate on both columns; 12 of them on 1 to 3 boundaries, which is
--   a real split landing on a boundary day and is unaffected by the choice. The
--   other two (3612, 8273) hold a stale yfinance price at a 2x and 3x offset and
--   need a re-fetch instead; pk cannot repair them.
--
-- Note: this is a script (DECLARE / BEGIN TRANSACTION). A dry-run may report scan=0.
--       The real cost is the raw.prices date-range read for the window functions.
DECLARE target_date DATE DEFAULT @target_date;
BEGIN TRANSACTION;
DELETE FROM `{{PROJECT}}.analytics.daily_metrics`
WHERE date = target_date;
INSERT INTO `{{PROJECT}}.analytics.daily_metrics`
( ticker, date, close, adj_close, volume,
  sma25, sma75, sma200,
  ret_1m, ret_3m, ret_6m,
  high_52w, low_52w, pct_from_52w_high,
  turnover_20d, vol_20d, computed_at )
WITH bd AS (
  -- Adjacent-row view used only to locate source boundaries. Same 400-day range
  -- as base so the two CTEs never disagree about which rows exist.
  SELECT
    p.ticker, p.source, p.close, p.adj_close,
    LAG(p.source)    OVER (PARTITION BY p.ticker ORDER BY p.date) AS ps,
    LAG(p.close)     OVER (PARTITION BY p.ticker ORDER BY p.date) AS pc,
    LAG(p.adj_close) OVER (PARTITION BY p.ticker ORDER BY p.date) AS pa
  FROM `{{PROJECT}}.raw.prices` p
  WHERE p.date BETWEEN DATE_SUB(target_date, INTERVAL 400 DAY) AND target_date
),
pk AS (
  -- Ratios are oriented jquants / yfinance on every boundary, so a healthy column
  -- sits near 1.0 regardless of which side comes first. The column with fewer
  -- deviations wins; ties go to 'adj' because yfinance rows satisfy
  -- adj_close = close and are therefore unaffected either way.
  SELECT
    ticker,
    IF(COUNTIF(ra > 2 OR ra < 0.5) <= COUNTIF(rc > 2 OR rc < 0.5), 'adj', 'close') AS pick
  FROM (
    SELECT
      ticker,
      IF(source = 'jquants', SAFE_DIVIDE(close, pc), SAFE_DIVIDE(pc, close)) AS rc,
      IF(source = 'jquants', SAFE_DIVIDE(adj_close, pa), SAFE_DIVIDE(pa, adj_close)) AS ra
    FROM bd
    WHERE ps IS NOT NULL AND ps <> source
  )
  GROUP BY ticker
),
base AS (
  -- Universe guard: exclude macro series (market='INDEX') and keep single stocks only.
  -- Macro series carry values on weekends and holidays. If they are mixed in, MAX(date)
  -- in 03 moves to a TSE holiday and screening_candidates becomes empty.
  -- Macro series are read directly from raw.prices on the C05 / C06 side.
  SELECT
    p.ticker, p.date, p.close,
    -- Per-ticker fallback: pk decides which column survives the source boundary.
    -- yfinance rows already satisfy adj_close = close, so this only ever changes
    -- jquants rows. A ticker absent from pk falls back to 'close', which is the
    -- v71 behaviour.
    IF(p.source = 'jquants' AND IFNULL(k.pick, 'close') = 'close', p.close, p.adj_close) AS adj_close,
    p.volume
  FROM `{{PROJECT}}.raw.prices` p
  LEFT JOIN pk k ON k.ticker = p.ticker
  WHERE p.date BETWEEN DATE_SUB(target_date, INTERVAL 400 DAY) AND target_date
    AND NOT EXISTS (
      SELECT 1
      FROM `{{PROJECT}}.raw.tickers` t
      WHERE t.ticker = p.ticker
        AND t.market = 'INDEX'
    )
),
flag AS (
  -- Locate the nearest traded close on each side. IF(volume > 0, ...) makes the
  -- window skip non-traded days, so a run of zero-volume rows is bridged.
  SELECT
    ticker, date, close, adj_close, volume,
    LAST_VALUE(IF(volume > 0, close, NULL) IGNORE NULLS) OVER (
      PARTITION BY ticker ORDER BY UNIX_DATE(date)
      RANGE BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_traded,
    FIRST_VALUE(IF(volume > 0, close, NULL) IGNORE NULLS) OVER (
      PARTITION BY ticker ORDER BY UNIX_DATE(date)
      RANGE BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) AS next_traded
  FROM base
),
clean AS (
  -- COALESCE keeps the 22 rows whose close is NULL: NOT of a NULL predicate
  -- would otherwise drop them silently.
  SELECT ticker, date, close, adj_close, volume
  FROM flag
  WHERE NOT COALESCE(
    volume = 0
    AND prev_traded IS NOT NULL
    AND next_traded IS NOT NULL
    AND (SAFE_DIVIDE(close, prev_traded) < 0.1 OR SAFE_DIVIDE(close, prev_traded) > 10)
    AND (SAFE_DIVIDE(close, next_traded) < 0.1 OR SAFE_DIVIDE(close, next_traded) > 10),
    FALSE)
),
with_ret AS (
  SELECT
    ticker, date, close, adj_close, volume,
    UNIX_DATE(date) AS dnum,
    SAFE_DIVIDE(adj_close, LAG(adj_close) OVER (PARTITION BY ticker ORDER BY date)) - 1 AS ret_1d
  FROM clean
),
calc AS (
  SELECT
    ticker, date, close, adj_close, volume,
    AVG(adj_close) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN  35 PRECEDING AND CURRENT ROW) AS sma25,
    AVG(adj_close) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN 109 PRECEDING AND CURRENT ROW) AS sma75,
    AVG(adj_close) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN 298 PRECEDING AND CURRENT ROW) AS sma200,
    SAFE_DIVIDE(adj_close, LAST_VALUE(adj_close IGNORE NULLS) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN UNBOUNDED PRECEDING AND  30 PRECEDING)) - 1 AS ret_1m,
    SAFE_DIVIDE(adj_close, LAST_VALUE(adj_close IGNORE NULLS) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN UNBOUNDED PRECEDING AND  94 PRECEDING)) - 1 AS ret_3m,
    SAFE_DIVIDE(adj_close, LAST_VALUE(adj_close IGNORE NULLS) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN UNBOUNDED PRECEDING AND 186 PRECEDING)) - 1 AS ret_6m,
    MAX(adj_close)      OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN 378 PRECEDING AND CURRENT ROW) AS high_52w,
    MIN(adj_close)      OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN 378 PRECEDING AND CURRENT ROW) AS low_52w,
    AVG(close * volume) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN  28 PRECEDING AND CURRENT ROW) AS turnover_20d,
    STDDEV_SAMP(ret_1d) OVER (PARTITION BY ticker ORDER BY dnum RANGE BETWEEN  28 PRECEDING AND CURRENT ROW) AS vol_20d
  FROM with_ret
)
SELECT
  ticker, date, close, adj_close, volume,
  sma25, sma75, sma200,
  ret_1m, ret_3m, ret_6m,
  high_52w, low_52w,
  SAFE_DIVIDE(adj_close, NULLIF(high_52w, 0)) - 1 AS pct_from_52w_high,
  turnover_20d, vol_20d,
  CURRENT_TIMESTAMP() AS computed_at
FROM calc
WHERE date = target_date;
COMMIT TRANSACTION;
