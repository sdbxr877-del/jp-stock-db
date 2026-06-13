---
rule_id: process-powershell-absolute-path
category: process
priority: critical
paths:
  - "*.ps1"
related_failures:
  - "失敗56"
related_rules:
  - "git-explicit-add (§9-5・PowerShell 明示 add の前提)"
  - "encoding/utf8-required (失敗60・Get-Content -Encoding utf8)"
  - "db_v0.16 追加原則 #4 (数値は実機実測で確定)"
  - process-handoff-disk-tracked-distinction
  - process-new-claude-code-session-per-rule
last_updated: 2026-06-13
applies_to_environments:
  - claude_code
  - chat_claude
  - human
---

# PowerShell 絶対パス必須ルール(.NET API / cwd 検算)

## 規範

PowerShell で **.NET 静的 API**(`[System.IO.File]::*` / `[System.IO.Directory]::*` / `[System.Text.*]` のファイル系等)を呼ぶ際は、**必ず絶対パスを渡す**こと。加えて、**新規 PowerShell ウィンドウ起動時は最初に `Get-Location` で cwd を検算**し、`C:\jp-stock-db` であることを確認すること。以下を禁止する:

1. **.NET API への相対パス引き渡し**(`[System.IO.File]::ReadAllBytes('.\src\x.py')` 等)
2. **`cd` 後に「`$PWD` が更新されたから .NET も追従する」と仮定**した相対パス利用
3. **新規ウィンドウで cwd 検算なしにファイル操作を開始**すること
4. **handoff / 検証スニペット設計時に相対パス前提のコマンドを記載**すること(受け手が別 cwd で実行して失敗する)

本ルールは失敗56(PowerShell `cd` と .NET `Environment.CurrentDirectory` の乖離 + ウィンドウ別 cwd 管理ミスにより `[System.IO.File]::ReadAllBytes` が `DirectoryNotFoundException` で計3回失敗した事故)の再発防止規範である。

### $PWD と .NET CurrentDirectory の乖離(技術的根拠)

PowerShell の `Set-Location`(`cd`)は **PowerShell プロバイダの location(`$PWD`)を更新するが、.NET の `[System.Environment]::CurrentDirectory` は更新しない**。これは設計上の意図的な乖離である。結果として:

- **PowerShell ネイティブ cmdlet**(`Get-Content` / `Set-Content` / `Test-Path` 等)は `$PWD` を基準に相対パスを解決する → `cd` 後の相対パスは正しく効く
- **.NET 静的 API**(`[System.IO.File]::ReadAllBytes` 等)は `Environment.CurrentDirectory`(= プロセス起動時の cwd・多くはユーザホーム)を基準にする → `cd` しても相対パスは**ユーザホーム基準のまま**で解決され `DirectoryNotFoundException`

つまり「`cd` したのに .NET 呼出だけ失敗する」という非対称が生じる。失敗56 のエラーパスが `C:\Users\hiroyuki\...` base だったのはこのためである。**.NET API には常に絶対パスを渡す**ことが唯一の確実な回避策となる。

### なぜ本リポジトリで頻発するか(固有の動機)

本プロジェクトは「案 A ハイブリッド」で **PowerShell + Claude Code + 新規ウィンドウ**を頻繁に行き来する。新規 PowerShell ウィンドウはユーザホームから起動するため、`cd C:\jp-stock-db` を忘れると cwd 検算なしのファイル操作が即座に破綻する。さらに検証で `Get-FileHash` や `[System.IO.File]::*` を多用するため、相対パス前提のスニペットは受け手環境で再現性を失う。実際に失敗56 は **第1ルール Phase3 / 第2ルール Phase4 / 第3ルール Phase2 の計3回再発**した(対策確立後は再発なし)。

### 対象範囲

