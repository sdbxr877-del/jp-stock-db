"""
edinet_fetch_index.py (db_v0.6 Step 1)
EDINET API から有価証券報告書インデックスを構築する

仕様:
  - EDINET API v2 書類一覧 (docTypeCode=120: 有価証券報告書) を取得
  - secCode (5桁) → ticker (4桁) へ変換してマッチング
  - 検索期間: 2021-06-01 〜 本日 (FY2021〜FY2025 の提出期間をカバー)
  - 中断・再開: edinet_index.json の last_searched_date から自動再開
  - APIキー: なしで開始 (.env の EDINET_API_KEY があれば自動使用)

実行:
  python edinet_fetch_index.py

出力:
  edinet_index.json
    docs: {ticker: [{docID, fiscal_year, period_start, period_end, ...}]}

所要時間の目安:
  全期間 (約 1,800 日): SLEEP=0.5s なら約 15 分
  再開した場合は残り分のみ
"""

import os
import json
import time
import requests
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv(dotenv_path=r"C:\jp-stock-db\.env")

EDINET_BASE  = "https://api.edinet-fsa.go.jp/api/v2"
INDEX_FILE   = "edinet_index.json"

SLEEP_SEC      = 0.5          # レート制限対策 (APIキーなし: 0.5〜1.0s 推奨)
SAVE_INTERVAL  = 30           # 何日ごとにチェックポイント保存するか
DOC_TYPE_YK    = "120"        # 有価証券報告書

# 検索期間
SEARCH_START = date(2021, 6, 1)    # FY2021 (3月決算) の最初の提出可能日
SEARCH_END   = date.today()        # 本日まで

# APIキー (.env に EDINET_API_KEY があれば使用)
EDINET_API_KEY = os.environ.get("EDINET_API_KEY", "")


# ─────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────

def seccode_to_ticker(seccode):
    """EDINET 5桁 secCode → 4桁 ticker ('72030' → '7203')"""
    if seccode and len(seccode) == 5 and seccode.endswith("0"):
        return seccode[:-1]
    return None


def period_end_to_fiscal_year(period_end):
    """'2025-03-31' → '25/3' (raw.financials の fiscal_year 形式)"""
    if not period_end or len(period_end) < 7:
        return None
    try:
        year  = int(period_end[2:4])
        month = int(period_end[5:7])
        return f"{year}/{month}"
    except ValueError:
        return None


# ─────────────────────────────────────────
# ファイル I/O
# ─────────────────────────────────────────

def load_targets():
    # SSOT: edinet_universe.py（db_v44・稼働 index.docs 16 で確定）
    from edinet_universe import EDINET_UNIVERSE
    return list(EDINET_UNIVERSE)


def load_index():
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE) as f:
            return json.load(f)
    return {"docs": {}, "last_searched_date": None, "search_end": None}


def save_index(index):
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────
# EDINET API 呼び出し
# ─────────────────────────────────────────

def fetch_docs_for_date(target_date, target_tickers):
    """
    指定日の書類一覧を取得し、対象 ticker の有価証券報告書のみ返す
    Returns: list of matched doc dict
    """
    url    = f"{EDINET_BASE}/documents.json"
    params = {"date": target_date.strftime("%Y-%m-%d"), "type": 2}
    if EDINET_API_KEY:
        params["Subscription-Key"] = EDINET_API_KEY
    headers = {}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        if resp.status_code == 404:
            return []          # その日は提出なし (EDINET が 404 を返す日がある)
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except requests.exceptions.RequestException as e:
        print(f"\n  [WARN] {target_date}: {e.__class__.__name__}")
        return []
    except (ValueError, KeyError):
        return []

    matched = []
    for doc in results:
        if doc.get("docTypeCode")    != DOC_TYPE_YK:
            continue
        if doc.get("withdrawalStatus") != "0":
            continue   # 取り下げ済みはスキップ
        if doc.get("xbrlFlag")       != "1":
            continue   # XBRL なしはスキップ

        ticker = seccode_to_ticker(doc.get("secCode", ""))
        if ticker and ticker in target_tickers:
            matched.append({
                "ticker":      ticker,
                "docID":       doc.get("docID"),
                "edinetCode":  doc.get("edinetCode"),
                "filerName":   doc.get("filerName"),
                "period_start": doc.get("periodStart", ""),
                "period_end":  doc.get("periodEnd", ""),
                "submit_date": target_date.strftime("%Y-%m-%d"),
            })

    return matched


# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────

def main():
    print("=" * 60)
    print("edinet_fetch_index.py: Step 1 EDINET インデックス構築")
    print("=" * 60)

    targets = load_targets()
    if not targets:
        print("[ERROR] 対象銘柄が空です")
        return

    target_set = set(targets)
    print(f"対象銘柄数 : {len(target_set)}")
    print(f"APIキー    : {'あり' if EDINET_API_KEY else 'なし (匿名)'}")

    index = load_index()
    docs  = index.get("docs", {})

    # 再開ポイントを決定
    last = index.get("last_searched_date")
    if last:
        y, m, d_ = map(int, last.split("-"))
        start = date(y, m, d_) + timedelta(days=1)
        existing_docs = sum(len(v) for v in docs.values())
        print(f"前回の続き : {start} から再開 (取得済み書類 {existing_docs} 件)")
    else:
        start = SEARCH_START

    end   = SEARCH_END
    total = (end - start).days + 1
    print(f"検索期間   : {start} 〜 {end} ({total} 日間)")
    print(f"SLEEP      : {SLEEP_SEC}s/日 → 目安 {total * SLEEP_SEC / 60:.1f} 分")
    print()

    current     = start
    day_count   = 0
    found_count = 0

    while current <= end:
        # 月初のみ進捗表示
        if current.day == 1 or current == start:
            remaining = target_set - set(docs.keys())
            pct = (current - start).days / max(total, 1) * 100
            print(f"  [{current}] {pct:4.1f}%  残り対象銘柄: {len(remaining)}")
            if not remaining:
                print("  → 全対象銘柄の書類を取得済み。検索終了。")
                break

        matched = fetch_docs_for_date(current, target_set)

        for m in matched:
            ticker      = m["ticker"]
            fiscal_year = period_end_to_fiscal_year(m["period_end"])
            entry = {
                "docID":       m["docID"],
                "fiscal_year": fiscal_year,
                "period_start": m["period_start"],
                "period_end":  m["period_end"],
                "submit_date": m["submit_date"],
                "edinetCode":  m["edinetCode"],
                "filerName":   m["filerName"],
            }
            if ticker not in docs:
                docs[ticker] = []

            # 同一 (ticker, fiscal_year) の重複を除去
            existing_fy = {d["fiscal_year"] for d in docs[ticker]}
            if fiscal_year not in existing_fy:
                docs[ticker].append(entry)
                found_count += 1

        day_count += 1

        # チェックポイント保存
        if day_count % SAVE_INTERVAL == 0 or current == end:
            index["docs"]               = docs
            index["last_searched_date"] = current.strftime("%Y-%m-%d")
            index["search_end"]         = end.strftime("%Y-%m-%d")
            save_index(index)

        current += timedelta(days=1)
        time.sleep(SLEEP_SEC)

    # 最終保存
    index["docs"]               = docs
    index["last_searched_date"] = min(current - timedelta(days=1), end).strftime("%Y-%m-%d")
    index["search_end"]         = end.strftime("%Y-%m-%d")
    save_index(index)

    # ─── 結果表示 ───────────────────────
    print()
    print("=" * 60)
    print("インデックス構築完了")
    print("=" * 60)
    found_tickers = set(docs.keys())
    not_found     = target_set - found_tickers
    total_docs    = sum(len(v) for v in docs.values())

    print(f"対象銘柄    : {len(target_set)}")
    print(f"書類取得    : {len(found_tickers)} 銘柄 / {total_docs} 件")
    print(f"書類未取得  : {len(not_found)} 銘柄")

    if not_found:
        print(f"\n--- 書類未取得銘柄 (先頭 20 件) ---")
        for t in sorted(not_found)[:20]:
            print(f"  {t}")

    print(f"\n→ {INDEX_FILE} に保存しました")
    print("次のステップ: python edinet_test5.py (SR-8 単体テスト)")


if __name__ == "__main__":
    main()
