---
process_id: rules-review-process
version: 1.0
last_updated: 2026-05-17
applies_to_environments:
  - claude_code
  - chat_claude
  - human_manual
related_handoffs:
  - handoff_db_v11_2.md
related_failures:
  - 失敗39
  - 失敗41
  - 失敗43
---

# rules-review 実行プロセス(環境非依存)

このプロセスは Claude Code, チャット Claude(Web/モバイル), 人間のいずれが実施しても
**同じ結果**になるよう設計されている。本ファイルがプロセスの「単一情報源」である。

## 1. 目的

コード差分を `.claude/rules/` 配下のルールファイルと照合し、違反を検出して報告する。

特に以下の過去教訓の再発防止を目的とする:
- 失敗39: Secrets 監査 hit(`print` 文に key / token / secret / password を含めない)
- 失敗41: BQ 全スキャン課金(MERGE 1本での全パーティション処理)
- 失敗43: 本番テーブル誤書込(staging-only-tests 違反)

## 2. 入力

| 項目 | 内容 | 取得方法(環境別) |
|---|---|---|
| 差分情報 | 変更ファイル一覧 + 各ファイルの diff | Claude Code: `git diff` Bash / チャット Claude: 添付された diff or 全文 |
| ルールファイル群 | `.claude/rules/**/*.md`(`_process/` と `README.md` を除外) | 両環境とも Read |

差分の起点(base commit)は、明示されなければ `HEAD~1`(直前 commit との差分)とする。

## 3. プロセス手順

### Step 1: ルールファイル収集

`.claude/rules/` 配下の `.md` ファイルを再帰的に列挙する。除外対象:
- `_process/` 配下(プロセス定義ファイル群)
- `README.md`(ルール体系の説明ファイル)
- `_tests/` 配下(将来追加されるテストケース置き場)

各ファイルの frontmatter を YAML としてパースし、以下フィールドを取得:
- `rule_id`(文字列・必須)
- `category`(文字列・必須)
- `priority`(critical / high / medium / low)
- `paths`(リスト・適用対象ファイルパターン)
- `related_failures`(リスト)
- `applies_to_environments`(リスト)

### Step 2: 適用範囲フィルタ

各ルールの frontmatter から `paths:` を取得し、変更ファイルとマッチング:

- ワイルドカード解釈ルール:
  - `*.py` → 任意のディレクトリの `.py` ファイル
  - `**/*.sql` → 任意の深さの `.sql` ファイル
  - `daily_*.py` → 先頭が `daily_` の `.py` ファイル
- マッチしたルールのみを以降の処理対象とする
- `paths:` が省略されているルールは「全変更ファイルに適用」と解釈

### Step 3: カテゴリグルーピング

frontmatter の `category` フィールドでグルーピング:
- `general`(全体規範)
- `bq`(BigQuery 関連)
- `secrets`(秘匿情報)
- `python`(Python 言語規約)
- `shell`(シェル / PowerShell 規約)
- `yaml`(YAML / GitHub Actions)
- `git`(Git 操作)

新カテゴリ追加時は `.claude/rules/README.md` も更新する。

### Step 4: グループごとのレビュー

各カテゴリグループに対し、そのグループ内のルールだけを使って差分をレビューする。

| 環境 | 実装方法 |
|---|---|
| Claude Code | `Task` tool でサブエージェントを並列起動。各サブエージェントは1カテゴリを担当 |
| チャット Claude | カテゴリごとに順次レビュー(または「カテゴリ X について」と区切って依頼) |
| 人間 | 各ルールの「レビュー時のチェックリスト」セクションを手動消化 |

各サブエージェント / 順次レビューは、対象カテゴリのルールファイルを Read した上で、差分の各行に対し以下を判定:
- ルールの違反パターン(`## 違反パターン` セクション)に該当するか
- ルールの正しい実装パターン(`## 正しい実装パターン` セクション)から逸脱していないか

### Step 5: 違反レポート出力

違反が見つかった場合、以下の**標準形式**で出力する:

```
## Rules Compliance Violations

### {rule_file_path}
- **Violated rule**: {rule のタイトルまたは規範文サマリ}
- **Location**: {ファイルパス}:{行番号}
- **Description**: {何が違反しているか具体的に}
- **Suggested fix**: {修正案}
- **Related failure**: {related_failures から}
```

複数の違反がある場合は `### {rule_file_path}` のブロックを繰り返す。

違反なしの場合:
```
✅ All rules compliant
```

## 4. 出力の決定論性

同じ入力(差分 + ルールファイル)に対しては、できるだけ同じ違反検出結果を返すこと。
Claude のサンプリングによるブレの許容範囲は **「同じ違反を見逃さない」** こと。

- **False Negative(見逃し): 許容 0%**(失敗教訓の再発になるため)
- **False Positive(誤検知): 許容 10〜20%**(後で人間が判定すれば良い)

## 5. 環境別の起動方法

### 5.1. Claude Code

```
/rules-review
/rules-review --base-commit abc1234
```

詳細は `.claude/commands/rules-review.md` を参照。

### 5.2. チャット Claude(Web/モバイル)

handoff zip(`.claude/` 含む)を添付した上で、自然言語プロンプト:

```
添付した jp_stock_db zip 内の .claude/rules/ ディレクトリを開き、
.claude/rules/_process/rules-review-process.md の手順に従って、
下記の差分を全ルールと照合してください。

差分:
{git diff の出力 または 変更後のファイル内容}

違反があれば標準形式で報告してください。
```

### 5.3. 人間(手動)

各ルールファイルの「レビュー時のチェックリスト」セクションを順次消化する。

## 6. プロセス更新時の整合性確認

本ファイルを更新した場合、以下を同期更新する:
- `.claude/commands/rules-review.md`(Claude Code 用スラッシュコマンド定義)
- `.claude/rules/README.md`(ルール体系の概要)
- 直近の `handoff_db_v{N}.md` に変更履歴を記載
- チャット Claude セッションには「プロセス更新済」と明示

## 7. 関連ドキュメント

- `handoff_db_v11_2.md §D-4`: 本プロセスの初出設計
- `handoff_db_v11_2.md §F`: チャット Claude 互換性設計
- `project_rules_db_v1.md`: 絶対命令ルール本体(SR-1〜SR-18 / G1〜G10)・マスタ

矛盾が生じた場合は `project_rules_db_v1.md` を優先する。