| 対象 | 範囲 |
|---|---|
| 必須 | 全 `.ps1` 内の `[System.IO.*]` / `[System.Text.*]` ファイル系 .NET 呼出 |
| 必須 | 対話 PowerShell での手打ち .NET API 呼出 |
| 必須 | 新規 PowerShell ウィンドウ起動直後の操作(cwd 検算の義務) |
| 必須 | handoff / プロンプトに記載する検証スニペット(相対パス前提を避ける) |
| 対象外 | PowerShell ネイティブ cmdlet のみで完結し `$PWD` 基準で正しく解決される操作(ただし新規ウィンドウの cwd 検算は依然必須) |

### 例外条項

| 例外 | 条件 |
|---|---|
| `$PWD` / `(Get-Location).Path` / `Resolve-Path` で絶対パス化した値を .NET API に渡す | 相対パス文字列を直接渡さず、明示的に絶対パスへ解決していれば可 |
| cmdlet 専用スクリプトで cwd 非依存が自明 | `Get-FileHash`(絶対パス指定)等、相対パスを使わない場合 |

### 主要パラメータ(本ルール作成時点)

| 項目 | 値 |
|---|---|
| 標準作業ディレクトリ | `C:\jp-stock-db` |
| 失敗56 再発回数 | 3(第1ルール Phase3 / 第2 Phase4 / 第3 Phase2) |
| cwd 検算コマンド | `Get-Location`(= `$PWD` 表示) |
| 乖離の根本 | `Set-Location` は `$PWD` 更新 / `Environment.CurrentDirectory` 非更新 |

## 違反パターン(検出すべきコード)

### Pattern 1: .NET API に相対パス(失敗56 の原型)

```powershell
# 違反: cd 後でも .NET は CurrentDirectory(ホーム)基準
cd C:\jp-stock-db
$bytes = [System.IO.File]::ReadAllBytes('.\.claude\rules\process\x.md')
# → DirectoryNotFoundException(base = C:\Users\hiroyuki\...)
```

### Pattern 2: `cd` 後の相対パス前提(乖離の誤認)

```powershell
# 違反: $PWD は更新されたが .NET は追従しないという誤解
Set-Location C:\jp-stock-db
[System.IO.File]::WriteAllBytes('output\result.bin', $data)   # ホーム基準で失敗
```

### Pattern 3: 新規ウィンドウで cwd 検算なし

```powershell
# 違反: 新規ウィンドウはホーム起動。検算せずいきなりファイル操作
git add .claude/rules/process/x.md   # 実は cwd がホームで「fatal: not a git repository」等
```

### Pattern 4: handoff 検証スニペットが相対パス前提

```powershell
# 違反: 受け手が別 cwd で実行すると破綻する記載
(Get-FileHash .\x.md).Hash   # cwd が C:\jp-stock-db でなければ FileNotFound
```
→ handoff には必ず冒頭 `cd C:\jp-stock-db` を併記するか、絶対パスで記す。

## 正しい実装パターン

### Pattern A: .NET API に絶対パス + 冒頭 cwd 検算(標準経路)

```powershell
cd C:\jp-stock-db
Get-Location                                  # C:\jp-stock-db を検算(失敗56 対策)
$path = "C:\jp-stock-db\.claude\rules\process\handoff-disk-tracked-distinction.md"
$bytes = [System.IO.File]::ReadAllBytes($path)   # 絶対パスなら確実
```

### Pattern B: `$PWD` / `Resolve-Path` で絶対パス化してから .NET へ渡す

```powershell
cd C:\jp-stock-db
$abs = (Resolve-Path '.\.claude\rules\process\x.md').Path   # $PWD 基準で絶対化
$bytes = [System.IO.File]::ReadAllBytes($abs)               # 絶対パスなので安全
```
→ どうしても相対表記を起点にする場合は `Resolve-Path` / `(Join-Path $PWD ...)` で絶対化してから .NET に渡す(例外条項①)。

### Pattern C: 新規ウィンドウ冒頭の cwd 確定(人為ミス対策)

```powershell
# 新規 PowerShell ウィンドウは必ずこの2行から開始
cd C:\jp-stock-db
Get-Location   # 出力が C:\jp-stock-db であることを目視確認してから作業
```

