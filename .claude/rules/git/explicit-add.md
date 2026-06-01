---
rule_id: git-explicit-add
category: git
priority: critical
paths:
  - "*.py"
  - "*.sh"
  - "*.ps1"
related_failures: []
related_rules:
  - "project_rules_db_v1.md §9-5 (git add . / -A 禁止)"
  - "§9-2 (commit 単一責任原則)"
  - git-single-responsibility-commit
  - G2
last_updated: 2026-06-01
applies_to_environments:
  - claude_code
  - chat_claude
  - human
---

# git add 明示パス必須ルール

## 規範

git のステージング(`git add`)は、**コミット対象を明示ファイルパスで 1 つずつ指定する**こと。以下を禁止する:

1. **`git add .` / `git add -A` / `git add --all`**(カレント以下 / リポジトリ全体の一括 stage)
2. **`git add -u`**(tracked 変更の一括 stage・新規 untracked は拾わないが意図確認を迂回)
3. **ディレクトリ単位 add**(`git add .claude/` のように末端ファイルを確定しない指定)
4. **glob 展開 add**(`git add *` / `git add *.md` のようにシェル展開へ stage 集合を委ねる指定)
5. **`git commit -a` / `git commit -am`**(tracked を暗黙一括 stage して明示 add を構造的に迂回)

本ルールは `project_rules_db_v1.md §9-5`(`git add .` / `-A` 禁止)を、機械検出可能なコマンドパターンへ分解した詳細仕様である。
固有の過去事故番号を持たない**予防的規範**であり、`related_failures` は空配列とする
(commit 済 `.claude/rules/bq/no-select-star.md`(SR-2)と同じ「事故記録なし予防ルール」の前例に準拠)。

### なぜ明示 add が必須か(本リポジトリ固有の動機)

本リポジトリは **untracked が 66 件常駐**している(handoff 系 `.md` / `jp_stock_db_v*_handoff.zip` / `.bak_*` / 実験 `.py` / `.txt` 等・db_v0.10 以前から既知残存)。
この状態で `git add .` を実行すると、これら 66 件が**意図せず一括で stage され**、§9-2(commit 単一責任原則)を一撃で破壊する。
明示パス add は、この「巻き込み事故」を構造的に防ぐ唯一の手段である。
特にルールファイル作成セッションでは「対象ルール 1 ファイルのみを commit する」ことが §9-2 の要請であり、本ルールはその前提条件にあたる。

### 対象範囲

| 対象 | 範囲 |
|---|---|
| 必須 | git 操作を記述する全 `.py`(`subprocess` 経由 git 呼出を含む) |
| 必須 | 全 `.sh` / `.bash`(シェルスクリプト内 git 操作) |
| 必須 | 全 `.ps1`(PowerShell スクリプト内 git 操作) |
| 必須(非ファイル) | 対話セッション(Claude Code / PowerShell / 人間)での手打ち `git add` |

### 例外条項

| 例外 | 理由 |
|---|---|
| 初回リポジトリ作成時の意図的全 add | 該当ファイルが少数かつ全て commit 対象と確定済の場合に限る(レビュー必須) |
| `git add -p`(パッチ単位の対話 stage) | hunk を 1 つずつ確認するため明示原則と矛盾しない |
| CI / 自動生成物のクリーン環境 | untracked が存在しないクリーン clone での自動化は本ルール対象外(ただし本リポジトリの作業環境は非該当) |

### 主要パラメータ(本ルール作成時点)

| パラメータ | 値 | SSOT |
|---|---|---|
| untracked 常駐件数 | 66 件 | handoff_db_v15.md §3 / §7-4 |
| commit 単一責任原則 | 1 commit = 1 論理変更 | project_rules_db_v1.md §9-2 |
| 明示 add の検証コマンド | `git status --short <file>` / `git diff --cached --name-only` | 本ルール Pattern A |

## 違反パターン(検出すべきコード)

### Pattern 1: `git add .` / `-A`(全体一括・最頻出)

```bash
# 違反例: カレント以下を無差別 stage
git add .            # ❌ untracked 66 件を巻き込む
git add -A           # ❌ 削除も含めリポジトリ全体を stage
git add --all        # ❌ -A と同義
```

