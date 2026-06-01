---
rule_id: git-no-dont-ask-again
category: git
priority: critical
paths:
  - "*.py"
  - "*.sh"
  - "*.ps1"
related_failures: []
related_rules:
  - "project_rules_db_v1.md §9-4 (don't ask again 系の選択肢は絶対選ばない)"
  - "§1.6 (Success を信じない原則)"
  - git-explicit-add
  - git-single-responsibility-commit
  - secrets-no-env-var-print
  - bq-staging-only-tests
last_updated: 2026-06-01
applies_to_environments:
  - claude_code
  - chat_claude
  - human
---

# 「don't ask again」系の選択肢を選ばないルール

## 規範

破壊的・不可逆・外部影響を持つアクションの承認ダイアログでは、**毎回 1 アクションずつ確認する選択肢のみを選ぶ**こと。承認を恒久化・一括化する選択肢を禁止する:

1. **Claude Code の `don't ask again` 系**(`2. Yes, and don't ask again for <X> commands in this session` 等の永続承認選択肢)
2. **`allow all edits` / `auto-accept edits` モード**(Write/Edit を以後無確認で適用する自動承認状態)
3. **承認プロンプトの一括バイパス**(`always allow` / `remember my choice` / `apply to all` / YOLO mode 等)
4. **git の人間確認を構造的に外す指定**(`git commit --no-verify`(pre-commit hook 迂回)/ `-a`・`-am` の暗黙 stage / hook の永続無効化)
5. **スクリプトでの承認自動回答の常用**(`echo y | <cmd>` / `--yes` / `-y` / `--force` を確認回避目的で恒常使用)

Claude Code の確認ダイアログでは **`1. Yes`(この 1 回のみ承認)だけ**を選ぶ。

本ルールは `project_rules_db_v1.md §9-4`(`don't ask again` 系の選択肢は絶対選ばない)を、環境横断で検出可能な選択肢・コマンドパターンへ分解した詳細仕様である。
固有の過去事故番号を持たない**予防的規範**であり、`related_failures` は空配列とする
(`git-explicit-add`(§9-5)/ `git-single-responsibility-commit`(§9-2)/ `bq/no-select-star.md`(SR-2)と同型の「事故記録なし予防ルール」)。

### なぜ毎回確認が必須か(本リポジトリ固有の動機)

本プロジェクトの安全性は「**提案と確定の分離**」で担保されている。案 A ハイブリッドでは、Claude Code が Write/編集を提案し、**commit は PowerShell 側で人間がクロスチェック**(失敗60 の `Get-Content -Encoding utf8` 照合 + pre-commit hook 目視)して確定する。`don't ask again` / `auto-accept` はこの確認チェックポイントを構造的に消し去り、分離を崩す。

加えて本リポジトリは **untracked が常駐**している(handoff 系 `.md` / `jp_stock_db_v*_handoff.zip` / `.bak_*` / 実験 `.py` 等・件数は次セッション開始時に PowerShell 実測で確定)。auto-accept edits 状態では §9-5(明示 add)/ §9-2(単一責任 commit)の巻き込み事故が**無確認で通過**し、検知不能になる。

本ルールは §1.6「Success を信じない原則」と同根である。自動承認は「数値・hash・ファイル状態で検証する前に操作を確定させる」ため、§1.6 の検証義務そのものを迂回する経路になる。

### 対象範囲

| 対象 | 範囲 |
|---|---|
| 必須(対話) | Claude Code の全 Write / Edit / Bash 承認ダイアログ(永続承認を選ばない) |
| 必須(対話) | git commit / push の確認、pre-commit hook の人間確認 |
| 必須(対話) | PowerShell / 人間操作での破壊的コマンド承認 |
| 必須(ファイル) | git 操作を記述する `.py`(`subprocess` 経由)/ `.sh` / `.ps1`(確認回避フラグの常用検出) |
| 必須(設定) | Claude Code / git / CLI の設定ファイルに永続 auto-allow を書き込まないこと |

