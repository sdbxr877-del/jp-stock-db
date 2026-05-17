---
description: コード変更をルールファイルと照合してチェック(Phase 2 P2-4 で本実装予定)
allowed-tools:
  - Read
  - Bash(git diff *)
  - Bash(git log *)
  - Task
argument-hint: "[--base-commit <sha>]"
status: stub
implementation_phase: P2-4
last_updated: 2026-05-17
---

# /rules-review(スタブ)

差分(デフォルト `HEAD~1`)を `.claude/rules/` の全ルールと照合する Claude Code カスタムスラッシュコマンド。

⚠️ **本ファイルは現在スタブ状態(Phase 2 P2-1 時点)。本実装は Phase 2 P2-4 で行う。**
スタブ実行時の挙動は本ファイル末尾「## 暫定動作」を参照。

## 設計仕様(P2-4 で実装するもの)

### 引数

- `--base-commit <sha>`: 比較起点(デフォルト `HEAD~1`)
- 引数なし: 直前 commit との差分

### 手順(P2-4 で実装する内容)

1. `.claude/rules/_process/rules-review-process.md` を Read
2. `git diff $BASE_COMMIT HEAD --name-only` で変更ファイル一覧を取得
3. `.claude/rules/` 配下の `.md` ファイルを再帰的に列挙(`_process/` `_tests/` `README.md` を除外)
4. 各ルールの frontmatter `paths:` で対象ファイルを絞る
5. frontmatter `category` でグルーピング
6. **カテゴリごとに並列で `Task` サブエージェント起動**
7. 各サブエージェントは「自分のカテゴリのルールだけ」を持って差分をレビュー
8. 違反があれば標準形式(下記)で報告

### 出力形式

違反なし:
```
✅ All rules compliant
```

違反あり:
```
## Rules Compliance Violations

### .claude/rules/bq/staging-only-tests.md
- **Violated rule**: テスト実行は staging テーブル限定
- **Location**: daily_update_prices_v3.py:142
- **Description**: --limit フラグ指定時も raw.prices に書き込んでいる
- **Suggested fix**: --target-table フラグを必須化し、--limit 時はデフォルト raw.prices_test_staging へ
- **Related failure**: 失敗43
```

詳細は `.claude/rules/_process/rules-review-process.md` の Step 5 を参照。

## 暫定動作(スタブ期間中)

P2-4 完了までは、本コマンドを `/rules-review` として呼び出した場合、Claude Code は以下のいずれかの応答を返すべき:

1. 「本コマンドは P2-4 で本実装予定のスタブです。現時点では暫定的に `.claude/rules/_process/rules-review-process.md` の手順を読んで、ユーザーから渡された差分に対し手動で照合します。差分を貼ってください。」と回答
2. または、暫定的に `_process/rules-review-process.md` の手順を実行(並列化なし・順次)

どちらでも構わないが、**「未実装エラー」を返してユーザー作業を停止させてはならない**。

## 関連ドキュメント

- `.claude/rules/_process/rules-review-process.md`: レビュー手順の単一情報源
- `.claude/rules/README.md`: ルール体系の概要
- `handoff_db_v11_2.md §D-3`: 本コマンドの初出仕様
- `handoff_db_v11_2.md §G-2 Task P2-4`: 本実装タスク定義
