---
rule_id: process-handoff-disk-tracked-distinction
category: process
priority: high
paths:
  - "handoff_*.md"
related_failures:
  - "失敗55"
related_rules:
  - "project_rules_db_v1.md §6 (重要ファイル表の状態区分)"
  - "db_v0.16 追加原則 #3 (handoff は disk のみ)"
  - "db_v0.16 追加原則 #4 (数値は実機実測で確定)"
  - "db_v0.17 追加原則 #4 (件数はカウント基準と時点を明記)"
  - process-powershell-absolute-path
  - process-new-claude-code-session-per-rule
last_updated: 2026-06-13
applies_to_environments:
  - chat_claude
  - human
---

# handoff 状態区分(disk / tracked / commit)必須ルール

## 規範

handoff 文書(`handoff_db_v*.md`)および引継ぎ manifest で各ファイルの状態を記載する際は、**「commit 済 / tracked / disk のみ(untracked)」の 3 状態を必ず区別**して記載すること。以下を禁止する:

1. **「配置済 ✅」等の単一表記**で commit 状態とディスク存在を混同すること
2. **状態カラムを持たないファイル表**(ファイル名と用途のみで Git 状態が不明な表)
3. **実測に基づかない状態の推測記載**(`git ls-files` / `git status --short` を取らずに「commit 済」と断定すること)
4. **3 状態のうち 2 状態のみの区別**(「disk / commit」だけで tracked を省くなど)

本ルールは失敗55(handoff「配置済 ✅」表記が tracked/disk 状態を区別せず、受け手が無意識に commit 済と誤読した事故)の再発防止規範である。`project_rules_db_v1.md §6`(重要ファイル表の状態区分)を、機械的にレビュー可能な記載要件へ分解した詳細仕様にあたる。

### なぜ 3 状態区別が必須か(本リポジトリ固有の動機)

本リポジトリは **untracked が 77 件常駐**している(handoff 系 `.md` / `jp_stock_db_v*_handoff.zip` / 中間 content `.md` / README manifest 等・db_v0.10 以前から既知残存)。この「常時 dirty working tree」が本ルールの構造的前提である。

受け取り側(次セッションの Web Claude / Claude Code / Hiroyuki)が handoff を読む際、ファイル表に「配置済 ✅」とだけ書かれていると、**無意識に「commit 済 = clean working tree に含まれる」と解釈**する。しかし実体は untracked(disk のみ)であることがあり、この乖離は Phase 1 の現状確認まで露見しない。失敗55 はまさにこの誤読で、`diag_recent_jquants_runs.py` 等が「配置済 ✅」と記載されながら `git ls-files` では untracked だった事例である。

77 件もの untracked が常駐する本リポジトリでは、「ディスクに在る」ことと「commit されている」ことは**頻繁に乖離する**。したがって状態は常に 3 つに分けて明示しなければならない。

### 状態定義(3 状態・厳密)

| 状態 | 定義 | 検出コマンド |
|---|---|---|
| **commit 済** | 最新 commit に含まれる(HEAD で追跡可能) | `git ls-files <path>` で出力される / `git log -1 -- <path>` が当該 commit を返す |
| **tracked** | stage 済または過去 commit にあるが最新ではない可能性(modified/staged) | `git status --short <path>` が ` M` / `M ` / `A ` 等を返す |
| **disk のみ** | ディスクに存在するが untracked | `git status --short <path>` が `??` を返す |

「tracked」と「commit 済」は実務上ほぼ同義に扱われがちだが、**stage 済・未 commit**(`A ` や ` M`)を「commit 済」と書くと巻き戻し可能性の判断を誤らせるため、本ルールでは区別を維持する。

### 対象範囲

| 対象 | 範囲 |
|---|---|
| 必須 | 全 `handoff_db_v*.md` のファイル表・状態記載 |
| 必須 | 引継ぎ zip の `README_*manifest*.md`(同梱/非同梱・commit 状態の記載) |
| 必須 | セッション内で「このファイルは○○済」とチャットで状態を報告する場合 |
| 対象外 | 状態に言及しない純粋な設計メモ・content 本文 |

### 例外条項

| 例外 | 条件 |
|---|---|
| 単一状態しか存在しないことが自明なセクション | 例:「本セッション新規 commit(全て commit 済)」と見出しで状態を確定済みの表は、各行へのカラム再掲を省略可。ただし見出しで状態を明示すること |
| commit hash を併記している場合 | commit hash(`9549f84` 等)が併記されていれば「commit 済」は自明。ただし tracked/disk との混在表では依然カラムを推奨 |

### 主要パラメータ(本ルール作成時点)

| 項目 | 値 |
|---|---|
| 現 untracked 件数 | 77(db_v0.18 開始時実測・handoff_db_v17.md disk 配置後) |
| 状態区分の初出 | handoff_db_v14 §6-1(失敗55 対策として導入) |
| カウント基準明記の連動原則 | db_v0.17 追加原則 #4 |

## 違反パターン(検出すべき表記)

### Pattern 1: 単一「配置済 ✅」表記(失敗55 の原型)

```markdown
<!-- 違反: disk 存在と commit 状態を混同 -->
| ファイル | 状態 | 用途 |
|---|---|---|
| diag_recent_jquants_runs.py | ✅ 配置済 | J-Quants 診断 |
```
→ 受け手は「commit 済」と誤読するが、実体は untracked。失敗55 の直接原因。

### Pattern 2: 状態カラムなしのファイル表

```markdown
<!-- 違反: Git 状態が一切不明 -->
| ファイル | 用途 |
|---|---|
| handoff_db_v18.md | 本セッション引継ぎ |
```
→ disk のみか commit 済か判断不能。読み手が推測で補完するリスク。

