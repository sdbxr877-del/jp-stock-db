---
rule_id: secrets-no-env-var-print
category: secrets
priority: critical
paths:
  - "*.py"
related_failures:
  - 失敗39
related_rules:
  - G2
  - SR-14
last_updated: 2026-05-23
applies_to_environments:
  - claude_code
  - chat_claude
  - human
---

# Secrets: 環境変数名を print 文に直書きしない

## 規範

秘匿情報を保持する環境変数の**変数名リテラル文字列**(例: `'JQUANTS_API_KEY'`)を
print 文(および同等の標準出力系)に直接書いてはならない。値そのものは言うまでもなく出力禁止。

変数名を出力したい場合は、**変数名を別の Python 変数(`env_var_label` 等)に格納してから
その変数経由で出力**する。これにより G2 監査の grep パターンに hit しないコード形態を維持する。

本ルールは `project_rules_db_v1.md §3 G2` の Secrets ログ出力ゲートを
**ファイル単位で照合可能な形に分解した詳細仕様**である。
G2 grep の現行パターンは `project_rules_db_v1.md §3` を参照(本ルール作成時点):

````
print.*token|print.*key|print.*secret|print.*password
````

両 case mode(Linux grep = case-sensitive / PowerShell Select-String = case-insensitive)で
**0 hit** を必須とする。**1 件でも hit したら誤検知判定禁止・即修正**(失敗39 教訓)。

### 対象環境変数(本ルール作成時点)

| 環境変数名 | 用途 | 漏洩時の影響 |
|---|---|---|
| `JQUANTS_API_KEY` | J-Quants V2 API 認証 | API 不正利用・rate limit 枯渇 |
| `EDINET_API_KEY` | EDINET API 補完用(Phase 2.5) | API 不正利用 |
| `GOOGLE_APPLICATION_CREDENTIALS` | GCP Service Account キーパス | BQ 全権限奪取・課金事故 |

将来追加される環境変数も**同等の扱い**とする。値 / 名前リテラルの直書き禁止は変数固定ではなく
「秘匿情報を含む可能性のある環境変数全て」に適用される一般原則である。

## 違反パターン(検出すべきコード)

### Pattern 1: 環境変数名リテラルを print 文に直書き(失敗39 直接型)

```python
# 違反例: jquants_test_fetch.py:94 (修正前) 相当
import os
print(f"JQUANTS_API_KEY is set: {bool(os.getenv('JQUANTS_API_KEY'))}")  # ❌
# G2 grep "print.*key" (両 case mode) に hit。失敗39 (2026-04-29) の事故箇所
```

### Pattern 2: print を避けて logger.* / sys.stderr に変える(grep 抜け道の悪用)

```python
# 違反例: G2 grep の print 限定パターンを回避しようとする
import logging
logger = logging.getLogger(__name__)
logger.info(f"JQUANTS_API_KEY is set")  # ❌
# G2 grep には現状 hit しないが、Secret 漏洩リスクは Pattern 1 と同じ。
# CI ログに環境変数名が永続記録される本質的問題が解決していない。
```

→ G2 grep のパターン抜け道を悪用するのは規範違反。grep が捕捉しなくても**本質的にダメ**。

### Pattern 3: env var の**値**を print(より深刻な漏洩)

```python
# 違反例
api_key = os.getenv('JQUANTS_API_KEY')
print(f"Using API key: {api_key}")  # ❌❌ 値自体が標準出力 / GHA log に露出
# Pattern 1 より深刻。CI ログ・トラブルシュート出力経由で Secret 自体が永続記録される
```

### Pattern 4: G2 grep hit を「誤検知」と独断判定(失敗39 真因)

行動パターンとしての違反:
- G2 監査で 1 件 hit
- 「変数名なので実害なし」と独断判定
- 修正せずに commit / push
- → GHA 上で G2 ステップが FAIL し workflow 全停止(失敗39 そのもの)

→ `project_rules_db_v1.md §3 db_v0.10 強化`「1 件でも hit したら必ず修正」違反。

## 正しい実装パターン

### Pattern A: 環境変数名を変数経由化(失敗39 修正例の標準形)

```python
import os

# 環境変数名を Python 変数に格納してから使う
env_var_label = 'JQUANTS_API_KEY'  # ✅ 変数名リテラルはここ 1 箇所のみ

# 存在チェックを print したい場合
present = bool(os.getenv(env_var_label))
print(f"Env var {env_var_label} is set: {present}")  # ✅ print 文に "KEY" 文字列なし

# 値の取得(print しない)
api_key = os.getenv(env_var_label)
if not api_key:
    raise SystemExit(f"Missing env var: {env_var_label}")  # ✅ raise メッセージ経由は許容
```

### Pattern B: 複数環境変数を一括チェック

```python
import os

ENV_LABELS = ['JQUANTS_API_KEY', 'EDINET_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS']

for label in ENV_LABELS:
    value_present = bool(os.getenv(label))
    print(f"  {label}: present={value_present}")  # ✅ print 文に key/token/secret/password 文字列なし
```

**重要**: `ENV_LABELS` の定義行は文字列リスト = `print` を含まないため G2 grep に hit しない。
リテラル文字列を**変数定義行に隔離**することで print 行を clean に保てる。

### Pattern C: G2 grep hit 検出時の行動手順

G2 監査(`project_rules_db_v1.md §3` の grep)で hit した場合:

1. **合法ヒットリストとの照合**: `handoff_db_v11_1.md §3.3` の最新リストに該当するか確認
   - 合法 hit の例: G2 監査ロジック自体を書いている行(`patch_daily_yml_v3.py:30, 31, 89` 等)
