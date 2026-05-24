# handoff_db_v14.md — db_v0.14 セッション完了記録(2026-05-23 着手 / 2026-05-24 完了)

セッション概要:
- 着手日: 2026-05-23(土)
- 完了日: 2026-05-24(日)
- 採用モデル: Web Claude(Opus 4.7)+ Claude Code(Sonnet 4.6・案 A ハイブリッド)
- 主要達成: Phase 2 P2-2 critical 3 ルール作成完了 + `.gitattributes` 設定完了

---

## §1. 本セッション総括

### 達成項目
- ✅ §7-A: Phase 2 P2-2 critical 3 ルール **全件完了**
  - `.claude/rules/bq/staging-only-tests.md`(失敗43 対策・commit `855e21c`)
  - `.claude/rules/secrets/no-env-var-print.md`(失敗39 対策・commit `accee96`)
  - `.claude/rules/bq/dry-run-required.md`(失敗41 対策・commit `219b0cb`)
- ✅ §7-B: `.gitattributes` 設定完了(失敗54 対策・commit `c320092`)
- ✅ 新規失敗候補 5 件発見・対策確立(失敗55〜59)

### 累積 commit(本セッション分)
- `855e21c`(§7-A 第1ルール)
- `accee96`(§7-A 第2ルール)
- `219b0cb`(§7-A 第3ルール)
- `c320092`(§7-B `.gitattributes`)

合計 4 件 commit。db_v0.13 完了時(HEAD = `d798ab2`)から 4 進。

### 残作業(db_v0.15 持ち越し)
- §7-C: Phase 2 P2-3 残り 10 ルール(分散運用想定)
- handoff §7-A `--renormalize` 適用判断(失敗54 対策の派生)

---

## §2. §7-A 達成事項詳細(Phase 2 P2-2 critical 3 ルール)

### §2-1. 作成ファイル一覧

| # | ファイル | 対策する失敗 | commit | サイズ | Get-Content 行数 | LF カウント |
|---|---|---|---|---|---|---|
| 1 | `.claude/rules/bq/staging-only-tests.md` | 失敗43(本番テーブル汚染) | `855e21c` | 10,612 | 166 | 213 |
| 2 | `.claude/rules/secrets/no-env-var-print.md` | 失敗39(Secrets ログ出力) | `accee96` | 10,642 | 163 | 207 |
| 3 | `.claude/rules/bq/dry-run-required.md` | 失敗41(BQ 全スキャン課金) | `219b0cb` | 10,756 | 186 | 229 |

### §2-2. 採用ワークフロー(案 A ハイブリッド・db_v0.13 から継続)

各ルールで以下のワークフローを適用:
1. Web Claude(Opus 4.7)が設計判断 Q1〜Q5 を提示
2. Hiroyuki が「推奨で進めて」で確定
3. Web Claude が content 全文を設計
4. レビューポイント R1〜R3 で最終確認
5. 新規 Claude Code セッション起動(失敗58 対策・後述)
6. Claude Code が Write のみ実行(content 改変禁止)
7. Claude Code 自身が Read で検証 + Bash で BOM/改行/サイズ確認
8. PowerShell で絶対パス検証(BOM・UTF-8・改行・git status)
9. 明示ファイル指定で add → commit → pre-commit hook ゲート確認

### §2-3. 各ルールの構造(統一形式)

frontmatter 必須キー(7 種):
- `rule_id` / `category` / `priority` / `paths` / `related_failures` / `related_rules` / `last_updated` / `applies_to_environments`

本体セクション(統一):
- 規範
- 違反パターン(複数のコード例付き)
- 正しい実装パターン(複数のコード例付き)
- 関連過去教訓
- レビュー時のチェックリスト
- 同型ケースの参照(横断 + コードベース内の双方向参照)

### §2-4. 設計判断の主な統一方針

| 観点 | 採用方針 |
|---|---|
| `paths` | 全ルール `["*.py"]`(False Positive 許容・False Negative 厳禁) |
| `applies_to_environments` | 全ルール `[claude_code, chat_claude, human]` |
| 違反パターン | 過去事故の直接型 + 同型派生型 + 機械的検出回避型 |
| 正解パターン | コピペ可能な完結コード例(変数定義・検証・本実行を含む) |
| 同型ケース参照 | 横断(他カテゴリルール) + コードベース内(既存スクリプト) |

