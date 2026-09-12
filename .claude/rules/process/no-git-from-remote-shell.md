---
rule_id: process-no-git-from-remote-shell
category: process
priority: high
paths: []
related_failures:
  - "OPS-01"
related_rules:
  - "process/powershell-absolute-path"
  - "git/explicit-add"
applies_to_environments: [claude_code, chat_claude, human]
scope: global
source_project: 横断（開発環境）
vault_version: 1.0
vault_status: active
vault_imported: 2026-08-31
origin_path: (新規・OPS-01 対策)
last_updated: 2026-08-31
---

# リモートシェル（Cowork / サンドボックス）から git コマンドを実行しない

<!-- portability-note -->
> **他プロジェクトでの読み替え** — 本ルールは `second-brain` から配布されている。
> 文中の `SR-xx` / `G-x` / `失敗NN` / `handoff_db_vNN.md` / `project_rules_db_v1.md` は
> **発祥プロジェクトでの出自の記録**であり、参照先が自プロジェクトに存在しなくてもよい。
> **規範・違反パターン・チェックリストはそのまま有効**。教訓の原文は
> `C:\second-brain\20_failures\` にある。
<!-- portability-note -->



## 規範

削除が禁止されたサンドボックス（Cowork の `device_bash` 等）から、ユーザPC上の
git リポジトリに対して **git コマンドを実行しない**。読み取り目的の `git status` も含む。

理由は「**作れるが消せない**」という環境の非対称性。`git status` は index 更新のために
`.git/index.lock` を作るが、削除できないため残留し、**以降の git 操作が全て失敗する**。

git 操作（status / add / commit / push）は **PowerShell から人間が実行する**。
これは `git/explicit-add`・`git/single-responsibility-commit` の「提案と確定の分離」とも一致する。

## 違反パターン(検出すべきコード)

### Pattern 1: 状態確認のつもりの git status
```bash
# 違反例（リモートシェル上）
git status --short          # index.lock を作り、消せずに残す
git diff                    # 同上（index を触る場合がある）
```

### Pattern 2: リモートシェルからの commit
```bash
# 違反例
git add -A && git commit -m "wip"   # explicit-add 違反でもある
```

## 正しい実装パターン

```bash
# ✅ 変更の有無はファイルシステムで見る（git を呼ばない）
find .claude/rules -name "*.md" -newer CLAUDE.md
diff -r <配布元> <配布先>
ls -la .git/index.lock       # 残留チェックだけは安全（読むだけ）
```

```powershell
# ✅ git は人間が PowerShell から実行する
cd C:\jp-stock-db
git status
git add .claude\rules\shell\no-python-c-oneliner.md
git commit -m "rules: add SR-12 rule file"
```

## 万一 index.lock が残ったら

1. `ls .git/index.lock` で存在を確認
2. 他の git プロセスが動いていないことを確認してから PowerShell で削除
   `Remove-Item C:\<project>\.git\index.lock`
3. `git status` が通ることを確認する（**通って初めて復旧**）

## 関連過去教訓

- [[OPS-01]]: `git status` の index.lock が残留し git が使用不能寸前になった

## レビュー時のチェックリスト

- [ ] 手順書・スクリプトにリモートシェルからの git 実行が混ざっていないか
- [ ] 状態確認を git 以外の手段（ls / find / diff）で代替できないか
- [ ] git 操作は人間が PowerShell から実行する前提で書かれているか
