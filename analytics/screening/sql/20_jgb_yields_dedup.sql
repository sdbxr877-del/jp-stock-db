-- 20_jgb_yields_dedup.sql -- JGB yields (all tenors) de-duplicated view
--
-- Source: MOF jgbcm daily yields ingested into raw.jgb_yields.
--   The current-month file is re-fetched daily, so (data_date, tenor) can be
--   appended multiple times. Keep only the row with the latest updated_at.
-- Design:
--   * Unlike FRED _latest (single most-recent point), this returns the full
--     de-duplicated time series, because C04 (real rate / yield spread) needs
--     the daily 10Y series.
--   * Dedup: one row per (data_date, tenor) by max updated_at.
--   * no-select-star: explicit columns (SR-2).
--   * jgb_yields is month-partitioned; SR-1 style explicit data_date lower bound.
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.jgb_yields_dedup` AS
WITH ranked AS (
  SELECT
    data_date, tenor, value, updated_at,
    ROW_NUMBER() OVER (
      PARTITION BY data_date, tenor
      ORDER BY updated_at DESC
    ) AS rn
  FROM `{{PROJECT}}.raw.jgb_yields`
  WHERE data_date >= DATE '1974-01-01'
)
SELECT
  data_date,
  tenor,
  value,
  updated_at
FROM ranked
WHERE rn = 1;
