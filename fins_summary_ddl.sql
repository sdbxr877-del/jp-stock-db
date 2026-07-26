-- fins_summary_ddl.sql -- raw.fins_summary (J-Quants V2 /fins/summary) prod + staging
-- Grain: one row per disclosure. PK = disc_no. Deploy via {{PROJECT}} stdin pipe.
-- Non-destructive: CREATE TABLE IF NOT EXISTS only. Types: money NUMERIC, ratio/eps FLOAT64.
-- ticker is 4-digit normalized (API Code is 5-digit) for joins with raw.prices / raw.financials.

CREATE SCHEMA IF NOT EXISTS `{{PROJECT}}.raw`;

CREATE TABLE IF NOT EXISTS `{{PROJECT}}.raw.fins_summary`
(
  disc_no           STRING  NOT NULL,   -- DiscNo, primary key (unique per disclosure)
  ticker            STRING  NOT NULL,   -- 4-digit normalized from API Code (5-digit)
  code5             STRING,             -- original 5-digit API Code
  disc_date         DATE,               -- DiscDate
  disc_time         STRING,             -- DiscTime (HH:MM:SS)
  doc_type          STRING,             -- DocType (e.g. 1QFinancialStatements_Consolidated_IFRS)
  cur_per_type      STRING,             -- CurPerType (FY/1Q/2Q/3Q)
  cur_per_start     DATE,               -- CurPerSt
  cur_per_end       DATE,               -- CurPerEn (cumulative period end for Q disclosures)
  cur_fy_start      DATE,               -- CurFYSt
  cur_fy_end        DATE,               -- CurFYEn
  nxt_fy_start      DATE,               -- NxtFYSt
  nxt_fy_end        DATE,               -- NxtFYEn
  -- consolidated actuals (cumulative for Q disclosures)
  sales             NUMERIC,            -- Sales
  op                NUMERIC,            -- OP (operating profit)
  odp               NUMERIC,            -- OdP (ordinary profit; empty under IFRS)
  np                NUMERIC,            -- NP (net profit)
  eps               FLOAT64,            -- EPS
  deps              FLOAT64,            -- DEPS (diluted EPS)
  total_assets      NUMERIC,            -- TA
  equity            NUMERIC,            -- Eq
  equity_ratio      FLOAT64,            -- EqAR
  bps               FLOAT64,            -- BPS
  cfo               NUMERIC,            -- CFO
  cfi               NUMERIC,            -- CFI
  cff               NUMERIC,            -- CFF
  cash_eq           NUMERIC,            -- CashEq
  -- dividend actuals
  div_ann           FLOAT64,            -- DivAnn (annual dividend per share, actual)
  div_total_ann     NUMERIC,            -- DivTotalAnn
  payout_ratio_ann  FLOAT64,            -- PayoutRatioAnn
  -- current-FY company forecast (populated on Q disclosures)
  f_sales           NUMERIC,            -- FSales (current-FY full-year forecast)
  f_op              NUMERIC,            -- FOP
  f_odp             NUMERIC,            -- FOdP
  f_np              NUMERIC,            -- FNP
  f_eps             FLOAT64,            -- FEPS
  f_div_ann         FLOAT64,            -- FDivAnn
  -- next-FY company forecast (populated on FY disclosures)
  nxf_sales         NUMERIC,            -- NxFSales
  nxf_op            NUMERIC,            -- NxFOP
  nxf_odp           NUMERIC,            -- NxFOdP
  nxf_np            NUMERIC,            -- NxFNp
  nxf_eps           FLOAT64,            -- NxFEPS
  nxf_div_ann       FLOAT64,            -- NxFDivAnn
  -- shares
  shares_out_fy     INT64,              -- ShOutFY (issued shares incl treasury, period end)
  treasury_shares_fy INT64,             -- TrShFY (treasury shares, period end)
  avg_shares        INT64,              -- AvgSh (period average shares)
  -- meta
  source            STRING,             -- constant 'jquants'
  fetched_at        TIMESTAMP           -- ingest timestamp (UTC)
)
CLUSTER BY ticker;

CREATE TABLE IF NOT EXISTS `{{PROJECT}}.raw.fins_summary_staging`
(
  disc_no           STRING  NOT NULL,
  ticker            STRING  NOT NULL,
  code5             STRING,
  disc_date         DATE,
  disc_time         STRING,
  doc_type          STRING,
  cur_per_type      STRING,
  cur_per_start     DATE,
  cur_per_end       DATE,
  cur_fy_start      DATE,
  cur_fy_end        DATE,
  nxt_fy_start      DATE,
  nxt_fy_end        DATE,
  sales             NUMERIC,
  op                NUMERIC,
  odp               NUMERIC,
  np                NUMERIC,
  eps               FLOAT64,
  deps              FLOAT64,
  total_assets      NUMERIC,
  equity            NUMERIC,
  equity_ratio      FLOAT64,
  bps               FLOAT64,
  cfo               NUMERIC,
  cfi               NUMERIC,
  cff               NUMERIC,
  cash_eq           NUMERIC,
  div_ann           FLOAT64,
  div_total_ann     NUMERIC,
  payout_ratio_ann  FLOAT64,
  f_sales           NUMERIC,
  f_op              NUMERIC,
  f_odp             NUMERIC,
  f_np              NUMERIC,
  f_eps             FLOAT64,
  f_div_ann         FLOAT64,
  nxf_sales         NUMERIC,
  nxf_op            NUMERIC,
  nxf_odp           NUMERIC,
  nxf_np            NUMERIC,
  nxf_eps           FLOAT64,
  nxf_div_ann       FLOAT64,
  shares_out_fy     INT64,
  treasury_shares_fy INT64,
  avg_shares        INT64,
  source            STRING,
  fetched_at        TIMESTAMP
);
