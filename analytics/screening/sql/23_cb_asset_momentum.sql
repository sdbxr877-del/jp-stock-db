-- 23_cb_asset_momentum.sql - central-bank balance-sheet momentum in USD (C03)
-- Combined Fed(WALCL) + ECB(ECBASSETSW) + BOJ(JPNASSETS) total assets, all in millions USD,
-- on a weekly spine with as-of forward-fill, then 12-week MA and its 12-week percent change.
-- Units: WALCL = millions USD; ECBASSETSW = millions EUR (x USD/EUR);
--        JPNASSETS = hundred-millions JPY (x100 -> millions JPY, / JPY-per-USD -> millions USD).
-- FX (DEXJPUS/DEXUSEU) backfilled from 2015-11-20, so the series starts there.
-- no-select-star / SR-1 lower-bound filter. Inputs come from analytics.fred_indicators_dedup.
CREATE OR REPLACE VIEW `{{PROJECT}}.analytics.cb_asset_momentum` AS
WITH params AS (
  SELECT DATE '2015-11-20' AS start_date
),
spine AS (
  SELECT wk AS week_date
  FROM params,
  UNNEST(GENERATE_DATE_ARRAY((SELECT start_date FROM params), CURRENT_DATE(), INTERVAL 7 DAY)) AS wk
),
src AS (
  SELECT indicator_code, data_date, value
  FROM `{{PROJECT}}.analytics.fred_indicators_dedup`
  WHERE data_date >= '1900-01-01'
    AND indicator_code IN ('WALCL', 'ECBASSETSW', 'JPNASSETS', 'DEXJPUS', 'DEXUSEU')
),
iv AS (
  SELECT
    indicator_code,
    value,
    data_date AS valid_from,
    LEAD(data_date) OVER (PARTITION BY indicator_code ORDER BY data_date) AS valid_to
  FROM src
),
asof AS (
  SELECT s.week_date, i.indicator_code, i.value
  FROM spine s
  JOIN iv i
    ON s.week_date >= i.valid_from
   AND (i.valid_to IS NULL OR s.week_date < i.valid_to)
),
pivoted AS (
  SELECT
    week_date,
    MAX(IF(indicator_code = 'WALCL', value, NULL)) AS walcl,
    MAX(IF(indicator_code = 'ECBASSETSW', value, NULL)) AS ecb_eur,
    MAX(IF(indicator_code = 'JPNASSETS', value, NULL)) AS boj_100m_jpy,
    MAX(IF(indicator_code = 'DEXJPUS', value, NULL)) AS jpy_per_usd,
    MAX(IF(indicator_code = 'DEXUSEU', value, NULL)) AS usd_per_eur
  FROM asof
  GROUP BY week_date
),
converted AS (
  SELECT
    week_date,
    walcl AS walcl_musd,
    ecb_eur * usd_per_eur AS ecb_musd,
    boj_100m_jpy * 100.0 / jpy_per_usd AS boj_musd,
    walcl + ecb_eur * usd_per_eur + boj_100m_jpy * 100.0 / jpy_per_usd AS combined_musd
  FROM pivoted
  WHERE walcl IS NOT NULL
    AND ecb_eur IS NOT NULL AND usd_per_eur IS NOT NULL
    AND boj_100m_jpy IS NOT NULL AND jpy_per_usd IS NOT NULL
),
smoothed AS (
  SELECT
    week_date, walcl_musd, ecb_musd, boj_musd, combined_musd,
    CASE
      WHEN COUNT(*) OVER w12 = 12 THEN AVG(combined_musd) OVER w12
    END AS ma12_musd
  FROM converted
  WINDOW w12 AS (ORDER BY week_date ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
)
SELECT
  week_date,
  walcl_musd,
  ecb_musd,
  boj_musd,
  combined_musd,
  ma12_musd,
  CASE
    WHEN ma12_musd IS NOT NULL
     AND LAG(ma12_musd, 12) OVER (ORDER BY week_date) IS NOT NULL
    THEN 100.0 * (ma12_musd / LAG(ma12_musd, 12) OVER (ORDER BY week_date) - 1)
  END AS mom_12w_pct
FROM smoothed;
