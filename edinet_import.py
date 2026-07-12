"""
edinet_import.py (db_v0.6 Step 3 — CSV版)
EDINET XBRL_TO_CSV → BigQuery raw.financials 本番投入

変更点 (CSV版):
  - XBRL_TO_CSV/jpcrp*.csv (タブ区切り・UTF-16) を読み込む
  - 値は円単位 → /1,000,000 で百万円に変換

実行:
  python edinet_import.py --dry   # DRY RUN
  python edinet_import.py         # 本番
"""
import os, io, json, time, argparse, zipfile, requests
import pandas as pd
from datetime import datetime, timezone, date
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv(dotenv_path=r"C:\jp-stock-db\.env")

PROJECT      = "project-3eaadce9-f852-40e1-932"
TABLE_FIN    = f"{PROJECT}.raw.financials"
INDEX_FILE   = "edinet_index.json"
CHECKPOINT   = "checkpoint_edinet.json"

EDINET_BASE    = "https://api.edinet-fsa.go.jp/api/v2"
EDINET_API_KEY = os.environ.get("EDINET_API_KEY", "")

CHUNK_SIZE             = 50
SLEEP_SEC              = 1.5
MAX_CONSECUTIVE_ERRORS = 5

client = bigquery.Client(project=PROJECT)

# ─── 要素ID → (BQ列名, 優先度) ─────────────────────────────────
ELEMENT_MAP = {
    "jpcrp_cor:NetSalesSummaryOfBusinessResults":              ("revenue",    2),
    "jpcrp_cor:NetSales":                                       ("revenue",    1),
    "jpigp_cor:RevenueIFRSSummaryOfBusinessResults":           ("revenue",    2),
    "jpcrp_cor:OperatingIncomeLossSummaryOfBusinessResults":   ("op_profit",  3),
    "jpcrp_cor:OperatingIncome":                               ("op_profit",  2),
    "jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults":    ("op_profit",  1),
    "jpigp_cor:OperatingProfitLossIFRSSummaryOfBusinessResults": ("op_profit", 3),
    "jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults": ("net_income", 2),
    "jpcrp_cor:ProfitLossAttributableToOwnersOfParent":        ("net_income", 1),
    "jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults": ("net_income", 2),
    "jpcrp_cor:BasicEarningsLossPerSharesSummaryOfBusinessResults": ("eps",   2),
    "jpcrp_cor:BasicEarningsPerShare":                         ("eps",        1),
    "jpigp_cor:BasicEarningsLossPerShareIFRSSummaryOfBusinessResults": ("eps", 2),
    "jpcrp_cor:NetAssetsSummaryOfBusinessResults":             ("equity",     2),
    "jpcrp_cor:NetAssets":                                     ("equity",     1),
    "jpigp_cor:EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults": ("equity", 2),
}

# R&D費(研究開発費)は候補元素が単一のため ELEMENT_MAP と別立てで厳密一致抽出
RD_ELEM = "jpcrp_cor:ResearchAndDevelopmentExpensesResearchAndDevelopmentActivities"


def download_csv_bytes(doc_id):
    url    = f"{EDINET_BASE}/documents/{doc_id}"
    params = {"type": 5}
    if EDINET_API_KEY:
        params["Subscription-Key"] = EDINET_API_KEY
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csvs = [n for n in zf.namelist()
                    if "XBRL_TO_CSV" in n and "jpcrp" in n and n.endswith(".csv")]
            if not csvs:
                return None
            return zf.read(max(csvs, key=lambda n: zf.getinfo(n).file_size))
    except Exception:
        return None


def parse_csv(csv_bytes):
    result = {k: None for k in ["revenue", "op_profit", "net_income", "eps", "equity", "rd_expenses"]}
    try:
        df = pd.read_csv(
            io.StringIO(csv_bytes.decode("utf-16", errors="replace")),
            sep="\t", dtype=str
        )
    except Exception:
        return result

    if "要素ID" not in df.columns:
        return result

    df_cur = df[
        df["コンテキストID"].str.contains("CurrentYear", na=False) &
        ~df["コンテキストID"].str.contains("Prior", na=False)
    ].copy()

    candidates = {k: [] for k in result}

    for _, row in df_cur.iterrows():
        elem = str(row.get("要素ID", ""))
        if elem not in ELEMENT_MAP:
            continue
        bq_col, priority = ELEMENT_MAP[elem]
        unit  = str(row.get("ユニットID", ""))
        val_s = str(row.get("値", ""))
        if not val_s or val_s.lower() in ("nan", "-", "－", ""):
            continue
        try:
            val = float(val_s.replace(",", ""))
        except ValueError:
            continue

        if "PerShare" in unit:
            value = round(val, 4)
        elif unit in ("JPY", ""):
            value = round(val / 1_000_000, 2)
        elif unit == "JPYThousands":
            value = round(val / 1_000, 2)
        else:
            value = round(val / 1_000_000, 2)

        candidates[bq_col].append((value, priority))

    for col, cands in candidates.items():
        if cands:
            result[col] = max(cands, key=lambda x: x[1])[0]

    # R&D費(研究開発活動・全社総額): 要素ID厳密一致 & CurrentYear & Prior除外 & Member除外。
    # 既存指標の df_cur/candidates 機構とは独立(既存の連結/個別解決を変えないため)。
    # 検証(4183/1808/8306)で連結総額が Member なし CurrentYearDuration に単一で立つことを確認済。
    rd_rows = df[
        (df["要素ID"].astype(str) == RD_ELEM) &
        df["コンテキストID"].astype(str).str.contains("CurrentYear", na=False) &
        ~df["コンテキストID"].astype(str).str.contains("Prior", na=False) &
        (~df["コンテキストID"].astype(str).str.contains("Member", na=False) |
         df["コンテキストID"].astype(str).str.contains("CorporateSharedMember", na=False))
    ]
    for _, row in rd_rows.iterrows():
        val_s = str(row.get("値", ""))
        if val_s and val_s.lower() not in ("nan", "-", "－", ""):
            try:
                result["rd_expenses"] = round(float(val_s.replace(",", "")) / 1_000_000, 2)
            except ValueError:
                pass

    return result


