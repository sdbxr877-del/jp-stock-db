---
doc_id: rules-readme
version: 1.0
last_updated: 2026-05-17
applies_to_environments:
  - claude_code
  - chat_claude
  - human_manual
related_handoffs:
  - handoff_db_v11_2.md
---

# .claude/rules/ — ルール体系の概要

jp_stock_db プロジェクトの **コードレビュー用ルール集** の置き場。
このディレクトリは `/rules-review` カスタムコマンドおよびチャット Claude による rules-review プロセスで参照される。

## 1. 設計思想

### 1.1. なぜルールを Markdown で外出しするか

`project_rules_db_v1.md`(マスタ)には SR-1〜SR-18 / G1〜G10 が網羅的に書かれているが、これは
**人間が一読する規範文書**であり、コードレビューで機械的に照合するには粒度が荒い。

本ディレクトリでは、同じルールを **カテゴリ別 / 違反パターン明示 / 正解パターン明示** の形に
分解し、Claude(Code / Web)が差分と照合しやすい構造で保管する。

### 1.2. ルール本体は単一情報源(SSOT)ではない

ルールの**マスタは `project_rules_db_v1.md`** であり、矛盾時はそちらを優先する。
本ディレクトリは「マスタをカテゴリ別に分解した照合用ビュー」と位置づける。
マスタ更新時は本ディレクトリも同期更新すること。

### 1.3. 環境非依存(Claude Code / チャット Claude / 人間で同一結果)

各ルールファイルは Markdown + YAML frontmatter で書く。
プロセス手順(`_process/rules-review-process.md`)も同じ形式で書かれており、
3環境のいずれが実行しても同じレビュー結果を返すことを目標とする。

## 2. ディレクトリ構造

````
.claude/rules/
├── README.md                    # 本ファイル
├── _process/                    # プロセス定義(レビュー対象外)
│   └── rules-review-process.md  # 単一情報源としての手順書
├── _tests/                      # 検出テスト(Phase 2-5 で作成・レビュー対象外)
├── general/                     # 全体規範
├── bq/                          # BigQuery 関連
├── secrets/                     # 秘匿情報
├── python/                      # Python 言語規約
├── shell/                       # シェル / PowerShell 規約
├── yaml/                        # YAML / GitHub Actions
└── git/                         # Git 操作
````

`_` で始まるディレクトリ(`_process/`, `_tests/`)は rules-review のレビュー対象から除外される。

## 3. カテゴリ一覧

| カテゴリ | 対象 | 想定ルール例 | 関連失敗教訓 |
|---|---|---|---|
| `general` | プロジェクト全体規範 | Success を信じない原則 / 一機能一バージョン | — |
| `bq` | BigQuery 関連の全コード | DRY RUN 必須 / パーティションフィルタ / SELECT * 禁止 / staging-only-tests | 失敗41 / 失敗43 |
| `secrets` | 秘匿情報の取り扱い | env var を print しない | 失敗39 |
| `python` | Python 言語規約 | UTF-8 必須 / `python -c` で SQL 渡さない | SR-14 / SR-12 |
| `shell` | シェル / PowerShell | PowerShell の文字列規約 | SR-15 |
| `yaml` | YAML / GitHub Actions | YAML は Python 生成のみ(手書き禁止) | SR-13 |
| `git` | Git 操作 | force push 禁止 / pre-commit 必須 | — |

同一カテゴリ内では原則 **5 ルール以下** を目標とする。超える場合はサブカテゴリ分割を検討
(例: `bq/dml/` と `bq/select/`)。

## 4. ルールファイル フォーマット

各ルールファイルは以下の構造で書く:

````markdown
---
rule_id: <カテゴリ>-<短い名前>          # 例: bq-dry-run-required
category: <カテゴリ名>                  # 例: bq
priority: critical | high | medium | low
paths:                                  # 適用対象ファイルパターン(省略時は全ファイル)
  - "*.py"
  - "**/*.sql"
related_failures:                       # 関連する過去教訓
  - 失敗XX
related_rules:                          # 関連する SR / G ルール
  - SR-X
  - G-Y
applies_to_environments:
  - claude_code
  - chat_claude
  - human
last_updated: YYYY-MM-DD
---

# <ルール名>

## 規範

<規範文 1〜3 段落>

## 違反パターン(検出すべきコード)

### Pattern 1: <違反タイプ名>
```python
# 違反例
```

## 正しい実装パターン

```python
# 正解例
```

## 関連過去教訓

- 失敗XX: <概要>

## レビュー時のチェックリスト

- [ ] <チェック項目 1>
- [ ] <チェック項目 2>
````

## 5. 優先度(priority)の運用ルール

| priority | 意味 | 違反時の挙動 |
|---|---|---|
| `critical` | 過去に実害(課金事故 / 本番事故 / Secret 漏洩等)が発生した教訓由来 | False Negative 厳禁・即時報告 |
| `high` | 構造的に重大リスクがあるが未発生 | False Negative 許容 5% 以下 |
| `medium` | 規約違反だが実害は限定的 | False Negative 許容 10% 以下 |
| `low` | スタイル / 慣習 | False Negative 許容 20% 以下 |

Phase 2 P2-2 で作成する **critical 3 ルール** は最優先で整備:
- `bq/staging-only-tests.md`(失敗43 対策)
- `secrets/no-env-var-print.md`(失敗39 対策)
- `bq/dry-run-required.md`(失敗41 対策)

## 6. プロセスとの関係

レビュー手順は `_process/rules-review-process.md` に独立して定義されている。
本 README は「ルール体系の概要」であり、レビュー手順そのものではない。

- ルール **何が** あるか → 本 README + 各ルールファイル
- ルールを **どう照合するか** → `_process/rules-review-process.md`
- ルールを **どう起動するか** → `.claude/commands/rules-review.md`(Claude Code 用)

## 7. 関連ドキュメント

- `.claude/rules/_process/rules-review-process.md`: レビュー手順の単一情報源
- `.claude/commands/rules-review.md`: Claude Code 用スラッシュコマンド定義
- `project_rules_db_v1.md`: 絶対命令ルール本体・マスタ
- `handoff_db_v11_2.md §D`: 本ディレクトリの初期設計