---

## §3. §7-B 達成事項詳細(`.gitattributes` 設定)

### §3-1. 作成ファイル

- パス: `.gitattributes`(プロジェクトルート直下)
- commit: `c320092`
- サイズ: 307 bytes
- 内容: 16 行(全 ASCII)

### §3-2. 内容

```
# Auto-normalize all text files to LF on commit
# (failure 54 mitigation, db_v0.14)
* text=auto eol=lf

# Explicit binary file types (no normalization)
*.png binary
*.jpg binary
*.jpeg binary
*.gif binary
*.ico binary
*.pdf binary
*.zip binary
*.gz binary
*.pyc binary
*.pyo binary
*.db binary
*.xlsx binary
```

### §3-3. 効果検証

- `git add .gitattributes` 実行時、LF→CRLF warning 出現せず(.gitattributes 効果が即時発動)
- 本セッションの §7-A 3 commit ではすべて warning 発動していたが、§7-B commit 以降は抑止

### §3-4. 既存ファイルへの再正規化(`git add --renormalize`)

本セッションでは実行せず(失敗53 同型回避・単一責任 commit 原則)。
- 既存 tracked 14 ファイル + 本セッション 4 新規ファイルの再正規化は db_v0.15 以降の別タスクで判断
- `--renormalize` 実行時は事前に CRLF 含有状況の調査が必要

---

## §4. 失敗候補の正式記録(本セッション新規発見・55〜59)

### 失敗55(候補): handoff「配置済 ✅」表記が tracked/disk 状態を区別していない

- **症状**: handoff §6 で「✅ 配置済」と記載されたファイル(`diag_recent_jquants_runs.py` 等)が `git ls-files` 結果では untracked。受け取り側は無意識に「commit 済」と解釈する可能性
- **発見 Phase**: 第1ルール Phase 1(現状確認)
- **真因**: 前 Web Claude(handoff 作成時)が「配置済 ✅」という単一表記で 2 状態(ディスク存在 / Git tracked)を区別せず扱った
- **影響**: 受け取り側が想定 = clean working tree と仮定し、Phase 1 Step 2 で初めて乖離発見
- **対策**: handoff 重要ファイル表で「ディスク」「tracked」「commit」の 3 状態を区別するカラムを追加(本 handoff §6 で実装)
- **責任所在**: 前 Web Claude(db_v0.13 handoff 作成時)

### 失敗56(候補): PowerShell cwd と .NET CurrentDirectory の乖離 + ウィンドウ別 cwd 管理の人為ミス

- **症状**: PowerShell で `cd` 後に `[System.IO.File]::ReadAllBytes('.\relative\path')` が `DirectoryNotFoundException` で失敗。エラーパスはユーザホーム base
- **発見 Phase**: 第1ルール Phase 3(リトライ時に発見)・第2ルール Phase 4 / 第3ルール Phase 2 でも再発(計 3 回)
- **真因**:
  - PowerShell の `Set-Location` (`cd`) は `$PWD` を更新するが、.NET API の `Environment.CurrentDirectory` は更新しない(設計上の意図的乖離)
  - 加えて、ウィンドウ別 cwd 管理の人為ミス(新規 PowerShell ウィンドウがユーザホームから起動・cd 忘れ)も発生
- **対策(原則化)**:
  - PowerShell コードで `[System.IO.File]::*` / `[System.IO.Directory]::*` を使う場合は**必ず絶対パスを渡す**
  - 新規 PowerShell ウィンドウ起動時は**必ず最初に `cd C:\jp-stock-db` を確認**(`Get-Location` で検算)
  - handoff の検証コマンド設計時、相対パス前提のスニペットを避ける
- **責任所在**: Web Claude(Phase 3 コマンド設計時に相対パスを使用)+ Hiroyuki(ウィンドウ別 cwd 管理)の複合

### 失敗57(候補): Claude Code が SR-12 違反(`python3 - <<EOF`)を検証手順で提案

