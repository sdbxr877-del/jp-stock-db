-- merge_fins_summary.sql -- MERGE raw.fins_summary_staging -> raw.fins_summary (key = disc_no).
-- Staging deduped by disc_no (latest fetched_at). Single source (jquants); no BY SOURCE clause.
-- Idempotent and re-runnable (one-time backfill + incremental daily). Deploy via {{PROJECT}} stdin pipe.

MERGE `{{PROJECT}}.raw.fins_summary` T
USING (
  SELECT
    disc_no, ticker, code5, disc_date, disc_time, doc_type, cur_per_type,
    cur_per_start, cur_per_end, cur_fy_start, cur_fy_end, nxt_fy_start, nxt_fy_end,
    sales, op, odp, np, eps, deps, total_assets, equity, equity_ratio, bps,
    cfo, cfi, cff, cash_eq, div_ann, div_total_ann, payout_ratio_ann,
    f_sales, f_op, f_odp, f_np, f_eps, f_div_ann,
    nxf_sales, nxf_op, nxf_odp, nxf_np, nxf_eps, nxf_div_ann,
    shares_out_fy, treasury_shares_fy, avg_shares, source, fetched_at
  FROM `{{PROJECT}}.raw.fins_summary_staging`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY disc_no ORDER BY fetched_at DESC) = 1
) S
ON T.disc_no = S.disc_no
WHEN MATCHED THEN UPDATE SET
  ticker = S.ticker,
  code5 = S.code5,
  disc_date = S.disc_date,
  disc_time = S.disc_time,
  doc_type = S.doc_type,
  cur_per_type = S.cur_per_type,
  cur_per_start = S.cur_per_start,
  cur_per_end = S.cur_per_end,
  cur_fy_start = S.cur_fy_start,
  cur_fy_end = S.cur_fy_end,
  nxt_fy_start = S.nxt_fy_start,
  nxt_fy_end = S.nxt_fy_end,
  sales = S.sales,
  op = S.op,
  odp = S.odp,
  np = S.np,
  eps = S.eps,
  deps = S.deps,
  total_assets = S.total_assets,
  equity = S.equity,
  equity_ratio = S.equity_ratio,
  bps = S.bps,
  cfo = S.cfo,
  cfi = S.cfi,
  cff = S.cff,
  cash_eq = S.cash_eq,
  div_ann = S.div_ann,
  div_total_ann = S.div_total_ann,
  payout_ratio_ann = S.payout_ratio_ann,
  f_sales = S.f_sales,
  f_op = S.f_op,
  f_odp = S.f_odp,
  f_np = S.f_np,
  f_eps = S.f_eps,
  f_div_ann = S.f_div_ann,
  nxf_sales = S.nxf_sales,
  nxf_op = S.nxf_op,
  nxf_odp = S.nxf_odp,
  nxf_np = S.nxf_np,
  nxf_eps = S.nxf_eps,
  nxf_div_ann = S.nxf_div_ann,
  shares_out_fy = S.shares_out_fy,
  treasury_shares_fy = S.treasury_shares_fy,
  avg_shares = S.avg_shares,
  source = S.source,
  fetched_at = S.fetched_at
WHEN NOT MATCHED THEN INSERT (
  disc_no, ticker, code5, disc_date, disc_time, doc_type, cur_per_type,
  cur_per_start, cur_per_end, cur_fy_start, cur_fy_end, nxt_fy_start, nxt_fy_end,
  sales, op, odp, np, eps, deps, total_assets, equity, equity_ratio, bps,
  cfo, cfi, cff, cash_eq, div_ann, div_total_ann, payout_ratio_ann,
  f_sales, f_op, f_odp, f_np, f_eps, f_div_ann,
  nxf_sales, nxf_op, nxf_odp, nxf_np, nxf_eps, nxf_div_ann,
  shares_out_fy, treasury_shares_fy, avg_shares, source, fetched_at
) VALUES (
  S.disc_no, S.ticker, S.code5, S.disc_date, S.disc_time, S.doc_type, S.cur_per_type,
  S.cur_per_start, S.cur_per_end, S.cur_fy_start, S.cur_fy_end, S.nxt_fy_start, S.nxt_fy_end,
  S.sales, S.op, S.odp, S.np, S.eps, S.deps, S.total_assets, S.equity, S.equity_ratio, S.bps,
  S.cfo, S.cfi, S.cff, S.cash_eq, S.div_ann, S.div_total_ann, S.payout_ratio_ann,
  S.f_sales, S.f_op, S.f_odp, S.f_np, S.f_eps, S.f_div_ann,
  S.nxf_sales, S.nxf_op, S.nxf_odp, S.nxf_np, S.nxf_eps, S.nxf_div_ann,
  S.shares_out_fy, S.treasury_shares_fy, S.avg_shares, S.source, S.fetched_at
);
