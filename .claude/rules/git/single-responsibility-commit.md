---
rule_id: git-single-responsibility-commit
category: git
priority: critical
paths:
  - "*.py"
  - "*.sh"
  - "*.ps1"
related_failures: []
related_rules:
  - "project_rules_db_v1.md §9-2 (commit 単一責任原則)"
  - "§9-5 (git add . / -A 禁止)"
  - git-explicit-add
  - "§1.2 (一機能一バージョン)"
  - G2
last_updated: 2026-06-01
applies_to_environments:
  - claude_code
  - chat_claude
  - human
---

# commit 単一責任原則ルール

## 規範

1 つの commit は、**1 つの論理的変更のみ**を含むこと(1 commit = 1 論理的変更)。以下を禁止する:

1. **無関係な複数変更の混在**(例: ルール追加とスクリプト修正を 1 commit に同梱)
2. **複数関心事を含む commit message**(例: `fix X and add Y` / 箇条書きで複数項目を列挙)
3. **生成物・中間ファイルとソースの混在**(例: 引継ぎ用中間 `.md` をルール本体と同梱)
4. **無責任な message**(`WIP` / `misc` / `various` / `update` 単体など、変更内容を特定できないもの)
5. **`git commit -a` / `-am` による意図しない変更の混入**(tracked 全変更を暗黙 stage)

本ルールは `project_rules_db_v1.md §9-2`(commit 単一責任原則)を、検証可能な形へ分解した詳細仕様である。
固有の過去事故番号を持たない**予防的規範**であり、`related_failures` は空配列とする
(`git-explicit-add`(§9-5)/ `bq/no-select-star.md`(SR-2)と同型の「事故記録なし予防ルール」)。

### 「1 論理的変更」とは

- ファイル数ではなく**論理的なまとまり**で判断する。1 機能の実装に複数ファイルが不可分に必要な場合、それらは 1 論理変更を成す
- 逆に、同一ファイル内でも無関係な 2 つの修正が混ざれば単一責任違反
- 判定基準: commit message を「`type: 単一の関心事`」で過不足なく記述できるか。`and` が必要なら分割対象

### 本リポジトリでの実証(ルール作成 = 1 commit)

db_v0.15〜db_v0.16 の全ルール作成 commit は、いずれも「1 ルール = `1 file changed`」を達成している:

| commit | ファイル | file changed |
|---|---|---|
| `0f3dd50` | `bq/partition-filter-required.md` | 1 |
| `03fa152` | `bq/no-select-star.md` | 1 |
| `5c213bc` | `encoding/utf8-required.md` | 1 |
| `0fcdcc8` | `git/explicit-add.md` | 1 |

この「1 ルール = 1 セッション(失敗58)= 1 commit(§9-2)」の対応が、レビュー可能性と巻き戻し容易性を担保している。

### 対象範囲

| 対象 | 範囲 |
|---|---|
| 必須 | 全 commit 操作(`.py` の `subprocess` 経由 / `.sh` / `.ps1` / 対話手打ち) |
| 必須 | commit message の構成(複数関心事の混在禁止) |

### 例外条項

| 例外 | 理由 |
|---|---|
| 1 機能に不可分な複数ファイル変更 | 論理的に 1 変更を成す場合に限る(レビューで「1 論理変更」を確認) |
| `git mv`(リネーム)| 1 操作として 1 commit に収まる |
| 初回スキャフォールド | 空リポジトリの初期構造投入は 1 論理変更とみなす(以後は本ルール厳守) |

### 主要パラメータ(本ルール作成時点)

| パラメータ | 値 | SSOT |
|---|---|---|
| 単一責任の検証 | `git diff --cached --name-only` の件数 = 想定件数 | 本ルール Pattern A |
| commit 後検算 | `git log -1 --stat` の `N file(s) changed` | 本ルール Pattern A |
| 明示 add(前提条件)| `git add <明示パス>` | `git-explicit-add.md`(§9-5)|

## 違反パターン(検出すべきコード)