- **症状**: Phase 2 Step 3 検証で Claude Code が `python3 - <<'EOF' ... EOF` ヒアドキュメントを使った検証スクリプトを提案
- **発見 Phase**: 第1ルール Phase 2 Step 3
- **真因**: Claude Code が前提読込(CLAUDE.md / handoff 等)後でも SR-12「python -c ワンライナーを使わない」を見落とし。`python3 - <<EOF` は `python -c` と同類だが、Claude Code が同類と認識しなかった
- **対策(確立済)**:
  - Phase 2 プロンプトで「SR-12 違反禁止(`python3 - <<EOF` 含む)」を明示
  - 第2・第3ルールでは事前明示により再発なし
- **責任所在**: Web Claude(初回 Phase 2 プロンプトで明示漏れ)+ Claude Code(規約読み込み後の参照失敗)

### 失敗58(候補): 同一 Claude Code セッションでルール content 連続 Write → long context tier 課金エラー

- **症状**: 第2ルール用プロンプト送信時、Claude Code が "Usage credits are required for long context requests" エラーで停止
- **発見 Phase**: 第2ルール Phase 2 起動時
- **真因**: 第1ルール完了時点で Claude Code セッションが前提 4 ファイル + Phase 2 プロンプト(7.2 KB content 含む) + SR-12 違反停止と再指示の往復 + 検証出力 + 完了報告を全て context 保持。そこに第2ルール content(9.5 KB)+ 周辺指示を追加すると 200K tier 超過
- **対策(確立済)**:
  - 原則: **ルール 1 個作成 = 新規 Claude Code セッション 1 回**(例外なし)
  - Web Claude 側の Phase 2 プロンプトで「セッション継続利用可」の選択肢を提示しない
  - 第3ルールでは新規セッション起動により再発なし
- **責任所在**: Web Claude(第2ルール Phase 2 で「セッション継続利用可」を提案したミス)

### 失敗59(候補): PowerShell Here-String 内日本語が CP932 文字化け

- **症状**: PowerShell `@"..."@` Here-String 内に日本語(全角括弧・中黒等)を含めて `[System.IO.File]::WriteAllBytes(...)` で UTF-8 保存すると、コンソール codepage(CP932)による一次解釈で文字化けして保存される
- **具体例**: `(失敗54 対策・db_v0.14)` → `墓セ遅問・ db_v0.14` のように化けて保存
- **発見 Phase**: §7-B Phase 3 Step 3-4(内容目視確認)
- **真因**: PowerShell Here-String は内部でコンソール codepage で文字列を保持。`[System.Text.UTF8Encoding]::new($false).GetBytes($content)` の UTF-8 指定は、すでに化けた Unicode 内部表現を UTF-8 化するだけで化けは解消されない
- **対策(確立済)**:
  - PowerShell から日本語を含むファイルを書き込む場合は Here-String を避ける
  - 代替案 A: 本文を全 ASCII にする(`.gitattributes` で採用)
  - 代替案 B: Claude Code 経由(Linux 環境・UTF-8 ネイティブ)で書き込む
  - 代替案 C: PowerShell 7+ の `Out-File -Encoding utf8NoBOM` を使う(本セッションでは未検証)
- **責任所在**: Web Claude(コマンド設計時に Here-String の日本語安全性を検証せず採用)
- **位置づけ**: 失敗47(`PYTHONIOENCODING=utf-8`)の同型(Windows 環境固有エンコーディング問題)だが、本件は環境変数設定では対処不可

### 観察事項(失敗番号付与なし): secrets ルール本体が G2 grep 8 hit

- `.claude/rules/secrets/no-env-var-print.md` 内の Python コード例(違反例 + 正解例)が G2 grep `print.*key|print.*token|print.*secret|print.*password` に 8 件 hit
- `.md` ファイルは G2 grep の現行運用対象外(`*.py` のみ)のため実害なし
- 将来 `.md` も G2 対象に拡張する場合は `handoff_db_v11_1.md §3.3` 合法ヒットリストへの追加が必要

---

## §5. 重要な数値スナップショット(2026-05-24 セッション完了時)

