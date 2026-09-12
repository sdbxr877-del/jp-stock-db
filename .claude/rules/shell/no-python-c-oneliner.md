---
rule_id: shell-no-python-c-oneliner
category: shell
priority: high
paths:
  - "*.ps1"
  - "*.md"
related_failures:
  - DB-32
  - DB-57
  - "CW-07"
related_rules:
  - SR-12
  - "encoding/utf8-required"
  - "process/powershell-absolute-path"
applies_to_environments: [claude_code, chat_claude, human]
scope: global
source_project: jp-stock-db
vault_version: 1.0
vault_status: active
vault_imported: 2026-08-29
origin_path: (新規・SR-12 をルールファイル化)
last_updated: 2026-09-11
---

# PowerShell から `python -c "..."` で複雑な文字列を渡さない（SR-12）

<!-- portability-note -->
> **他プロジェクトでの読み替え** — 本ルールは `second-brain` から配布されている。
> 文中の `SR-xx` / `G-x` / `失敗NN` / `handoff_db_vNN.md` / `project_rules_db_v1.md` は
> **発祥プロジェクトでの出自の記録**であり、参照先が自プロジェクトに存在しなくてもよい。
> **規範・違反パターン・チェックリストはそのまま有効**。教訓の原文は
> `C:\second-brain\20_failures\` にある。
<!-- portability-note -->



## 規範

PowerShell から Python を呼ぶとき、**バッククォート・引用符・改行・正規表現を含む文字列を
`python -c "..."` のワンライナーで渡してはならない**。必ず `.py` ファイルとして保存し
`python <絶対パス>.py` の形式で実行する。

理由は PowerShell 固有のパーサ仕様である。

| 記号 | PowerShell での意味 | 起きること |
|---|---|---|
| `` ` `` | エスケープ文字（バックスラッシュ相当） | SQL の `` `table` `` が剥がれて構文エラー（DB-32） |
| `"` `'` | 引用の入れ子が Python 側と競合 | 文字列が途中で閉じる（DB-28） |
| 改行 | 引数が途中で切れる | 置換処理が黙って失敗する（CW-07） |
| 日本語 | コンソール codepage = CP932 で一次解釈 | 文字化けしたまま保存される（DB-59） |

**「1行で済むから」は採用理由にならない。** 過去3プロジェクトすべてで同じ壊れ方をしている。

## 違反パターン(検出すべきコード)

### Pattern 1: SQL をワンライナーで渡す（DB-32 直接型）
```powershell
# 違反例: バッククォートが PowerShell に食われる
python -c "import bq; bq.run('SELECT * FROM `raw.prices`')"
```

### Pattern 2: 改行や正規表現を含む置換処理（CW-07 直接型）
```powershell
# 違反例: 改行入り文字列が途中で切れ、置換が「成功」表示のまま何も変わらない
python -c "import re,io; s=open('x.md').read(); s=re.sub(r'^# .*\n', '# new\n', s, flags=re.M); open('x.md','w').write(s)"
```

### Pattern 3: ヒアドキュメントで Python を流し込む（DB-57 直接型）
```bash
# 違反例: bash では動くが PowerShell では再現できず、手順書として成立しない
python3 - <<'EOF'
...
EOF
```

## 正しい実装パターン

```powershell
# ✅ 独立スクリプトにして絶対パスで実行する
python C:\<プロジェクトルート>\tools\replace_header.py
```

```python
# C:\<プロジェクトルート>\tools\replace_header.py
from pathlib import Path
import re

target = Path(r"C:\<プロジェクトルート>\docs\x.md")
text = target.read_text(encoding="utf-8")
target.write_text(re.sub(r"^# .*\n", "# new\n", text, flags=re.M), encoding="utf-8", newline="\n")
print("replaced:", target)   # 実行後に必ず中身を読み直して確認する（Success を信じない）
```

例外として許容できるのは、**引用符・バッククォート・改行・日本語・正規表現をいっさい含まない
短い ASCII のみの式**に限る（例: `python -c "import sys; print(sys.version)"`）。

## 関連過去教訓

- [[DB-32]]: `python -c` 内のバッククォートが剥がれて SQL 構文エラー
- [[DB-57]]: Claude Code が検証手順として `python3 - <<EOF` を提案（SR-12 違反）
- [[DB-28]]: PowerShell `Add-Content` でシングルクォートが閉じない
- [[CW-07]]: 改行入り文字列を渡して置換が失敗（成功表示のまま無変更）
- [[DB-59]]: PowerShell Here-String 内の日本語が CP932 で文字化け

## レビュー時のチェックリスト

- [ ] `python -c` に引用符・バッククォート・改行・日本語・正規表現が含まれていないか
- [ ] 手順書・handoff に `python3 - <<EOF` 形式が混入していないか
- [ ] スクリプト実行は絶対パスか（`process/powershell-absolute-path`）
- [ ] 置換・書込処理の後、結果ファイルを読み直して確認しているか
