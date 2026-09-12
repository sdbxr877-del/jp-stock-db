---
rule_id: secrets-no-secret-print
category: secrets
priority: critical
paths:
  - "*.py"
related_failures:
  - DB-39
related_rules:
  - "§5"
  - "§3"
applies_to_environments: [claude_code, chat_claude, human]
last_updated: 2026-09-11
scope: global
source_project: FX-db
vault_version: 1.0
vault_imported: 2026-08-29
origin_path: C:\FX-db\.claude\rules\secrets\no-secret-print.md
---

# APIキー・口座番号・トークンをログ/標準出力に出さない

<!-- portability-note -->
> **他プロジェクトでの読み替え** — 本ルールは `second-brain` から配布されている。
> 文中の `SR-xx` / `G-x` / `失敗NN` / `handoff_db_vNN.md` / `project_rules_db_v1.md` は
> **発祥プロジェクトでの出自の記録**であり、参照先が自プロジェクトに存在しなくてもよい。
> **規範・違反パターン・チェックリストはそのまま有効**。教訓の原文は
> `C:\second-brain\20_failures\` にある。
<!-- portability-note -->


## 規範
API キー・口座番号・アクセストークン・パスワードを `print` / `log` / 例外メッセージに出力しない。
セッション末の監査 grep で 1件でも hit したら「誤検知」と独断せず**必ず修正**する。
Linux `grep`（小文字マッチ）と PowerShell `Select-String`（大文字小文字無視）の**両方で 0 hits** を確認する。

## 違反パターン(検出すべきコード)

### Pattern 1: 秘匿値の直接出力
```python
# 違反例
print(f"token={api_token}")
logging.info("account=%s key=%s", account_id, api_key)
```

### Pattern 2: 例外にそのまま含める
```python
# 違反例
raise RuntimeError(f"auth failed with key {api_key}")
```

### Pattern 3: レスポンス丸ごとダンプ（キーを含み得る）
```python
# 違反例
print(response.json())     # access_token を含む場合がある
```

## 正しい実装パターン
```python
def mask(s: str, keep: int = 4) -> str:
    return "****" if not s else s[:keep] + "****"

log.info("auth ok (key=%s, account=%s)", mask(api_key), mask(account_id))
# 秘匿値は .env から読み、値そのものは決してログに出さない
```

監査コマンド（両環境で 0 件を確認）:
```bash
grep -nE "print.*token|print.*key|print.*secret|print.*password|print.*account" *.py
```

## 関連過去教訓
- DB-39: G2 grep の hit を「誤検知だから OK」と独断 → CI で FAIL。1件でも hit したら必ず修正。

## レビュー時のチェックリスト
- [ ] token/key/secret/password/account を print・log していないか
- [ ] 例外メッセージに秘匿値が混ざっていないか
- [ ] API レスポンスを無加工でダンプしていないか
- [ ] 監査 grep が Linux/PowerShell 両方で 0 件か