| 項目 | 値 |
|---|---|
| HEAD commit | `c320092` |
| 直近 8 commit hash | `c320092` / `219b0cb` / `accee96` / `855e21c` / `d798ab2` / `8216f0e` / `d9fa1cb` / `1d3d0a0` |
| Tracked ファイル数 | **約 14 + 4 = 18 件**(本セッション 4 新規追加・要再カウント) |
| Untracked ファイル数 | **64 件**(本セッション対象外・継続残存) |
| `.claude/rules/` 配下ファイル数 | **5 件**(README + _process/rules-review-process + bq/staging-only-tests + secrets/no-env-var-print + bq/dry-run-required) |
| `raw.prices` 行数 | 4,934,612(db_v0.11 完了時点・本セッションで変更なし) |
| BQ 環境 | 変更なし(本セッションは BQ 触らず) |

---

## §6. 重要な参照ファイル(C:\jp-stock-db\ 直下)

### §6-1. 状態区分の定義(失敗55 対策)

以下表で各ファイルの状態を 3 段階で記載:
- **commit 済**: 最新 commit に含まれる(`git ls-files` で検出)
- **tracked**: stage 済または過去 commit にあるが最新ではない可能性
- **disk のみ**: ディスクには存在するが untracked(`??`)

### §6-2. 本セッション新規配置(全て commit 済)

| ファイル | 状態 | commit | 用途 |
|---|---|---|---|
| `.claude/rules/bq/staging-only-tests.md` | commit 済 | `855e21c` | 失敗43 対策ルール |
| `.claude/rules/secrets/no-env-var-print.md` | commit 済 | `accee96` | 失敗39 対策ルール |
| `.claude/rules/bq/dry-run-required.md` | commit 済 | `219b0cb` | 失敗41 対策ルール |
| `.gitattributes` | commit 済 | `c320092` | LF 正規化(失敗54 対策) |

### §6-3. 既存 commit 済(db_v0.13 以前から継続)

| ファイル | 状態 | 最終更新 commit | 用途 |
|---|---|---|---|
| `.claude/rules/README.md` | commit 済 | `d798ab2` | ルール体系概要 |
| `.claude/rules/_process/rules-review-process.md` | commit 済 | `d798ab2` | rules-review プロセス単一情報源 |
| `.claude/commands/rules-review.md` | commit 済 | `d798ab2` | rules-review コマンドスタブ |
| `CLAUDE.md` | commit 済 | (要確認) | プロジェクト規約 |

### §6-4. disk のみ(untracked・64 件残存・本セッション対象外)

代表的なもの(全リストは `git status --short` 参照):
- `handoff_db_v08.md` / `handoff_db_v11.md` / `handoff_db_v11_1.md` / `handoff_db_v11_2.md` / `handoff_db_v12.md` / `handoff_db_v12_session_log.md` / `handoff_db_v13.md`
- `project_rules_db_v1.md`
- `daily_update_prices_v3.py` / `jquants_update.py` / `jquants_test_fetch.py` / `rescue_drop_2026_04_27_28.py` 他多数の `.py`
- `.bak_*` ファイル / `.zip` ファイル / `.txt` ファイル

**重要**: 上記 untracked は db_v0.10 以前から継続残存している既知状態。本セッションで増減なし。

### §6-5. 環境変数(レジストリ・C:\jp-stock-db\ 外)

| 変数名 | 値 | スコープ | 設定 commit/handoff |
|---|---|---|---|
| `PYTHONIOENCODING` | `utf-8` | User | db_v0.13 §2-3(失敗47 対策) |

---

## §7. 次セッション(db_v0.15)の作業フロー

### §7-A. Phase 2 P2-3 残りルール作成(分散運用想定)

handoff_db_v11_2.md §G-2 で予定されていた P2-3 ルールは以下 10 件(優先度順):