### Pattern 1: 無関係な複数ファイルを 1 commit に混在

```bash
# 違反例: ルール追加とスクリプト修正を同梱
git add .claude/rules/git/explicit-add.md daily_update_prices_v3.py
git commit -m "add rule and fix price script"   # ❌ 2 つの論理変更が混在
```

→ 後から「ルール追加だけ巻き戻す」ことが不可能になり、レビュー単位も崩れる。

### Pattern 2: `git commit -a` / `-am`(暗黙一括で混入)

```bash
# 違反例: tracked 全変更を一括 commit
git commit -am "update"      # ❌ 編集中の無関係ファイルまで混入
```

→ stage 集合を確認しないため、意図しない変更が単一 commit に紛れ込む(§9-5 とも連動)。

### Pattern 3: 複数関心事を含む commit message

```bash
# 違反例: message に複数の関心事
git commit -m "fix typo, add encoding rule, bump version"   # ❌ 3 関心事
```

→ message が `,` や `and` で複数項目を列挙する時点で、論理変更が複数である証左。

### Pattern 4: 生成物・中間ファイルとソースの混在

```bash
# 違反例: 引継ぎ用中間 md をルール本体と同梱
git add .claude/rules/git/explicit-add.md git_explicit_add_content.md
git commit -m "add explicit-add rule"   # ❌ 中間ファイルが history に残る
```

→ 中間 / 生成物(`*_content.md` 等)は commit 対象外(引継ぎ用は disk のみ)。

### Pattern 5: 無責任な message

```bash
# 違反例: 変更内容を特定できない message
git commit -m "WIP"        # ❌
git commit -m "misc"       # ❌
git commit -m "update"     # ❌(対象不明)
```

→ history から変更意図を追えず、巻き戻し判断ができない。

## 正しい実装パターン

### Pattern A: 1 論理変更を stage → 件数検算 → 単一関心 commit(標準経路)

```bash
# ✅ 正しい例
git add .claude/rules/git/single-responsibility-commit.md   # 1 論理変更のみ明示 add(§9-5)
git diff --cached --name-only                               # staged 集合 = 1 件を確認
git commit -m "docs: add .claude/rules/git/single-responsibility-commit.md (§9-2 enforcement)"
git log -1 --stat                                           # "1 file changed" を数値確認
```

- add 対象は 1 論理変更分のみ(明示パス・§9-5 が前提)
- `git diff --cached --name-only` の件数が想定どおりかを commit 前に確認
- commit 後 `git log -1 --stat` で `N file(s) changed` を数値検証

### Pattern B: 混在してしまった変更を分離(stash 経由)

```bash
# ✅ 正しい例: 無関係変更を一時退避してから個別 commit
git stash push daily_update_prices_v3.py     # 無関係変更を退避
git add .claude/rules/git/single-responsibility-commit.md
git commit -m "docs: add single-responsibility-commit rule (§9-2)"
git stash pop                                # 退避分を戻し、別 commit で扱う
```

- handoff_db_v12 の `jquants_update.py` 分離と同型の実例
- 1 作業で複数変更が生じたら、commit 単位で分離する

### Pattern C: commit message の規約(単一関心事)

```
# ✅ 正しい形式: type: 単一の関心事
docs: add .claude/rules/git/single-responsibility-commit.md (§9-2 enforcement)
fix: correct fiscal year label in s12 forecast
refactor: extract verify_utf8 into standalone script
```

- `type: 要約` の 1 行で、1 つの関心事を過不足なく記述
- `and` / `,` で複数項目を列挙する必要が生じたら、commit を分割する合図

### Pattern D: PowerShell での件数検算

```powershell
# ✅ 正しい例
git add .claude/rules/git/single-responsibility-commit.md
$staged = (git diff --cached --name-only | Measure-Object -Line).Lines
Write-Host "staged files: $staged (expected: 1)"
git commit -m "docs: add single-responsibility-commit rule (§9-2)"
git log -1 --stat
```