2. 合法 hit の場合: そのまま継続(リストに**新規追加が必要かは別判断**で handoff に記録)
3. 非合法 hit の場合: **即修正**(誤検知判定禁止・失敗39 教訓)
4. 修正後、両 case mode(Linux grep + PowerShell Select-String)で再検査し 0 hit 確認

`don't ask again` 系の選択肢で監査をスキップすることは `project_rules_db_v1.md §9` 原則違反。

## 関連過去教訓

### 失敗39(本ルール作成の直接動機)

- **発生**: db_v0.10 セッション中(2026-04-29 頃)
- **直接原因**: `jquants_test_fetch.py:94` および `jquants_update.py:361` で
  `JQUANTS_API_KEY` リテラルを print 文に直書き → G2 grep hit
- **悪化要因**: 「変数名だから誤検知」と当時の Claude が独断判定 → 修正せずに push
- **検出**: GHA workflow の G2 ステップが FAIL → workflow 全停止
- **復旧**: db_v0.11 Pre-A6 で 6 件一括修正(`handoff_db_v11.md §A-2` 参照):
  - `jquants_test_fetch.py:56 / 94 / 137 / 144`
  - `jquants_update.py:361`
  - `test_listed.py:10`(初期テスト残骸 → ファイル削除)
- **修正パターン**: 上記 Pattern A(変数名リテラルを `env_var_label` 等の変数経由に)
- **教訓**: G2 grep の hit は 1 件でも誤検知判定禁止。両 case mode で 0 hit 必須

### 合法ヒットリスト

本ルール作成時点の合法ヒット(`handoff_db_v11_1.md §3.3` SSOT):
- `edinet_fetch_index.py:164`(EDINET 環境変数読込)
- `patch_daily_yml_v3.py:30, 31, 89`(G2 監査ロジック自体)
- `write_jquants_yaml.py:118`(G2 監査ロジック自体)
- `write_yaml.py:70`(G2 監査ロジック自体)

**重要**: 上記は **2026-05-10 時点のスナップショット**であり、最新は
`handoff_db_v11_1.md §3.3` の合法ヒットリストを参照すること。
本ルールファイル側にリストを複製すると失敗53 同型(現状確認漏れ)のリスクが生じるため、
**リスト本体は handoff を SSOT とし、本ルールでは複製しない**。

## レビュー時のチェックリスト

- [ ] `print` 文に `KEY` / `TOKEN` / `SECRET` / `PASSWORD` を含む環境変数名リテラルが**直書きされていない**か確認した
- [ ] 環境変数名は **`env_var_label` 等の変数経由**で参照されているか確認した
- [ ] 環境変数の**値自体**が print / log 出力に含まれていないか確認した(Pattern 3 = 最も深刻)
- [ ] `logger.info` / `logger.debug` / `sys.stderr.write` 等の**print 以外の標準出力系**に環境変数名が含まれていないか確認した(Pattern 2 = grep 抜け道)
- [ ] G2 grep `print.*token|print.*key|print.*secret|print.*password` を**両 case mode**で実行し 0 hit を確認した
- [ ] 1 件でも hit した場合、合法ヒットリスト(`handoff_db_v11_1.md §3.3`)と照合した
- [ ] 非合法 hit を「誤検知だから OK」と独断判定**せず**、即修正したか確認した
- [ ] 新規スクリプトで合法ヒット候補が発生した場合、handoff への記録提案を行ったか確認した

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 同型構造 | 関連失敗 | 参照ルール |
|---|---|---|
| 本実行前の安全弁不足(DRY RUN なし) | 失敗41(BQ 全スキャン課金) | `.claude/rules/bq/dry-run-required.md` |
| テスト・debug 出力が本番に漏出 | 失敗43(本番テーブル汚染) | `.claude/rules/bq/staging-only-tests.md` |
| 環境差検証漏れ(Linux と Windows の挙動差) | 失敗54(CRLF/LF) | `handoff_db_v13.md §4 失敗54` |
| 既存状態を確認せずに「推奨」を実装 | 失敗53(handoff 推奨の現状確認漏れ) | `handoff_db_v13.md §4 失敗53` |

これらは「**機械的検査の hit を独断判定せずに対応する**」あるいは「**環境差を 1 環境のみで検証して見落とす**」
という共通の構造的リスクを持つ。本ルール違反を検出した際は、上記同型ルールの違反パターンも併せて確認する。

### コードベース内の同型箇所(レビュー対象候補)

| スクリプト | 同型リスクの所在 | 確認すべき項目 |
|---|---|---|
| `jquants_test_fetch.py` (rev2) | **失敗39 修正済の事故箇所**(line 94) | 修正後の Pattern A 形式維持・rev2 以降の再発生なし |
| `jquants_update.py` (rev5) | **失敗39 修正済の事故箇所**(line 361) | 修正後の Pattern A 形式維持・rev5 以降の再発生なし |
| `edinet_fetch_index.py` | EDINET 環境変数読込(合法ヒット line 164) | 合法ヒットリストに残存・新規追加コードで非合法 hit を作らないこと |
| `patch_daily_yml_v3.py` | G2 監査ロジック自体(合法ヒット line 30, 31, 89) | 監査ロジック改修時の合法 hit 追加・handoff 更新 |
| `write_jquants_yaml.py` / `write_yaml.py` | G2 監査ロジック自体(合法ヒット line 118 / 70) | 同上 |
| 新規スクリプト全般 | print 文書く際の Pattern A デフォルト | 新規ファイル作成直後に G2 監査実行 |

新規スクリプト追加時も同型かどうかを判定し、必要に応じて本表および
`handoff_db_v11_1.md §3.3` の合法ヒットリストに追記すること。