→ 本リポジトリでは untracked 66 件が即座に stage され、単一責任 commit(§9-2)が崩壊する。

### Pattern 2: `git commit -a` / `-am`(明示 add の迂回・見落としやすい)

```bash
# 違反例: add を経由せず tracked を一括 commit
git commit -a -m "fix"     # ❌ tracked 全変更を暗黙 stage
git commit -am "fix"       # ❌ 同上(-a と -m の結合形)
```

→ `git add` を一切書かないため grep で `git add` を探しても hit しない。`commit -a` の検出が必要(False Negative 厳禁・§2-4)。

### Pattern 3: ディレクトリ / glob add(末端を確定しない指定)

```bash
# 違反例: ディレクトリ指定 / シェル glob
git add .claude/           # ❌ 配下に未確定の untracked が混入し得る
git add *                  # ❌ シェル展開に stage 集合を委譲
git add *.md               # ❌ handoff 系 .md を巻き込む
```

→ 「何が stage されるか」がコマンド時点で確定せず、レビュー不能。

### Pattern 4: Python `subprocess` 経由の一括 add

```python
# 違反例: スクリプト内で git add . を発行
import subprocess
subprocess.run(["git", "add", "."])          # ❌ Pattern 1 と同型
subprocess.run("git add -A", shell=True)     # ❌ shell=True で -A
```

→ `.py` 内に埋め込まれると対話画面に出ず、自動実行で巻き込み事故が起きる。

### Pattern 5: PowerShell スクリプト内の一括 add

```powershell
# 違反例: .ps1 内の git add .
git add .                  # ❌ PowerShell でも挙動は同一
& git add -A               # ❌ 呼出演算子経由でも同型
```

→ 失敗56(絶対パス)対策と併せ、PowerShell 自動化での巻き込みを防ぐ。

## 正しい実装パターン

### Pattern A: 明示ファイルパス add + 前後検証(標準経路)

```bash
# ✅ 正しい例: 対象 1 ファイルを明示 stage し、前後を数値確認
git status --short .claude/rules/git/explicit-add.md      # add 前: ?? (untracked)
git add .claude/rules/git/explicit-add.md                 # 明示パス add
git status --short .claude/rules/git/explicit-add.md      # add 後: A  (staged)
git diff --cached --name-only                             # staged 集合が想定 1 件のみか確認
```

- `git add <相対 or 絶対パス>`: stage 対象を 1 件ずつ確定
- add 直後の `git status --short` で `A`(Added)を目視
- `git diff --cached --name-only` で **staged 集合全体**が意図どおり(想定件数ちょうど)かを確認

### Pattern B: 複数ファイルの明示列挙

```bash
# ✅ 正しい例: 各ファイルを個別に列挙(まとめて指定でも 1 つずつ書く)
git add path/to/file_a.py path/to/file_b.py
git diff --cached --name-only      # 2 件ちょうどであることを確認
```

- 関連する複数ファイルでも、ワイルドカードではなく**全パスを明示列挙**
- 列挙数と `git diff --cached --name-only` の出力件数が一致することを確認

### Pattern C: commit も明示(`-a` を使わない)

```bash
# ✅ 正しい例: add 済のものだけを commit
git add .claude/rules/git/explicit-add.md
git commit -m "docs: add .claude/rules/git/explicit-add.md (§9-5 enforcement)"
git log -1 --stat       # 1 file changed であることを確認(§9-2)
```

- `git commit` に `-a` を付けない(stage 済集合のみを commit)
- commit 後 `git log -1 --stat` で `1 file changed`(単一責任)を数値確認

### Pattern D: PowerShell からの明示 add(失敗56 併用)

```powershell
# ✅ 正しい例: 相対パス明示 add(cwd 検算済前提)
Get-Location                                              # C:\jp-stock-db\ を確認(失敗56 対策)
git status --short .claude/rules/git/explicit-add.md
git add .claude/rules/git/explicit-add.md                # 明示パス(§9-5)
git status --short .claude/rules/git/explicit-add.md
```

- 新規ウィンドウは最初に `Get-Location` で cwd 検算(失敗56 対策)
- `git add .` を絶対に書かない

## 関連過去教訓

### §9-5 の出自(事故記録なしの予防的規範)