- stage 件数を数値で確認してから commit
- `Get-Content` 等で日本語を確認する場合は `-Encoding utf8` 明示(失敗60)

## 関連過去教訓

### §9-2 の出自(事故記録なしの予防的規範)

- **位置づけ**: handoff_db_v12.md 以降「commit 単一責任原則: 1 commit = 1 論理的変更」として継続記載
- **実証例**: handoff_db_v12 で `jquants_update.py` を stash 経由で分離し、単一責任を保った(Pattern B の原型)
- **固有失敗番号**: なし(予防原則として確立)→ `related_failures` 空配列

### §9-5(明示 add)との連動

- **関係**: 単一責任 commit は、明示 add(§9-5)で stage 集合を 1 論理変更に限定することが**前提条件**
- **本ルールとの関係**: `git-explicit-add.md` と双方向参照(add の規律 → commit の規律)

### §1.2(一機能一バージョン)との同型

- **関係**: §1.2 は「1 セッション = 1 機能」、§9-2 は「1 commit = 1 論理変更」。粒度は異なるが「変更を 1 つに絞る」同型構造
- **本ルールとの関係**: `general/one-feature-per-version.md`(§1.2)とカテゴリ横断で対応

### 関連ルール

- `project_rules_db_v1.md §9-2`: commit 単一責任原則(本ルールの SSOT)
- `project_rules_db_v1.md §9-5`: `git add .` / `-A` 禁止(明示 add が前提)
- `git-explicit-add.md`: 明示パス add の規範(本ルールと対)
- `general/one-feature-per-version.md`(§1.2): 機能レベルの単一責任(同型)
- `G2`: Secrets 監査(混在 commit は秘匿物の巻き込み経路にもなる)

## レビュー時のチェックリスト

- [ ] この commit が含む論理変更は 1 つだけか確認した
- [ ] commit message が単一の関心事を記述し、`and` / `,` で複数項目を列挙していないか確認した
- [ ] `git diff --cached --name-only` の件数が想定どおり(通常 1 件)か確認した
- [ ] 生成物・中間ファイル(`*_content.md` 等)を巻き込んでいないか確認した
- [ ] `git commit -a` / `-am` を使っていないか確認した(明示 stage 済集合のみを commit)
- [ ] `WIP` / `misc` / `update` 単体のような無責任 message を使っていないか確認した
- [ ] commit 後に `git log -1 --stat` で `N file(s) changed` を数値確認したか
- [ ] 複数変更が生じた場合、stash 等で分離して個別 commit したか(Pattern B)

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 同型構造 | 関連規範 | 参照ルール |
|---|---|---|
| stage 集合を明示確定する(commit の前提) | §9-5 | `git-explicit-add.md` |
| 変更を 1 つに絞る(機能レベル) | §1.2 | `general/one-feature-per-version.md` |
| 1 ルール = 1 セッション(作業レベル) | 失敗58 | `process/new-claude-code-session-per-rule.md`(予定) |
| 混在が秘匿物を巻き込む経路 | G2 / 失敗39 | `secrets/no-env-var-print.md` |

これらは「**変更単位を 1 つに絞り、混在を構造的に禁止する**」という共通のリスク制御構造を持つ(作業 / 機能 / stage / commit の各レイヤ)。

### コードベース内の同型箇所(レビュー対象候補)

| ファイル / スクリプト | 同型リスクの所在 | 確認すべき項目 |
|---|---|---|
| 全 `.py`(`subprocess` 経由 commit を含む)| スクリプト内の `git commit -a` | Pattern 2 適用 |
| 全 `.ps1`(自動化スクリプト)| 一括 commit ロジック | Pattern 2 / D 適用 |
| 自動 commit を行う将来のバッチ | message の単一関心事性 | Pattern C 適用 |
| pre-commit hook | 単一責任を前提とした検証粒度 | stage 集合が 1 論理変更である前提を維持 |

新規スクリプト追加時も本表に追記し、commit 経路ごとの Pattern 適用を判定すること。
