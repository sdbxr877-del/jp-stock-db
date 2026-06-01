---
rule_id: encoding-utf8-required
category: encoding
priority: critical
paths:
  - "*.py"
  - "*.md"
  - "*.yml"
  - "*.yaml"
related_failures:
  - 失敗47
  - 失敗54
  - 失敗59
  - 失敗60
related_rules:
  - "project_rules_db_v1.md SR-14 (UTF-8 確認)"
  - SR-14
  - SR-12
  - G1
  - G2
last_updated: 2026-05-24
applies_to_environments:
  - claude_code
  - chat_claude
  - human
---

# UTF-8 エンコーディング必須ルール

## 規範

プロジェクト内の全 `.py` / `.md` / `.yml` / `.yaml` ファイルは、以下 3 条件を満たすこと:

1. **エンコーディング: UTF-8**(Shift-JIS / CP932 / UTF-16 等は禁止)
2. **BOM なし**(先頭 3 バイトが `EF BB BF` でないこと)
3. **改行コード: LF**(CRLF / CR は禁止・`.gitattributes` で自動正規化される前提だが、書込時から LF が望ましい)

本ルールは `project_rules_db_v1.md SR-14`(UTF-8 確認)を**ファイル単位で照合可能な形に分解した詳細仕様**である。
特に Windows PowerShell 経由でファイルを書き込む際の文字化け事故(失敗47 / 59 / 60)が頻発しているため、
書込側プロセスごとの正しい手順を明示する。

### 対象範囲

| 対象 | 範囲 |
|---|---|
| 必須 | `.py` / `.md` / `.yml` / `.yaml`(本リポジトリ内全ファイル) |
| 必須 | `.claude/rules/*.md`(本ルール自身を含む) |
| 必須 | handoff 系 `.md`(全 14 ファイル・disk のみ含む) |

### 例外条項

| 例外 | 理由 |
|---|---|
| `.gitattributes` で `binary` 指定済ファイル(`.png` / `.jpg` / `.pdf` / `.zip` 等) | バイナリ・エンコーディング概念非該当 |
| Windows レジストリエクスポート `.reg` | UTF-16 LE BOM 必須(Windows 公式仕様) |
| `INFORMATION_SCHEMA.*` 出力 / BQ クエリ結果ファイル | システム生成・本ルール対象外 |

### 主要パラメータ(本ルール作成時点)

| パラメータ | 値 | SSOT |
|---|---|---|
| 環境変数 `PYTHONIOENCODING` | `utf-8`(User scope) | db_v0.13 §2-3(失敗47 対策) |
| `.gitattributes` LF 正規化 | `* text=auto eol=lf` | db_v0.14 §7-B(commit `c320092`) |
| 検証スクリプト | `verify_utf8.py`(SR-12 遵守) | `project_rules_db_v1.md L176` |

## 違反パターン(検出すべきコード)

### Pattern 1: BOM 付き UTF-8(`EF BB BF`)

```python
# 違反例: Python で BOM 付き保存
with open('file.py', 'w', encoding='utf-8-sig') as f:  # ❌ utf-8-sig は BOM 付き
    f.write(content)
```

→ G1 構文チェックが Python の `# coding: utf-8` 宣言と衝突して false hit する場合あり。
PowerShell の `Out-File` デフォルトも BOM 付き(`utf8` 指定でも PowerShell 5.x は BOM 付き)で同型。

### Pattern 2: CRLF 改行(Windows ネイティブ・`.gitattributes` 適用前の残存)

```powershell
# 違反例: PowerShell Set-Content デフォルト(Windows 改行)
Set-Content -Path 'file.md' -Value $content  # ❌ CRLF で保存される
```

→ git diff 汚染・Linux 環境で改行表示乱れ・`.gitattributes` 配置後は警告出るが既存 tracked は再正規化必要。

### Pattern 3: Shift-JIS / CP932 で保存(Windows メモ帳デフォルト・失敗47 同型)

```powershell
# 違反例: PowerShell デフォルト書込(コンソール codepage = CP932 のまま保存)
$content | Out-File -FilePath 'file.py'  # ❌ デフォルト encoding が CP932
```

→ Python 実行時 `UnicodeDecodeError`・GitHub Actions Linux 環境で読込失敗。
失敗47 (2026-04 月頃) と同型の Windows 環境固有エンコーディング問題。

### Pattern 4: PowerShell Here-String 経由日本語書込で CP932 一次解釈(失敗59 直接型)

```powershell
# 違反例: Here-String 内に日本語を含めて UTF-8 保存
$content = @"
# タイトル
(失敗54 対策・db_v0.14)
"@
$bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($content)
[System.IO.File]::WriteAllBytes('file.md', $bytes)  # ❌ Here-String 内日本語が CP932 一次解釈で化け済
```