### 例外条項

| 例外 | 理由 |
|---|---|
| 読み取り専用・冪等・課金ゼロの操作の 1 回承認(`1. Yes`) | 1 アクション承認は本ルール対象外。**永続化(don't ask again)だけ**を禁止する |
| `git add -p` のパッチ単位対話 stage | hunk を 1 つずつ確認するため毎回確認原則と矛盾しない |
| CI / クリーン clone の非対話自動化 | 対話する人間が存在しない環境(本リポジトリの作業環境は非該当・原則 per-action 確認を維持) |

「危険でないから一括承認してよい」という判断は本ルールでは採用しない。安全な操作でも `don't ask again` を選ぶ習慣自体が、後続の破壊的操作での誤承認を誘発するため、選択肢の永続化を一律に避ける。

### 主要パラメータ(本ルール作成時点)

| パラメータ | 値 | SSOT |
|---|---|---|
| Claude Code で選ぶ選択肢 | `1. Yes` のみ | project_rules_db_v1.md §9-4 |
| commit 確定の主体 | PowerShell 側(人間クロスチェック) | handoff_db_v16.md §5 追加原則 #2 |
| hook 迂回の禁止 | `--no-verify` 不使用 | 失敗60(encoding クロスチェック) |
| untracked 常駐 | 実測で確定(要再カウント) | handoff_db_v16.md §3 / 追加原則 #4 |

## 違反パターン(検出すべき選択・コード)

### Pattern 1: Claude Code の永続承認選択肢(最頻出・対話)

```text
# Claude Code の承認ダイアログで以下を選ぶのは違反
2. Yes, and don't ask again for edit commands in this session   # ❌ 永続承認
3. Yes, allow all edits this session                            # ❌ 一括承認
```

→ 以後の Write/Edit が無確認で通過し、§9-5 / §9-2 の巻き込みと §1.6 の検証義務迂回を同時に招く。正解は `1. Yes` のみ。

### Pattern 2: auto-accept / allow-all モードの常用(対話・設定)

```text
# モード切替・設定での一括承認は違反
auto-accept edits: ON          # ❌ 編集を以後無確認適用
"always allow" を選択           # ❌ 承認の恒久化
"apply to all" / "remember"     # ❌ 選択の永続化
```

→ チェックポイントが消え、提案と確定の分離(案 A ハイブリッドの安全弁)が崩壊する。

### Pattern 3: git の人間確認を外す指定(対話・スクリプト)

```bash
# 違反例: hook 迂回・暗黙 stage で人間確認を構造的に外す
git commit --no-verify -m "fix"   # ❌ pre-commit hook(失敗60 照合)を迂回
git commit -am "fix"              # ❌ 暗黙 stage + 確認省略(§9-5 / §9-2 と二重違反)
git config core.hooksPath /dev/null  # ❌ hook の永続無効化
```

→ `--no-verify` は失敗60 のクロスチェックを飛ばす。grep で `git add` を探しても出ないため、`--no-verify` / `commit -a` の検出が必要(False Negative 厳禁)。

### Pattern 4: スクリプトでの承認自動回答(`.py` / `.ps1` / `.sh`)

```python
# 違反例: 確認プロンプトを自動 yes で潰す
import subprocess
subprocess.run("echo y | dangerous_cmd", shell=True)   # ❌ 確認を自動承認
subprocess.run(["rm", "-rf", path, "--force"])         # ❌ 強制で確認省略
```

→ `.py` / スクリプト内に埋め込まれると対話画面に出ず、自動実行で不可逆操作が無確認で走る。

### Pattern 5: PowerShell での確認回避フラグ常用(`.ps1` / 対話)

```powershell
# 違反例: PowerShell で確認を一律無効化
Remove-Item .\target -Recurse -Force -Confirm:$false   # ❌ 確認の一律無効
$ConfirmPreference = 'None'                             # ❌ セッション全体で確認停止
```

→ 失敗56(絶対パス)対策と相反する。cwd 誤認時に `-Confirm:$false` が走ると、意図しない範囲を無確認で破壊する。

## 正しい実装パターン

### Pattern A: Claude Code は毎回「1. Yes」のみ(標準経路)

```text
# ✅ 正しい選択: この 1 回だけを承認する
1. Yes                          # ← これのみを選ぶ
# 2 / 3(don't ask again / allow all)は絶対に選ばない
```

- Write / Edit / Bash の各確認で、**毎回 `1. Yes`** を選ぶ
- 「同じ確認が何度も出て手間」でも永続承認に逃げない(§1.6 の検証チェックポイントを保つ)

### Pattern B: 破壊的操作は per-action 確認 + 数値検証(§1.6 併用)

```bash
# ✅ 正しい例: 1 操作ごとに確認し、結果を数値で検証する
git status --short .claude/rules/git/no-dont-ask-again.md   # 操作前の状態を確認
git add .claude/rules/git/no-dont-ask-again.md              # 明示パス add(§9-5)
git diff --cached --name-only                               # staged 集合 1 件を検算
```

- 各ステップで状態を確認してから次へ進む(独断進行禁止)
- 「成功」表示ではなく `git status` / `git diff --cached` の出力で確定を判断(§1.6)

### Pattern C: commit は PowerShell 側で human クロスチェック(案 A 分離維持)

```powershell
# ✅ 正しい例: hook を通し、人間が出力を目視確認してから確定
Get-Location                                                # cwd 検算(失敗56)
git add .claude/rules/git/no-dont-ask-again.md              # 明示 add(§9-5)
git commit -m "docs: add .claude/rules/git/no-dont-ask-again.md (§9-4 enforcement)"
git log -1 --stat                                           # 1 file changed を目視(§9-2)
```

- commit の確定主体は PowerShell 側の人間(handoff §5 追加原則 #2)
- pre-commit hook の出力(G1 / G2 / SR-14)を人間が PASS 確認してから次へ

### Pattern D: hook は `--no-verify` せず必ず通す(失敗60 連動)

```bash
# ✅ 正しい例: hook を迂回しない / 失敗時は修正してから再 commit
git commit -m "docs: add .claude/rules/git/no-dont-ask-again.md (§9-4 enforcement)"
# hook が FAIL したら --no-verify で押し通さず、原因(encoding 等)を修正して再実行
```

- `--no-verify` を使わない。hook FAIL は「迂回」ではなく「修正」で解消する
- encoding 不一致は `Get-Content -Encoding utf8`(失敗60)で原因を特定してから再 commit

## 関連過去教訓

### §9-4 の出自(事故記録なしの予防的規範)

- **位置づけ**: handoff_db_v12.md §9 第4項「`don't ask again` 系の選択肢は絶対選ばない: 全ての破壊的アクションは毎回確認を取る運用を維持」として db_v0.12 で確立
- **固有失敗番号**: なし(実害が発生する前に予防原則として確立)
- **本ルールとの関係**: 予防原則を環境横断の選択肢・コマンドパターンへ分解。`related_failures` は空配列(`git-explicit-add` / `git-single-responsibility-commit` と同型の誠実表現)

### db_v0.13 での実証

- **内容**: handoff_db_v13.md §9 第4項で、Claude Code の Write 確認・git commit 確認において**選択肢 2(don't ask again)を明示的に拒否**して原則を実証
- **本ルールとの関係**: 「対話のたびに `1. Yes` を選ぶ」運用が既に複数セッションで実績化(Pattern A)

### §1.6(Success を信じない原則)との連動

- **関係**: 自動承認は「数値・hash・ファイル状態で検証する前に操作を確定」させ、§1.6 の検証義務を構造的に迂回する
- **本ルールとの関係**: per-action 確認(Pattern B)が §1.6 の検証チェックポイントを物理的に確保する

### explicit-add / single-responsibility-commit との連動

- **関係**: auto-accept edits 状態では §9-5(明示 add)/ §9-2(単一責任 commit)の巻き込みが無確認で通過し、両ルールの明示性が無効化される
- **本ルールとの関係**: `git-explicit-add.md` の「同型ケース参照」表が本ルールを `git/no-dont-ask-again.md(予定)`として予約済 → 本ルール完成で実体化

### 関連ルール

- `project_rules_db_v1.md §9-4`: `don't ask again` 系の選択肢は絶対選ばない(本ルールの SSOT)
- `§1.6`: Success を信じない原則(per-action 確認が検証義務を担保)
- `git-explicit-add.md`: 明示 add(auto-accept はこの明示性を破壊)
- `git-single-responsibility-commit.md`: 単一責任 commit(同上)
- `secrets/no-env-var-print.md`: `don't ask again` 系で監査をスキップすることは §9 原則違反(本ルールと双方向)
- `bq/staging-only-tests.md`: 承認が無い場合は実行禁止・`don't ask again` 系は §9 原則により絶対拒否(本ルールと双方向)

## レビュー時のチェックリスト

- [ ] Claude Code の承認ダイアログで `2 / 3`(don't ask again / allow all)を選んでいないか確認した
- [ ] auto-accept edits / always allow / apply to all を有効化していないか確認した
- [ ] `git commit --no-verify` で pre-commit hook を迂回していないか確認した
- [ ] `git commit -a` / `-am` で暗黙 stage + 確認省略をしていないか確認した(grep で `git add` が出なくても要確認)
- [ ] hook を永続無効化(`core.hooksPath` 改変等)していないか確認した
- [ ] `.py` / `.sh` / `.ps1` 内に `echo y |` / `--yes` / `-y` / `--force` を確認回避目的で常用していないか確認した
- [ ] PowerShell で `-Confirm:$false` / `$ConfirmPreference='None'` を一律無効化していないか確認した
- [ ] commit の確定を PowerShell 側の人間クロスチェック経由で行ったか(案 A 分離)
- [ ] hook FAIL を迂回せず修正で解消したか(失敗60 連動)
- [ ] per-action 確認の結果を `git status` / `git diff --cached --name-only` の出力で検証したか(§1.6)

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 同型構造 | 関連規範 | 参照ルール |
|---|---|---|
| 操作対象を明示確定し無差別実行を禁止 | §9-5(明示 add) | `git-explicit-add.md` |
| 1 操作 = 1 論理変更で混入を防ぐ | §9-2(単一責任) | `git-single-responsibility-commit.md` |
| 承認なしの実行を禁止し監査を維持 | §9 原則 | `secrets/no-env-var-print.md` |
| 承認が無い場合は実行禁止 | §9 原則 | `bq/staging-only-tests.md` |
| 検証前に操作を確定させない | §1.6 | （全ルール共通の検証義務） |

これらは「**承認・検証のチェックポイントを構造的に保持し、無確認・一括での確定を禁止する**」という共通のリスク制御構造を持つ。

### コードベース内の同型箇所(レビュー対象候補)

| ファイル / 経路 | 同型リスクの所在 | 確認すべき項目 |
|---|---|---|
| 全 `.py`(git / 破壊的操作を含むもの) | `subprocess` 経由の `--force` / `echo y |` | Pattern 4 適用 |
| 全 `.ps1`(将来の自動化スクリプト) | `-Confirm:$false` / `$ConfirmPreference='None'` | Pattern 5 適用 |
| `.sh` / `.bash`(将来追加分) | `--yes` / `-y` の確認回避常用 | Pattern 3-4 適用 |
| Claude Code セッション(対話) | 承認ダイアログでの永続承認選択 | Pattern 1-2 / A 適用 |
| pre-commit hook(`.git/hooks/`) | `--no-verify` での迂回 | Pattern 3 / D 適用 |

新規スクリプト・新規セッション運用を追加する際も本表に追記し、承認経路ごとの Pattern 適用を判定すること。