### Pattern 3: 実測なしの状態推測

```markdown
<!-- 違反: git status を取らずに「commit 済」と断定 -->
secrets ルールは前回 commit したはずなので commit 済。
```
→ db_v0.16 追加原則 #4(数値は実機実測で確定)違反。状態も実測対象である。

### Pattern 4: 2 状態のみの区別(tracked の脱落)

```markdown
<!-- 違反: tracked を省き disk/commit の 2 値に潰す -->
各ファイルは「disk のみ」または「commit 済」のいずれか。
```
→ stage 済・未 commit(`A `)を取りこぼし、巻き戻し判断を誤らせる。

## 正しい実装パターン

### Pattern A: 3 状態カラム付きファイル表 + 取得コマンド明記(標準経路)

```markdown
### §6-2. 本セッション新規配置

| ファイル | 状態 | commit | 用途 |
|---|---|---|---|
| .claude/rules/process/handoff-disk-tracked-distinction.md | commit 済 | a1b2c3d | 失敗55 対策 |
| handoff_db_v18.md | disk のみ | — | 本引継ぎ(disk 運用) |

> 状態は `git status --short` 実測。commit 済は `git ls-files` で確認。
```

### Pattern B: 見出しで状態を確定し本文を簡潔化(例外条項の活用)

```markdown
### §6-2. 本セッション新規 commit(全て commit 済・hash 併記)

| ファイル | commit |
|---|---|
| .../handoff-disk-tracked-distinction.md | a1b2c3d |

### §6-5. disk のみ(untracked・77 件・実測確定)
```
→ 見出しで状態を確定すれば各行カラム省略可(例外条項①)。commit hash 併記で「commit 済」は自明(例外条項②)。

### Pattern C: 件数記載とカウント基準の併記(db_v0.17 追加原則 #4 連動)

```markdown
| 時点 | .claude/rules/ 配下 .md | .claude/ 全体 |
|---|---|---|
| db_v0.18 末 | 15(rules/ のみ基準) | 16 |

> カウント基準: (Get-ChildItem .claude\rules -Recurse -File -Filter *.md).Count
```
→ 状態区分と同様、件数も「基準 + 時点」を明示(handoff_db_v17 §3 reconciliation の前例)。

## 関連過去教訓

### 失敗55 の出自(handoff_db_v14 §4)

失敗55 は db_v0.14 第1ルール Phase 1 で発見。前 Web Claude(db_v0.13 handoff 作成時)が「配置済 ✅」という単一表記で「ディスク存在」と「Git tracked」の 2 状態を区別せず記載した。受け取り側は clean working tree を仮定し、Phase 1 Step 2 の `git status` 実測で初めて乖離(untracked 残存)を発見した。対策として handoff §6 に 3 状態カラムを導入し、以降の handoff(v14〜v17)で運用が定着している。本ルールはその運用を明文化したもの。

### untracked 77 件常駐という構造的背景

`git-explicit-add`(§9-5)が指摘する「untracked 66 件(現 77 件)常駐」は、本ルールの動機と同根である。常時 dirty な working tree では「disk に在る ≠ commit 済」が常態であり、状態の暗黙的同一視が事故を生む。explicit-add は「巻き込み commit」を、本ルールは「状態誤読」を、それぞれ untracked 常駐リスクの別側面として扱う。

### db_v0.16/v0.17 追加原則との連動

- db_v0.16 #3(handoff は disk のみ): handoff 自身が untracked で運用されるため、handoff 内の状態記載は特に誤読されやすい
- db_v0.16 #4(数値は実機実測で確定): 状態も「推測でなく `git status` 実測」で記載するという本ルール Pattern 3 の根拠
- db_v0.17 #4(件数はカウント基準と時点を明記): 状態区分の「数値版」。両者は handoff の記載精度を担保する対の原則

### 関連ルール

- `process-powershell-absolute-path`(失敗56): 状態を実測する `git status` 実行時も絶対パス / cwd 検算が前提
- `git-explicit-add`(§9-5): untracked 常駐という同一の構造的前提を共有
- `git-single-responsibility-commit`(§9-2): commit 状態の正確な記載は単一責任 commit の検証可能性を支える

## レビュー時のチェックリスト

- [ ] ファイル表に「commit 済 / tracked / disk のみ」を区別するカラムがあるか
- [ ] 状態は `git status --short` / `git ls-files` の**実測**に基づくか(推測でないか)
- [ ] 「配置済 ✅」のような状態混同表記を使っていないか
- [ ] tracked(stage 済・未 commit)を commit 済に潰していないか
- [ ] commit 済の行に commit hash を併記しているか(または見出しで状態確定済か)
- [ ] disk のみ(untracked)の件数に取得コマンドと時点を併記しているか(db_v0.17 #4 連動)
- [ ] zip manifest がある場合、同梱/非同梱と commit 状態を区別しているか

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 観点 | 関連ルール | 関係 |
|---|---|---|
| untracked 常駐リスク | `git-explicit-add` | 同一構造前提(巻き込み vs 誤読) |
| 実測主義 | db_v0.16 追加原則 #4 | 状態も数値も実測で確定 |
| 記載基準の明示 | db_v0.17 追加原則 #4 | 状態区分の件数版 |
| PowerShell 実測の前提 | `process-powershell-absolute-path` | `git status` 実行時の cwd 検算 |

### handoff 内の同型箇所(レビュー対象候補)

- handoff_db_v*.md §6(重要な参照ファイル): 全ての状態記載が 3 区分されているか
- 引継ぎ zip の README manifest: 同梱件数とディスク実体件数の基準差(handoff_db_v17 観察事項④の「9 同梱 + 2 非同梱 = 11」型)
- セッション末の commit 一覧: commit hash 併記で commit 済を確定しているか