→ 具体例: `(失敗54 対策・db_v0.14)` → `墓セ遅問・ db_v0.14`(失敗59 §4 記録)。
PowerShell Here-String は内部でコンソール codepage で文字列を保持。
`UTF8Encoding` 指定は化けた Unicode 内部表現を UTF-8 化するだけで化けは解消されない。

### Pattern 5: PowerShell `Get-Content` デフォルト読込で表示文字化け(失敗60 直接型)

```powershell
# 違反例: Get-Content デフォルト読込(encoding 未指定)
Get-Content 'file_with_japanese.md'  # ❌ CP932 として誤解釈 → 化け表示
```

→ 具体例: `セッション完了記録` → `縺サ繝・• す繝ァ繝ウ螳御コ・ ィ倅嶸`(失敗60 §補足1 記録)。
**ファイル本体は無事**だが、検証コマンドで化け表示を見て誤判断するリスク。
失敗60 で db_v0.14 セッション末に handoff_db_v14.md 自身の検証時に発覚した。

## 正しい実装パターン

### Pattern A: Python ファイル書込(UTF-8 / LF 明示)

```python
# ✅ 正しい例
with open('file.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

# Python 検証(verify_utf8.py 経由)
# $ python verify_utf8.py *.py
# → ALL UTF-8 OK (SR-14 PASS)
```

- `encoding='utf-8'`: BOM なし UTF-8(`utf-8-sig` は禁止)
- `newline='\n'`: 全環境で LF を強制(Windows でも CRLF 変換されない)

### Pattern B: PowerShell からのファイル書込(`.NET` API 経由・Here-String 日本語禁止)

```powershell
# ✅ 正しい例: 本文が ASCII のみの場合
$content = @"
# Auto-normalize all text files to LF on commit
* text=auto eol=lf
"@
$bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($content)
[System.IO.File]::WriteAllBytes('C:\jp-stock-db\.gitattributes', $bytes)
```

- `[System.Text.UTF8Encoding]::new($false)`: 引数 `$false` = BOM なし
- `[System.IO.File]::WriteAllBytes`: バイナリ書込で encoding 二次変換を回避
- **絶対パス使用**(失敗56 対策)

**日本語を含むファイルは PowerShell 経由で書き込まない**(失敗59 対策):
- 代替 A: 本文を ASCII 化(`.gitattributes` で採用)
- 代替 B: **Claude Code 経由で書き込む**(Linux 環境・UTF-8 ネイティブ・本ルールファイル自身も含む全 `.claude/rules/*.md` がこの方式)

### Pattern C: PowerShell ファイル読込・表示(`-Encoding utf8` 明示・失敗60 対策)

```powershell
# ✅ 正しい例: Get-Content 表示
Get-Content 'C:\jp-stock-db\file.md' -Encoding utf8

# ✅ 正しい例: .NET API 経由読込(検証用)
$content = [System.IO.File]::ReadAllText('C:\jp-stock-db\file.md', [System.Text.Encoding]::UTF8)
```

- `-Encoding utf8`: PowerShell 5.x デフォルト読込 encoding は CP932 のため明示必須
- 恒久対策: PowerShell 7+ に移行(デフォルトが UTF-8)

### Pattern D: 検証は verify_utf8.py 経由(SR-12 遵守)

```powershell
# ✅ 正しい例
python verify_utf8.py *.py
# → ALL UTF-8 OK (SR-14 PASS)
```

- `python -c "..."` ワンライナー禁止(SR-12)
- `python3 - <<EOF` ヒアドキュメント禁止(SR-12 同型・失敗57 で実害確認済)
- 検証スクリプトは `.py` ファイルに集約

## 関連過去教訓

### 失敗47(`PYTHONIOENCODING` レジストリ設定・2026-04 月頃)

- **症状**: Windows コンソールの codepage(CP932)が Python の標準入出力 encoding に影響し、UTF-8 出力が化ける
- **対策**: 環境変数 `PYTHONIOENCODING=utf-8` を User scope で設定(db_v0.13 §2-3)
- **本ルールとの関係**: 環境変数で Python 側を強制 UTF-8 化する基盤。本ルールはファイル単位の規範

### 失敗54(`.gitattributes` で LF 強制・db_v0.14)

- **症状**: Windows で作成した `.py` / `.md` が CRLF で git commit され、Linux 環境で差分汚染
- **対策**: `.gitattributes` で `* text=auto eol=lf` 配置(db_v0.14 §7-B・commit `c320092`)
- **本ルールとの関係**: 改行コード LF 強制の構造的解決。本ルールは書込時点での LF 明示を促す

### 失敗59(PowerShell Here-String 日本語化け・db_v0.14)

