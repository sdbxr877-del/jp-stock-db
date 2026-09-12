---
rule_id: yaml-no-powershell-heredoc
category: yaml
priority: high
paths:
  - "*.yml"
  - "*.yaml"
  - ".github/workflows/*"
related_failures:
  - DB-33
  - DB-28
related_rules:
  - SR-13
  - SR-17
  - G10
  - "shell/no-python-c-oneliner"
  - "encoding/utf8-required"
applies_to_environments: [claude_code, chat_claude, human]
scope: global
source_project: jp-stock-db
vault_version: 1.0
vault_status: active
vault_imported: 2026-08-29
origin_path: (新規・SR-13 をルールファイル化)
last_updated: 2026-09-11
---

# YAML / 設定ファイルを PowerShell ヒアドキュメントで生成しない（SR-13）

<!-- portability-note -->
> **他プロジェクトでの読み替え** — 本ルールは `second-brain` から配布されている。
> 文中の `SR-xx` / `G-x` / `失敗NN` / `handoff_db_vNN.md` / `project_rules_db_v1.md` は
> **発祥プロジェクトでの出自の記録**であり、参照先が自プロジェクトに存在しなくてもよい。
> **規範・違反パターン・チェックリストはそのまま有効**。教訓の原文は
> `C:\second-brain\20_failures\` にある。
<!-- portability-note -->



## 規範

`.yml` / `.yaml` / `.json` などインデントが意味を持つ設定ファイルを、
**PowerShell の Here-String（`@"..."@`）やエディタ手書きで作らない**。
必ず生成スクリプト（`write_workflow.py` / `write_yaml.py` 等）を経由して出力する。

さらに **生成された workflow を手で直接編集しない。** 直すのは生成スクリプト側であり、
編集後は必ず再生成する。手編集すると次の再生成で消え、消えたことに気づけない。

理由:

1. Here-String 内でインデントとタブが崩れ、YAML が構文的に壊れる（DB-33・約60分の手戻り）
2. 日本語を含むと CP932 で一次解釈され文字化けする（DB-59）
3. CRLF / BOM が混入し、GitHub Actions の Ubuntu runner でのみ失敗する（DB-34 / DB-54）
   — **Windows 側では最後まで気づけない**

## 違反パターン(検出すべきコード)

### Pattern 1: Here-String で workflow を書き出す（DB-33 直接型）
```powershell
# 違反例
@"
name: daily
on:
  schedule:
    - cron: '0 22 * * *'
"@ | Set-Content .github\workflows\daily.yml
```

### Pattern 2: `Set-Content` / `Add-Content` のデフォルト encoding
```powershell
# 違反例: CP932 + CRLF で保存され、Ubuntu runner で落ちる
Set-Content -Path config.yml -Value $body
```

### Pattern 3: 生成済み workflow の手編集
```
# 違反例: .github/workflows/daily.yml を直接エディタで修正して commit
# → write_workflow.py を再実行した瞬間に消える
```

## 正しい実装パターン

```python
# tools/write_workflow.py — YAML の唯一の生成元
from pathlib import Path

WORKFLOW = """\
name: daily
on:
  schedule:
    - cron: '0 22 * * *'
jobs:
  run:
    runs-on: ubuntu-latest
"""

out = Path(r"C:\<プロジェクトルート>\.github\workflows\daily.yml")
out.write_text(WORKFLOW, encoding="utf-8", newline="\n")   # UTF-8 BOMなし / LF
print("wrote:", out, out.stat().st_size, "bytes")
```

```powershell
# ✅ 生成 → 検証 → pre-flight の順で確認する
python C:\<プロジェクトルート>\tools\write_workflow.py
python C:\<プロジェクトルート>\tools\verify_utf8.py .github\workflows\daily.yml
# 各 step の bash はローカルで実行して確認する（SR-17 / G10）
```

## 関連過去教訓

- [[DB-33]]: PowerShell `@"..."@` で YAML 構文が破壊された（3回・約60分）
- [[DB-28]]: `Add-Content` でシングルクォートが閉じない
- [[DB-34]]: Windows 作成ファイルが Shift-JIS のまま push され CI で失敗
- [[DB-54]]: CRLF 混入。`.gitattributes` で LF 強制して構造的に解決
- [[DB-42]]: GHA の `set -euo pipefail` × grep の環境差は GHA でしか出ない → pre-flight 必須

## レビュー時のチェックリスト

- [ ] YAML / JSON が生成スクリプト経由で作られているか
- [ ] `@"..."@` / `Set-Content` で設定ファイルを書いていないか
- [ ] 出力が UTF-8 BOMなし / LF か（`verify_utf8.py` で実測）
- [ ] 生成済み workflow を手編集していないか（直すのは生成スクリプト）
- [ ] workflow の各 step の bash をローカルで実行確認したか（SR-17 / G10）