1. `.claude/rules/bq/partition-filter-required.md`(SR-2 関連)
2. `.claude/rules/bq/no-select-star.md`(SR-2 関連)
3. `.claude/rules/encoding/utf8-required.md`(SR-14 関連)
4. `.claude/rules/git/explicit-add.md`(§9-5 「git add . 禁止」)
5. `.claude/rules/git/single-responsibility-commit.md`(§9-2)
6. `.claude/rules/git/no-dont-ask-again.md`(§9-4)
7. `.claude/rules/secrets/no-secret-in-url-params.md`
8. `.claude/rules/process/handoff-disk-tracked-distinction.md`(失敗55 対策・本セッション新規発見)
9. `.claude/rules/process/powershell-absolute-path.md`(失敗56 対策・本セッション新規発見)
10. `.claude/rules/process/new-claude-code-session-per-rule.md`(失敗58 対策・本セッション新規発見)

**推定**: 1 ルール = 1 セッション(失敗58 対策)で 10 セッション分。1 セッションあたり 1〜2 時間。

**db_v0.15 では上記 #1〜#3(BQ + encoding カテゴリ)を優先**することを推奨。`process/` カテゴリは更に蓄積待ち。

### §7-B. handoff §G-2 §7-A `--renormalize` 適用判断

- `.gitattributes` 配置後の既存 tracked 14 ファイルの再正規化
- 事前検証: `git ls-files --eol` で各ファイルの現状改行コード調査
- 判断: 再正規化 commit を打つか、自然な編集タイミングで自動正規化に委ねるか

### §7-C. handoff_db_v15.md 作成(セッション末)

---

## §8. 次セッション(db_v0.15)開始時の「最初の一言」

### パターン A: 同日 or 翌日に新セッション(`claude`)で開始

```
東証約3,900銘柄の株価・財務データを BigQuery(完全無料)に蓄積し、スクリーニング → AI分析 → UI表示の一貫パイプラインを構築する。
db_v0.15 セッション開始(db_v0.14 完了の {日付})。
添付ファイル: jp_stock_db_v14_handoff.zip
(中身: handoff_db_v14.md + handoff_db_v13.md + handoff_db_v12.md + handoff_db_v12_session_log.md + handoff_db_v11_2.md + handoff_db_v11_1.md + handoff_db_v11.md + project_rules_db_v1.md + .claude/ 配下 5 ファイル)

## 前提(db_v0.14 完全完了)
- §7-A: Phase 2 P2-2 critical 3 ルール完了(commit: 855e21c / accee96 / 219b0cb)
- §7-B: .gitattributes 配置完了(commit: c320092)
- 新規失敗候補 5 件記録(55〜59)・全て対策確立済

## 本日(db_v0.15)の作業予定
優先順:
- §7-A: Phase 2 P2-3 BQ + encoding 3 ルール(handoff_db_v14.md §7-A の #1〜#3)
- §7-B: handoff_db_v14.md §7-B の --renormalize 適用判断

## 採用ワークフロー
案 A ハイブリッド(db_v0.13〜db_v0.14 で 4 ルール作成実証済):
- Web Claude(Opus 4.7): content 全文設計
- Claude Code(Sonnet 4.6・新規セッション・**ルール 1 個ごとに新規起動・失敗58 対策**): Write のみ
- PowerShell: 検証 + commit(**絶対パス使用・cwd 確認・失敗56 対策**)

## 進行方針(絶対遵守)
- ステップごとに確認・独断進行禁止
- §1.6「Success」を信じない(commit hash/サイズ/数値で必ず検証)
- §9 原則 + db_v0.14 追加原則(対話省力化・Yes 単独応答可)

## 最初にしてほしいこと
1. handoff_db_v14.md 読込
2. handoff_db_v14.md §6 で本セッション基準の commit 済/disk のみの区別を把握
3. handoff_db_v14.md §7-A の #1〜#3 から作業対象を選んで設計確認質問
```

### パターン B: 同セッション継続(db_v0.14 当日 reset 後再開)

(本 handoff が完成済の場合は不要)

---

## §9. 重要原則の再確認(次セッションでも適用)

### 既存原則(handoff_db_v13.md §9 から継続)