### Pattern D: handoff / プロンプトの検証スニペットは絶対パス前提で記載

```powershell
# handoff に書く検証コマンドは冒頭 cd を必ず併記
cd C:\jp-stock-db
(Get-FileHash .\.claude\rules\process\x.md -Algorithm SHA256).Hash
```
→ 受け手がどの cwd から始めても再現するよう、冒頭 `cd` を省略しない(db_v0.16 #4「実機実測」の前提を崩さない)。

## 関連過去教訓

### 失敗56 の出自(handoff_db_v14 §4)

失敗56 は db_v0.14 第1ルール Phase3 のリトライ時に発見。`cd` 後に `[System.IO.File]::ReadAllBytes('.\relative\path')` が `DirectoryNotFoundException` で失敗し、エラーパスの base がユーザホームだった。真因は「`Set-Location` は `$PWD` を更新するが .NET `Environment.CurrentDirectory` は更新しない」という設計上の乖離に、新規ウィンドウの cwd 管理ミス(ホーム起動・cd 忘れ)が重なったもの。責任所在は Web Claude(Phase3 コマンドで相対パスを使用)+ Hiroyuki(ウィンドウ別 cwd 管理)の複合と記録されている。

### 3回再発の経緯

第1ルール Phase3 で初発見後、第2ルール Phase4・第3ルール Phase2 でも再発(計3回)。対策「.NET API は絶対パス + 新規ウィンドウ冒頭 cwd 検算 + handoff スニペットの相対パス前提排除」を原則化して以降は再発ゼロ。本ルールはその原則を機械検出可能なパターンに落とし込んだもの。

### 関連ルール

- `git-explicit-add`(§9-5): PowerShell からの明示 add(Pattern D)も冒頭 `Get-Location` 検算を前提とする(本ルールと併用)
- `encoding/utf8-required`(失敗60): `Get-Content -Encoding utf8` も同じ PowerShell 操作規律の一部
- `process-handoff-disk-tracked-distinction`(失敗55): 状態を実測する `git status` も正しい cwd 前提
- `process-new-claude-code-session-per-rule`(失敗58): セッション/ウィンドウ管理規律の対

## レビュー時のチェックリスト

- [ ] `.ps1` / 手打ちで `[System.IO.*]` / `[System.Text.*]` に**絶対パス**を渡しているか(相対パス直渡しでないか)
- [ ] 相対表記を起点にする場合 `Resolve-Path` / `$PWD` で絶対化しているか
- [ ] 新規 PowerShell ウィンドウ冒頭に `cd C:\jp-stock-db` + `Get-Location` 検算があるか
- [ ] handoff / プロンプトの検証スニペットに冒頭 `cd` が併記されているか(相対パス前提でないか)
- [ ] 「`cd` したから .NET も追従する」という誤った前提に基づいていないか
- [ ] `git add` 等を実行する前に cwd がリポジトリルートであることを確認したか

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 観点 | 関連ルール | 関係 |
|---|---|---|
| PowerShell 操作規律 | `encoding/utf8-required` | `-Encoding utf8` 明示(失敗60)と対 |
| 明示 add の前提 | `git-explicit-add` | PowerShell 明示 add も cwd 検算前提 |
| 実機実測の前提 | db_v0.16 追加原則 #4 | 実測コマンドが正しい cwd で動くこと |
| セッション/ウィンドウ管理 | `process-new-claude-code-session-per-rule` | 環境境界の管理規律 |

### コードベース内の同型箇所(レビュー対象候補)

- 検証用 `.ps1` / Here-String 内の `[System.IO.File]::WriteAllBytes`(失敗59 と併発しやすい箇所)
- handoff §7-A 等の数値確定スニペット: 冒頭 `cd C:\jp-stock-db` の有無
- Claude Code が提案する PowerShell 検証手順: .NET API 利用時の絶対パス化
