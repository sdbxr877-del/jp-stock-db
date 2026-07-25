-- Macro signal panel: latest snapshot of each macro signal, unified.
-- Sources: adr_threshold_flags (breadth), bull_steepening (yield_curve),
-- fred_threshold_flags (credit / liquidity), tankan_signal (sentiment).
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.macro_signals` AS
WITH adr_latest AS (
  SELECT date AS as_of_date, adr_signal, adr_25d
  FROM (
    SELECT
      date, adr_signal, adr_25d,
      ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
    FROM `{{PROJECT}}.analytics.adr_threshold_flags`
    WHERE adr_signal IS NOT NULL
  )
  WHERE rn = 1
),
bull_latest AS (
  SELECT data_date AS as_of_date, is_bull_steepening, delta_y2
  FROM (
    SELECT
      data_date, is_bull_steepening, delta_y2,
      ROW_NUMBER() OVER (ORDER BY data_date DESC) AS rn
    FROM `{{PROJECT}}.analytics.bull_steepening`
    WHERE is_bull_steepening IS NOT NULL
  )
  WHERE rn = 1
),
fred_latest AS (
  SELECT indicator_code, data_date AS as_of_date, signal, value
  FROM `{{PROJECT}}.analytics.fred_threshold_flags`
  WHERE signal IS NOT NULL
),
tankan_latest AS (
  SELECT sector, as_of_date, signal, di_actual, is_active
  FROM `{{PROJECT}}.analytics.tankan_signal`
),
unified AS (
  -- breadth
  SELECT
    'adr_25d'   AS signal_key,
    'breadth'   AS category,
    as_of_date,
    adr_signal  AS signal,
    adr_25d     AS metric_value,
    (adr_signal <> 'neutral') AS is_active
  FROM adr_latest

  UNION ALL

  -- yield_curve
  SELECT
    'bull_steepening' AS signal_key,
    'yield_curve'     AS category,
    as_of_date,
    CASE WHEN is_bull_steepening THEN 'active' ELSE 'inactive' END AS signal,
    delta_y2          AS metric_value,
    is_bull_steepening AS is_active
  FROM bull_latest

  UNION ALL

  -- credit (HY) / liquidity (NFCI)
  SELECT
    CASE indicator_code
      WHEN 'BAMLH0A0HYM2' THEN 'credit_hy'
      WHEN 'NFCI'         THEN 'liquidity_nfci'
      ELSE LOWER(indicator_code)
    END AS signal_key,
    CASE indicator_code
      WHEN 'BAMLH0A0HYM2' THEN 'credit'
      WHEN 'NFCI'         THEN 'liquidity'
      ELSE 'macro'
    END AS category,
    as_of_date,
    signal,
    value AS metric_value,
    (signal <> 'calm') AS is_active
  FROM fred_latest

  UNION ALL

  -- sentiment (TANKAN DI)
  SELECT
    CONCAT('tankan_', sector) AS signal_key,
    'sentiment'               AS category,
    as_of_date,
    signal,
    di_actual                 AS metric_value,
    is_active
  FROM tankan_latest
)
SELECT
  signal_key,
  category,
  as_of_date,
  signal,
  metric_value,
  is_active
FROM unified
ORDER BY category, signal_key;
