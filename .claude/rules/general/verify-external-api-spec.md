---
rule_id: general-verify-external-api-spec
category: general
priority: high
paths: []
related_failures:
  - DB-22
  - DB-23
  - DB-25
  - DB-36
  - DB-37
  - IR-08
related_rules:
  - "SR-9"
  - "project_rules_db_v1.md §1.5"
  - "general/dont-trust-success"
applies_to_environments: [claude_code, chat_claude, human]
scope: global
source_project: jp-stock-db
vault_version: 1.1
vault_status: active
vault_imported: 2026-08-31
last_updated: 2026-09-11
---

# 外部仕様は「公式ドキュメント」と「実機」の両方で確認する

<!-- portability-note -->
> **他プロジェクトでの読み替え** — 本ルールは `second-brain` から配布されている。
> 文中の `SR-xx` / `G-x` / `失敗NN` / `handoff_db_vNN.md` / `project_rules_db_v1.md` は
> **発祥プロジェクトでの出自の記録**であり、参照先が自プロジェクトに存在しなくてもよい。
> **規範・違反パターン・チェックリストはそのまま有効**。教訓の原文は
> `C:\second-brain\20_failures\` にある。
<!-- portability-note -->



## 規範

外部 API・ライブラリ・クラウドサービスの仕様を、**記憶・類推・社内ドキュメントだけを根拠に実装しない**。
実装前に (1) **公式ドキュメント**で確認し、(2) **最小リクエストを実機で1回通す**。両方が揃って初めて「わかった」とする。

社内ドキュメント（過去の handoff・設計書・本ルール自身を含む）も**外部公式仕様で再確認する**。
作成者が逆に解釈していることがある（[[DB-36]]）。

さらに、**一度確認した仕様は変わる**。API キー必須化（[[DB-23]]・2024年4月）、
ファイル形式の変更（[[DB-25]]）、rate-limit 強化（[[DB-37]]）はいずれも「以前は動いていた」ものが壊れた例。
動かなくなったときは、まず自分のコードを疑う前に**外部仕様が変わっていないか**を見る。

## 統合前に必ずやること（機械的な手順・2026-09-11追加）

外部APIに**初めて統合する**とき、または**既存統合の仕様が変わった**ときは、実装に入る前に次を実行する。

```powershell
Select-String -Path "C:\second-brain\20_failures\*.md","C:\second-brain\30_notes\*.md" -Pattern "<API名>" -List
```

ヒットが出たファイルは**開いて読む**。ヒットが無くても、思い当たる言い回し（サービス名の別表記、
使用ライブラリ名など）で最低1回は検索する。ゼロ件が続く場合のみ、
`00_index/MOC-notes.md` / `MOC-failures.md` を一覧してタグや関連プロジェクトから探す（全件は読まない）。

これは「探すべき」という規範を足すのではなく、**探す行為そのものを1個のコマンドとして手順化する**のが狙い。
索引・失敗教訓・技術ノートの全件先読みは行わない（[[note-rules-review-cost]]）。

## 違反パターン(検出すべきコード)

### Pattern 1: BASE URL・エンドポイントを記憶で書く
```python
# 違反例: それらしいが存在しないドメイン（DB-22。NXDOMAIN だった）
BASE = "https://api.edinet-api.go.jp/api/v2"
```

### Pattern 2: 認証の要否を確認せず匿名で叩く
```python
# 違反例: 2024年4月から Subscription-Key 必須（DB-23）
requests.get(BASE + "/documents.json", params={"date": d, "type": 2})
```

### Pattern 3: ライブラリのバージョンを固定せず「動いたから」で放置
```python
# 違反例: yfinance 0.2.54 は rate-limit 強化に非対応（DB-37）
# requirements.txt: yfinance
```

### Pattern 4: 社内ドキュメントの主張をそのまま前提にする
```
# 違反例: 「12週遅延説は誤り」と設計書にあったので遅延なしで設計した
# → 実際は公式仕様として今も生きていた（DB-36）
```

### Pattern 5: HTTPステータスコードだけで成否を判定する
```python
# 違反例: API管理ゲートウェイがエラーもJSONでラップして返すため、
# raise_for_status() も res.ok も素通りする（EDINET）
res = requests.get(BASE + "/documents.json", params=params)
assert res.status_code == 200          # ← 通過しても実際には失敗している場合がある
data = res.json()
if len(data.get("results", [])) == 0:
    return []                          # 誤り: 認証エラーでも同じ形になる。「0件」と誤読する
```

EDINET の実測（[[note-edinet-api]] §1）:

| 状況 | 実際の応答 |
|---|---|
| 匿名で `documents.json` | HTTP **200** / `metadata {}` / 本文 `{"StatusCode": 401, "message": "Access denied..."}` |
| 存在しない docID | HTTP **200** / `{"metadata": {"status": "404", "message": "Not Found"}}` |

判定は本文で行う: `results` 空 かつ `metadata` 空 → 認証エラー（0件ではない）／
`results` 空 かつ `metadata` あり → 本当に0件／HTTP 404 → 0件（休日など）。

さらに、**他プロジェクトの実装コードを前例として引き写すときも要注意**（[[IR-08]]）。
ir-auto-analyst は jp-stock-db の `edinet_import.py` に「APIキーなし可」とコメントがあるのを
根拠に匿名前提で設計したが、jp-stock-db 側の `.env` には鍵が設定されており、
**匿名経路はそもそも一度も実行されていなかった**。
「コードにその分岐がある」＝「その分岐が検証済み」ではない。
他プロジェクトの実装は「動く前例」ではなく「**その環境で**動いた前例」でしかない。
前提となる環境変数・鍵・権限が自分の環境でも同じか確認してから引き写す。

## 正しい実装パターン

```python
# ✅ 1. 公式ドキュメントの URL とバージョンをコード内に残す
# 公式: https://api.edinet-fsa.go.jp/api/v2  (EDINET API v2 仕様書 2024-04 版)
BASE = "https://api.edinet-fsa.go.jp/api/v2"

# ✅ 2. 最小リクエストを1回通し、HTTPステータスだけでなく本文/metadataも確認する
r = requests.get(f"{BASE}/documents.json",
                 params={"date": "2026-08-01", "type": 2,
                         "Subscription-Key": os.environ["EDINET_KEY"]}, timeout=30)
assert r.status_code == 200, f"疎通失敗: {r.status_code}"
data = r.json()
assert data.get("metadata"), f"本文でエラーの可能性（HTTP 200でもエラーを返すゲートウェイがある）: {data}"
```

```
# ✅ 3. 外部依存はバージョンを固定する
yfinance>=1.0.0,<2.0.0
```

## レビュー時のチェックリスト

- [ ] エンドポイント・パラメータ名の根拠（公式 URL）がコードかコメントに残っているか
- [ ] 認証方式と必須化時期を確認したか
- [ ] 外部ライブラリのバージョンが固定されているか
- [ ] 社内ドキュメントの主張を外部公式仕様で再確認したか（SR-9 / §1.5）
- [ ] 「昨日まで動いていた」障害で、外部仕様の変更を最初に疑ったか
- [ ] レスポンスは HTTP ステータスだけでなく本文/metadataも確認したか（ゲートウェイがエラーを200で返すAPIがある）
- [ ] 他プロジェクトの実装を前例にする場合、環境変数・鍵・権限が自分の環境でも同じか確認したか（[[IR-08]]）
- [ ] 初めての統合／仕様変更時に `20_failures/` `30_notes/` を API 名で検索したか