def calc_roe(net_income, equity):
    if net_income is None or equity is None or equity == 0:
        return None
    return round((net_income / equity) * 100, 2)


def get_existing_edinet(all_tickers):
    """失敗18対策: 全対象の既存 source='edinet' を事前一括取得"""
    if not all_tickers:
        return set()
    codes_sql = ", ".join(f"'{t}'" for t in all_tickers)
    sql = f"""
        SELECT DISTINCT ticker, fiscal_year
        FROM `{TABLE_FIN}`
        WHERE ticker IN ({codes_sql}) AND source = 'edinet'
    """
    try:
        return {(r.ticker, r.fiscal_year) for r in client.query(sql).result()}
    except Exception as e:
        print(f"[WARN] 既存確認: {e.__class__.__name__}")
        return set()


def upload_chunk(records, dry_run=False):
    if not records:
        return 0
    df = pd.DataFrame(records)
    df["reported_at"] = pd.to_datetime(df["reported_at"]).dt.date
    if dry_run:
        print(f"    [DRY RUN] {len(df)} 行 スキップ")
        return len(df)
    job = client.load_table_from_dataframe(
        df, TABLE_FIN,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
    )
    job.result()
    return len(df)


def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            return json.load(f)
    return {"done": []}


def save_checkpoint(done):
    with open(CHECKPOINT, "w") as f:
        json.dump({"done": list(done)}, f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print(f"edinet_import.py: Step 3 CSV版 ({'DRY RUN' if args.dry else '本番'})")
    print("=" * 60)

    with open(INDEX_FILE, encoding="utf-8") as f:
        index = json.load(f)
    docs = index.get("docs", {})
    if not docs:
        print("[ERROR] インデックスが空です")
        return

    cp          = load_checkpoint()
    done        = set(cp["done"])
    all_tickers = list(docs.keys())
    remaining   = [t for t in all_tickers if t not in done]

    print(f"対象銘柄: {len(all_tickers)}  残り: {len(remaining)}")
    print("BQ 既存確認中...")
    existing = get_existing_edinet(all_tickers)
    print(f"  既存: {len(existing)} ペア\n")

    chunk_records, chunk_done = [], []
    consecutive_errors = 0
    total_rows = 0

    for ticker in remaining:
        entries     = docs.get(ticker, [])
        new_entries = [e for e in entries
                       if (ticker, e.get("fiscal_year")) not in existing]

        if not new_entries:
            done.add(ticker); save_checkpoint(done); continue

        ticker_records = []
        for entry in new_entries:
            doc_id     = entry["docID"]
            fy         = entry.get("fiscal_year", "")
            period_end = entry.get("period_end", "")

            csv_bytes = download_csv_bytes(doc_id)
            if csv_bytes is None:
                print(f"  [{ticker}] {fy}: DL エラー")
                consecutive_errors += 1
                time.sleep(SLEEP_SEC)
                continue

            consecutive_errors = 0
            values = parse_csv(csv_bytes)
            roe    = calc_roe(values["net_income"], values["equity"])

            try:
                rep_date = date.fromisoformat(period_end) if period_end else None
            except ValueError:
                rep_date = None
            try:
                fiscal_month = int(period_end[5:7]) if period_end and len(period_end)>=7 else None
            except (ValueError, IndexError):
                fiscal_month = None

            record = {
                "ticker":       ticker,
                "fiscal_year":  fy,
                "period_type":  "annual",
                "revenue":      values["revenue"],
                "op_profit":    values["op_profit"],
                "net_income":   values["net_income"],
                "eps":          values["eps"],
                "roe":          roe,
                "rd_expenses":  values["rd_expenses"],
                "reported_at":  rep_date,
                "source":       "edinet",
                "fetched_at":   datetime.now(timezone.utc),
            }
            ticker_records.append(record)
            nn = sum(1 for v in values.values() if v is not None)
            print(f"  [{ticker:6s}] {fy:6s}: rev={values['revenue'] or 'None'}  op={values['op_profit'] or 'None'}  ni={values['net_income'] or 'None'} ({nn}/6)")
            time.sleep(SLEEP_SEC)

        chunk_records.extend(ticker_records)
        chunk_done.append(ticker)

        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            print(f"\n!!! 連続エラー {MAX_CONSECUTIVE_ERRORS} 回 → 自動停止 !!!")
            break

        if len(chunk_done) >= CHUNK_SIZE:
            rows = upload_chunk(chunk_records, args.dry)
            for t in chunk_done: done.add(t)
            save_checkpoint(done)
            total_rows += rows
            print(f"\n  >>> BQ 投入: {len(chunk_done)} 銘柄 / {rows} 行\n")
            chunk_records, chunk_done = [], []
            time.sleep(2)

    if chunk_records:
        rows = upload_chunk(chunk_records, args.dry)
        for t in chunk_done: done.add(t)
        save_checkpoint(done)
        total_rows += rows
        print(f"  >>> BQ 投入(端数): {len(chunk_done)} 銘柄 / {rows} 行")

    print(f"\n{'='*60}")
    print(f"完了: 投入行数={total_rows} / 完了銘柄={len(done)}")
    if not args.dry:
        print("次: python quality_check_fin.py ; python dedup_check_fin.py")


if __name__ == "__main__":
    main()
