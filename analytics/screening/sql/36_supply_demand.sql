-- 36_supply_demand.sql
-- Snapshot of supply and demand signals, one row per ticker (latest traded day).
--
-- Scope decided in db_v81:
--   IN  C16 InstitutionFlow = turnover / market cap.
--   OUT C16 ShortRatioGap. Margin balance (JPX weekly / JSF daily) is not in
--       raw. All 18 raw tables were enumerated and none holds it.
--   OUT C09 Q and M scores. The inventory states "100 points / 10 points,
--       dynamic weights" but no point allocation exists in any SSOT document.
--       Do not invent one here.
--
-- Every input is reused as-is. Nothing is recomputed:
--   analytics.daily_metrics.turnover_20d = AVG(close * volume) over
--     RANGE BETWEEN 28 PRECEDING AND CURRENT ROW, i.e. a 29 CALENDAR DAY
--     window despite the "20d" name.
--   analytics.daily_metrics.vol_20d = STDDEV_SAMP(ret_1d) over that same
--     calendar window. It is return volatility, not average volume.
--   analytics.technicals.vol_spike20 = volume / AVG(volume) over
--     ROWS BETWEEN 19 PRECEDING AND CURRENT ROW, i.e. a 20 TRADING DAY window.
--   The two window kinds differ. Callers must not treat them as aligned.
--
-- raw.prices has no turnover column (10 columns, verified), so turnover_1d is
-- close * volume rather than a reported value.
--
-- Coverage: market_cap is NULL for 26.7% of capital_metrics rows because
-- raw.fins_summary.shares_out_fy is absent for 828 tickers and no fallback
-- column exists. Such rows are kept and flagged (mcap_missing, fin_missing)
-- rather than dropped, and institution_flow stays NULL through SAFE_DIVIDE.
-- If share counts are later backfilled from EDINET this view widens with no
-- change to the SQL.
--
-- Grain note: capital_metrics is a per-ticker snapshot with no date column, so
-- market_cap has no time series. A daily InstitutionFlow would require an
-- as-of join on fins_summary.disc_date to avoid look-ahead bias. That is
-- deferred to the backtest work, not approximated here.

CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.supply_demand` AS
WITH bounds AS (
  SELECT MAX(date) AS max_px_date
  FROM `{{PROJECT}}.analytics.daily_metrics`
  WHERE date >= DATE '2000-01-01'
),

latest_px AS (
  SELECT
    ticker,
    date,
    close,
    volume,
    turnover_20d,
    vol_20d
  FROM `{{PROJECT}}.analytics.daily_metrics`
  WHERE date >= DATE '2000-01-01'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) = 1
),

tech AS (
  SELECT
    ticker,
    date,
    vol_spike20,
    win_valid14,
    win_jump14
  FROM `{{PROJECT}}.analytics.technicals`
  WHERE date >= DATE '2000-01-01'
),

fin AS (
  SELECT
    ticker,
    market_cap,
    shares_outstanding
  FROM `{{PROJECT}}.analytics.capital_metrics`
)

SELECT
  p.ticker,
  p.date AS px_date,
  DATE_DIFF(b.max_px_date, p.date, DAY) AS days_stale,
  DATE_DIFF(b.max_px_date, p.date, DAY) > 0 AS is_stale,
  p.close,
  p.volume,
  p.close * p.volume AS turnover_1d,
  p.turnover_20d,
  p.vol_20d,
  t.vol_spike20,
  t.vol_spike20 IS NULL AS vol_spike_missing,
  t.win_valid14,
  t.win_jump14,
  f.market_cap,
  f.shares_outstanding,
  f.market_cap IS NULL AS mcap_missing,
  f.ticker IS NULL AS fin_missing,
  SAFE_DIVIDE(p.turnover_20d, f.market_cap) AS institution_flow_20d,
  SAFE_DIVIDE(p.close * p.volume, f.market_cap) AS institution_flow_1d
FROM latest_px AS p
CROSS JOIN bounds AS b
LEFT JOIN tech AS t
  ON t.ticker = p.ticker
 AND t.date = p.date
LEFT JOIN fin AS f
  ON f.ticker = p.ticker
