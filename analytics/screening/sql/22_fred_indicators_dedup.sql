-- 22_fred_indicators_dedup.sql - full dedup series for raw.fred_indicators (C03 input)
-- Keeps one row per (indicator_code, data_date) with the largest updated_at.
-- Unlike fred_indicators_latest (single most-recent point), this is the full series
-- required by C03 central-bank asset momentum. no-select-star / SR-1 lower-bound filter.
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.fred_indicators_dedup` AS
WITH ranked AS (
  SELECT
    indicator_code,
    indicator_name,
    data_date,
    value,
    updated_at,
    ROW_NUMBER() OVER (
      PARTITION BY indicator_code, data_date
      ORDER BY updated_at DESC
    ) AS rn
  FROM `{{PROJECT}}.raw.fred_indicators`
  WHERE data_date >= '1900-01-01'
)
SELECT
  indicator_code,
  indicator_name,
  data_date,
  value,
  updated_at
FROM ranked
WHERE rn = 1;