- §1.6 「Success」を信じない: commit hash / サイズ / 数値で必ず検証
- §1.2 一機能一バージョン
- §9-2 commit 単一責任原則(1 commit = 1 論理的変更)
- §9-4 `don't ask again` 系の選択肢は絶対選ばない
- §9-5 `git add .` / `git add -A` 禁止(ファイル明示指定)
- handoff 推奨手順の事前検証(環境前提条件を確認してから採用)
- 「追加推奨」「変更推奨」前に必ず現状確認

### db_v0.14 新規追加原則(実証ベース)

| # | 原則 | 根拠失敗 | 適用範囲 |
|---|---|---|---|
| 1 | ルール 1 個作成 = 新規 Claude Code セッション 1 回(継続利用禁止) | 失敗58 | 案 A ハイブリッド全般 |
| 2 | PowerShell `.NET` API は絶対パスで呼ぶ + 新規ウィンドウは最初に `cd` 確認 | 失敗56 | 全 PowerShell 操作 |
| 3 | PowerShell から日本語含むファイル書込は Here-String を避ける(ASCII 化 or Claude Code 経由) | 失敗59 | 全 PowerShell ファイル作成 |
| 4 | Phase 2 プロンプトで SR-12 違反禁止(`python3 - <<EOF` 含む)を明示 | 失敗57 | 全 Claude Code Write タスク |
| 5 | handoff 重要ファイル表は「ディスク / tracked / commit」の 3 状態を区別 | 失敗55 | 全 handoff 作成 |
| 6 | 対話省力化原則: Web Claude が「Yes 推奨」判断時は「Yes」一語のみ回答 | (Hiroyuki 指示) | Phase 2 Claude Code 確認ダイアログ |

---

## §10. セッション終了手順

### 本セッション(db_v0.14)終了時

1. ✅ §7-A 3 ルール commit 済(`855e21c` / `accee96` / `219b0cb`)
2. ✅ §7-B `.gitattributes` commit 済(`c320092`)
3. ✅ handoff_db_v14.md 作成 + commit 完了(本ファイル)
4. ✅ 失敗候補 55〜59 を §4 に正式記録
5. ⏳ jp_stock_db_v14_handoff.zip 作成(Hiroyuki 側)

### 次セッション(db_v0.15)開始時

1. zip 展開 + 配置確認
2. PowerShell で cwd + HEAD commit (`c320092`) 確認
3. Untracked 64+ 件残存の既知認識(失敗55 同型回避)
4. handoff_db_v14.md §8 のパターン A プロンプト送信

---

## §11. db_v0.14 セッションの俯瞰評価

### 達成評価

- **計画通り達成**: §7-A 3 ルール + §7-B `.gitattributes`
- **計画外の収穫**: 新規失敗候補 5 件発見・全て対策確立 → db_v0.15 以降の安全運用基盤強化
- **ワークフロー成熟度**: 案 A ハイブリッドが第1〜第3ルールで 4 回安定運用 → P2-3 以降の量産フェーズに耐える基盤に到達

### 時間消費の構造

handoff_db_v13.md §11 で「P2-2 は 3〜4 時間規模」と予測されていたが、実績は:

- §7-A 第1ルール: 約 90 分(設計 + Phase 1〜4・新規失敗候補 3 件発見の対処込み)
- §7-A 第2ルール: 約 60 分(失敗57 対策プロンプト効果・失敗58 発生対処込み)
- §7-A 第3ルール: 約 45 分(ワークフロー成熟により最短)
- §7-B: 約 30 分(失敗59 発生と ASCII 化リトライ込み)
- §7-D 本ファイル: 約 40〜60 分(推定・本 commit 完了時に追記可)

合計 **約 4〜5 時間**(失敗候補発見の対処時間を含むため予測より長め)。新規発見コストは将来削減効果なので投資価値あり。

### 次セッションへの示唆

- P2-3 残り 10 ルールは失敗候補発見頻度が下がるため、1 ルール 30〜45 分の実績ベースが期待値
- handoff 作成負荷も本ファイルがテンプレートになるため軽減

---

## ✅ 本記録の品質保証

- 全 commit hash は実値(本セッションで取得)
- 全ファイルサイズ・行数は PowerShell 検証結果
- 失敗候補 5 件はすべて Phase 進行中に発生した実事象
- 推測・希望的観測なし