- **位置づけ**: handoff_db_v12.md 以降「`git add .` / `git add -A` 禁止: 必ずディレクトリ/ファイル指定で stage(意図せぬ巻き込み防止)」として継続記載
- **固有失敗番号**: なし(実害が発生する前に予防原則として確立)
- **本ルールとの関係**: 予防原則を機械検出可能なコマンドパターンへ分解。`related_failures` は空配列(no-select-star.md と同型の誠実表現)

### untracked 66 件常駐という構造的リスク

- **状態**: handoff 系 `.md` / zip / `.bak_*` / 実験 `.py` 等が db_v0.10 以前から untracked 残存(handoff_db_v15.md §7-4)
- **リスク**: `git add .` 一発で 66 件が stage され、単一責任 commit が崩壊
- **本ルールとの関係**: 明示 add がこの巻き込みを構造的に防ぐ。本リポジトリ固有の最重要動機

### §9-2(commit 単一責任原則)との連動

- **関係**: 本ルール(明示 add)は §9-2(1 commit = 1 論理変更)の**前提条件**
- **実例**: db_v0.15〜db_v0.16 の全ルール作成 commit が「明示パス add → 1 file changed」を達成(`0f3dd50` / `03fa152` / `5c213bc`)
- **本ルールとの関係**: `git-single-responsibility-commit.md` と双方向参照

### 関連ルール

- `project_rules_db_v1.md §9-5`: `git add .` / `-A` 禁止(本ルールの SSOT)
- `project_rules_db_v1.md §9-2`: commit 単一責任原則(明示 add が前提)
- `git-single-responsibility-commit.md`: 単一責任 commit の検証規範(本ルールと対)
- `G2`: Secrets 監査(無差別 add は秘匿ファイル巻き込みの経路にもなり得る)

## レビュー時のチェックリスト

- [ ] `git add .` / `git add -A` / `git add --all` を使っていないか確認した
- [ ] `git add -u` でまとめて tracked を stage していないか確認した
- [ ] `git add .claude/` のようなディレクトリ単位指定をしていないか確認した
- [ ] `git add *` / `git add *.md` のような glob 展開に依存していないか確認した
- [ ] `git commit -a` / `git commit -am` で明示 add を迂回していないか確認した(grep で `git add` が出なくても要確認)
- [ ] `.py`(`subprocess` 経由)/ `.sh` / `.ps1` 内に一括 add が埋め込まれていないか確認した
- [ ] add 後に `git status --short <file>` で `A` を目視確認したか
- [ ] `git diff --cached --name-only` で staged 集合の件数が想定どおりか確認した
- [ ] commit 後に `git log -1 --stat` で `1 file changed`(§9-2)を数値確認したか
- [ ] PowerShell の場合、最初に `Get-Location` で cwd を検算したか(失敗56 併用)

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 同型構造 | 関連規範 | 参照ルール |
|---|---|---|
| 操作対象を明示確定し無差別実行を禁止 | §9-2(commit 単一責任) | `git-single-responsibility-commit.md` |
| 巻き込み防止のため操作を機械的に制約 | 失敗56(絶対パス) | `process/powershell-absolute-path.md`(予定) |
| 無差別操作が秘匿物を巻き込む経路 | G2 / 失敗39 | `secrets/no-env-var-print.md` |
| 「don't ask again」系で安全弁を外さない | §9-4 | `git/no-dont-ask-again.md`(予定) |

これらは「**操作対象を明示確定し、無差別な一括実行を構造的に禁止する**」という共通のリスク制御構造を持つ。

### コードベース内の同型箇所(レビュー対象候補)

| ファイル / スクリプト | 同型リスクの所在 | 確認すべき項目 |
|---|---|---|
| 全 `.py`(git 操作を含むもの) | `subprocess` 経由の `git add .` / `-A` | Pattern 4 適用 |
| 全 `.ps1`(将来の自動化スクリプト) | PowerShell 内 `git add .` | Pattern 5 / D 適用 |
| `.sh` / `.bash`(将来追加分) | シェル内一括 add | Pattern 1-3 適用 |
| pre-commit hook(`.git/hooks/`) | stage 済集合前提の検証ロジック | 明示 add で集合が確定している前提を維持 |

新規スクリプト追加時も本表に追記し、git 操作経路ごとの Pattern 適用を判定すること。
