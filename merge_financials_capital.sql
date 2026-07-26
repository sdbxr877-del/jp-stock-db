-- merge_financials_capital.sql -- one-off DML (db_v57 / P3)
-- Bring capital columns (equity / shares_outstanding / dividend_paid) from
-- raw.financials_staging into raw.financials.
--   WHEN MATCHED           : update yfinance rows in place with the 3 columns.
--   WHEN NOT MATCHED BY TARGET : insert staging rows absent from target
--                            (new latest periods, new tickers). rd_expenses /
--                            cip / avg_salary are not in the INSERT list -> NULL.
-- edinet rows and any yfinance rows without a staging match are NOT touched
-- (no WHEN NOT MATCHED BY SOURCE clause), so they are preserved.
-- Expected affected rows: UPDATE 15534 + INSERT 2451 = 17985; table 16874 -> 19325.
MERGE `{{PROJECT}}.raw.financials` T
USING `{{PROJECT}}.raw.financials_staging` S
ON T.ticker = S.ticker AND T.fiscal_year = S.fiscal_year AND T.source = S.source
WHEN MATCHED THEN UPDATE SET
  T.equity = S.equity,
  T.shares_outstanding = S.shares_outstanding,
  T.dividend_paid = S.dividend_paid
WHEN NOT MATCHED BY TARGET THEN INSERT
  (ticker, fiscal_year, period_type, revenue, op_profit, net_income, eps, roe,
   reported_at, source, fetched_at, equity, shares_outstanding, dividend_paid)
  VALUES
  (S.ticker, S.fiscal_year, S.period_type, S.revenue, S.op_profit, S.net_income,
   S.eps, S.roe, S.reported_at, S.source, S.fetched_at,
   S.equity, S.shares_outstanding, S.dividend_paid);