- **症状**: PowerShell `@"..."@` Here-String 内日本語が CP932 一次解釈で化けて UTF-8 保存される
- **対策**: PowerShell からの日本語含むファイル書込は Here-String 避ける(db_v0.14 追加原則 #3)
- **本ルールとの関係**: Pattern 4 / Pattern B で正式記載

### 失敗60(PowerShell `Get-Content` デフォルト読込文字化け・db_v0.14 supplement)

- **症状**: `Get-Content` デフォルト読込が CP932 で日本語 UTF-8 ファイルを誤解釈
- **対策**: `Get-Content` は `-Encoding utf8` 明示(db_v0.14 追加原則 #7)
- **本ルールとの関係**: Pattern 5 / Pattern C で正式記載

### 関連ルール

- `project_rules_db_v1.md SR-14`: UTF-8 確認(本ルールの SSOT)
- `project_rules_db_v1.md SR-12`: PowerShell `python -c` ワンライナー禁止(検証経路の制約)
- `project_rules_db_v1.md G1`: 構文チェック(BOM 付きは G1 false hit リスク)
- `project_rules_db_v1.md G2`: Secrets 監査(grep ベース・encoding 誤解釈で false negative)
- `.gitattributes`(commit `c320092`): LF 自動正規化(改行コード強制基盤)
- `verify_utf8.py`: SR-14 検証スクリプト本体(Pattern D の標準経路)

## レビュー時のチェックリスト

- [ ] 全 `.py` / `.md` / `.yml` / `.yaml` の先頭 3 バイトが `EF BB BF`(BOM)になっていないか確認した
- [ ] 全対象ファイルの改行コードが LF(0x0A)のみで CRLF(0x0D 0x0A)を含まないか確認した
- [ ] Python ファイル書込時に `encoding='utf-8'` と `newline='\n'` の両方を明示しているか確認した
- [ ] PowerShell ファイル書込時に `[System.Text.UTF8Encoding]::new($false)` で BOM なし指定しているか確認した
- [ ] PowerShell Here-String 内に日本語を含めていないか確認した(Pattern 4)
- [ ] PowerShell `Get-Content` 使用時に `-Encoding utf8` を明示しているか確認した(Pattern 5)
- [ ] 検証経路が `verify_utf8.py` 経由で `python -c` を使っていないか確認した
- [ ] `PYTHONIOENCODING=utf-8` 環境変数が User scope で設定されているか確認した(Windows の場合)
- [ ] `.gitattributes` の LF 強制設定がリポジトリルートに存在するか確認した

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 同型構造 | 関連失敗 | 参照ルール |
|---|---|---|
| Windows 環境固有のエンコーディング問題 | 失敗47 / 59 / 60 | 本ルール Pattern 3-5 |
| Linux と Windows の挙動差を機械的に解決 | 失敗54(CRLF) | `.gitattributes`(commit c320092) |
| 検証経路の SR-12 遵守(`python -c` 禁止) | 失敗57 | `.claude/rules/bq/dry-run-required.md` 等(全 BQ ルール共通) |
| 機械的検査の hit を独断判定で見逃さない | 失敗39 | `.claude/rules/secrets/no-env-var-print.md` |
| 本実行前の安全弁の機械的強制 | 失敗41 | `.claude/rules/bq/partition-filter-required.md` / `.claude/rules/bq/dry-run-required.md` |

これらは「**Windows / Linux 環境差を構造的に解決する**」あるいは
「**検証経路の標準化(SR-12 遵守)で安全弁を機械化する**」という共通の構造的リスクを持つ。

### コードベース内の同型箇所(レビュー対象候補)

| ファイル / スクリプト | 同型リスクの所在 | 確認すべき項目 |
|---|---|---|
| `verify_utf8.py` | **本ルール Pattern D の模範例**(SR-14 検証スクリプト本体) | 参照模範 |
| 全 `.py` ファイル(Windows 経由作成可能性のあるもの) | 書込時の encoding / newline 指定 | Pattern A 適用 |
| `.claude/rules/*.md`(本ルール自身を含む) | Claude Code 経由 Write の UTF-8 保存 | BOM なし / LF / `verify_utf8.py` 検証 |
| handoff 系 `.md`(disk のみ含む全 14 ファイル) | Web Claude 提示 → Hiroyuki 配置の経路 | PowerShell 経由の場合は Pattern B 適用 |
| `project_rules_db_v1.md` | SSOT として SR-14 定義本体 | 本ルールとの整合性維持 |
| `.gitattributes`(commit c320092) | LF 自動正規化の基盤 | 設定変更時は本ルール改訂と連動 |

新規ファイル追加時も本表に追記し、書込経路ごとの Pattern 適用を判定すること。
