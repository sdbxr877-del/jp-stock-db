-- C: TANKAN business-conditions DI signal (sector-level latest snapshot).
-- Source: raw.tankan_di (quarterly, Large enterprises).
-- One row per sector (mfg / nonmfg): latest actual DI, QoQ change,
-- forward change (next forecast minus latest actual), derived signal.
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.tankan_signal` AS
WITH base AS (
  SELECT
    series_code,
    data_date,
    survey_period,
    value,
    CASE
      WHEN series_code IN ('TK99F1000601GCQ01000', 'TK99F1000601GCQ11000') THEN 'mfg'
      ELSE 'nonmfg'
    END AS sector,
    CASE
      WHEN series_code IN ('TK99F1000601GCQ01000', 'TK99F2000601GCQ01000') THEN 'actual'
      ELSE 'forecast'
    END AS kind
  FROM `{{PROJECT}}.raw.tankan_di`
  WHERE data_date >= '1974-01-01'
    AND value IS NOT NULL
),
actual_ranked AS (
  SELECT
    sector,
    data_date,
    survey_period,
    value,
    ROW_NUMBER() OVER (PARTITION BY sector ORDER BY data_date DESC) AS rn
  FROM base
  WHERE kind = 'actual'
),
latest_actual AS (
  SELECT sector, data_date, survey_period, value
  FROM actual_ranked
  WHERE rn = 1
),
prev_actual AS (
  SELECT sector, value
  FROM actual_ranked
  WHERE rn = 2
),
forecast_ranked AS (
  SELECT
    sector,
    value,
    ROW_NUMBER() OVER (PARTITION BY sector ORDER BY data_date DESC) AS rn
  FROM base
  WHERE kind = 'forecast'
),
latest_forecast AS (
  SELECT sector, value
  FROM forecast_ranked
  WHERE rn = 1
)
SELECT
  la.sector,
  la.data_date AS as_of_date,
  la.survey_period,
  la.value AS di_actual,
  pa.value AS di_prev_actual,
  la.value - pa.value AS di_qoq,
  lf.value AS di_forecast_next,
  lf.value - la.value AS di_fwd_change,
  CASE
    WHEN la.value < 0 THEN 'contraction'
    WHEN lf.value - la.value < 0 THEN 'peaking'
    ELSE 'expansion'
  END AS signal,
  (la.value < 0 OR lf.value - la.value < 0) AS is_active
FROM latest_actual la
LEFT JOIN prev_actual pa USING (sector)
LEFT JOIN latest_forecast lf USING (sector)
ORDER BY la.sector;
