---
rule_id: bq-staging-only-tests
category: bq
priority: critical
paths:
  - "*.py"
related_failures:
  - 失敗43
related_rules:
  - "SR-19 (案・project_rules_db_v1.md 改訂時に正式採番予定)"
  - SR-11
  - G3
applies_to_environments:
  - claude_code
  - chat_claude
  - human
last_updated: 2026-05-23
---

# BQ テスト実行は staging テーブル限定

## 規範

BigQuery の本番テーブル(`raw.prices` / `raw.tickers` / `raw.financials`)への
**書込系操作(INSERT / UPDATE / DELETE / MERGE / LOAD / TRUNCATE)**は、
GitHub Actions の scheduled cron(production workflow)からのみ実行を許可する。

開発者・Claude Code・チャット Claude が手動またはセッション内で実行するテスト実行
(`--limit N` / `--ticker T` / `--dry-run` / `--debug` 等のフラグを伴う実行を含む)は、
必ず staging テーブルへ向けて書き込むこと。本番テーブルへ書き込む場合は、
**明示フラグ(例: `--prod-write`)とユーザの事前承認**を両方満たすこと。

本ルールの対象は **BQ に INSERT / MERGE / LOAD / DML を発行する全 Python スクリプト**である。
`paths: "*.py"` で広く拾い、レビュー時に対象外(BQ 書込のない pure SELECT スクリプトなど)を
人間判断で除外する運用とする(False Positive 許容・False Negative 厳禁)。

### 対象テーブル(本ルール作成時点)

| 区分 | テーブル名 | 備考 |
|---|---|---|
| 本番 | `raw.prices` | 失敗43 の事故対象 |
| 本番 | `raw.tickers` | 上場銘柄マスタ |
| 本番 | `raw.financials` | 財務データ |
| (旧本番) | `raw.prices_old` | 未 DROP・将来 DROP 予定。書込禁止 |
| staging(稼働中) | `raw.prices_jquants_staging` | jquants_update.py 用ステージング(TRUNCATE 運用) |
| staging(計画) | `raw.prices_test_staging` | Phase 3.4 D6.1 で新設予定。テスト系の primary 書込先 |

## 違反パターン(検出すべきコード)

### Pattern 1: テスト用フラグの実行が本番テーブルに書き込む(失敗43 直接型)

```python
# 違反例: daily_update_prices_v3.py 相当
parser.add_argument("--limit", type=int, default=None)
parser.add_argument("--ticker", type=str, default=None)
args = parser.parse_args()

if args.limit:
    rows = rows[:args.limit]
if args.ticker:
    rows = [r for r in rows if r["ticker"] == args.ticker]

# テスト実行でも target が本番ハードコード ❌
client.load_table_from_dataframe(df, "raw.prices").result()
```

→ 失敗43 (2026-04-29) と同型の事故再発リスク。

### Pattern 2: target テーブル名がハードコードで切替不能

```python
# 違反例
TABLE_ID = "raw.prices"  # ❌ ハードコード・テスト時にも上書き不能
# --target-table フラグ無し・テスト系の分岐ロジック無し

client.query(f"INSERT INTO {TABLE_ID} ...").result()
```

### Pattern 3: 診断 / 補修系スクリプトが本番テーブルを直接書き換える

```python
# 違反例: diag_xxx.py / fix_xxx.py
sql = "DELETE FROM raw.prices WHERE date = '2026-04-27'"
client.query(sql).result()  # ❌ 本番直接書込・承認フラグ無し
```

`rescue_*.py` のように `--confirm` フラグで明示的に本番書込を許可する設計は本ルールの**例外**として許容するが、
スクリプト先頭の docstring と `--help` 出力で**「本番書込スクリプト」である旨**を明示すること。

### Pattern 4: Claude Code 自律実行による本番書込(承認手順スキップ)

```python
# 違反例: Claude Code が独断で実行
# - DRY RUN 結果未提示
# - ユーザの「実行してよい」未取得
# - そのまま client.query(sql).result() を発行
```

→ `handoff_db_v11_1.md §5.1`(本番テーブル書込は事前承認制)の違反。

## 正しい実装パターン

### Pattern A: テストフラグ検出 → 強制 staging ルーティング

```python
import argparse

TABLE_PROD = "raw.prices"
TABLE_STAGING_JQUANTS = "raw.prices_jquants_staging"  # 稼働中
TABLE_STAGING_TEST = "raw.prices_test_staging"        # Phase 3.4 D6.1 で新設予定

parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=None)
parser.add_argument("--ticker", type=str, default=None)
parser.add_argument("--target-table", type=str, default=None)
parser.add_argument("--prod-write", action="store_true",
                    help="Explicit flag to allow writing to production raw.* tables.")
args = parser.parse_args()

# テスト系フラグ検出
is_test_mode = (args.limit is not None) or (args.ticker is not None)

if args.target_table:
    target = args.target_table
elif is_test_mode:
    # テストフラグ時は target 未指定でも強制 staging
    target = TABLE_STAGING_TEST  # 新設後。それまでは TABLE_STAGING_JQUANTS で代用
    print(f"[INFO] Test mode detected (--limit/--ticker), forced to staging: {target}")
elif args.prod_write:
    target = TABLE_PROD
    print(f"[WARN] Writing to PRODUCTION table: {target}")
else:
    raise SystemExit("Specify --target-table or --prod-write explicitly.")

# 書込実行(target をログ出力してから)
print(f"[INFO] Writing {len(df)} rows to {target}")
client.load_table_from_dataframe(df, target).result()
print(f"[INFO] Write complete: {target} ({len(df)} rows)")
```

### Pattern B: Claude Code 実行時の対話パターン

Claude Code が本番テーブル書込を含む処理を実行する場合は、
`handoff_db_v11_1.md §5.1` に従い以下を順に提示:

1. 「これから実行する操作: `INSERT INTO raw.prices VALUES ... (N rows)`」を明示
2. DRY RUN 結果(`total_bytes_processed`, 投入予定件数)を提示
3. 期待値と実測値の整合確認(投入対象日 / ticker / 件数の事前検算)
4. **ユーザの「実行してよい」を待つ**
5. 承認後に本実行・実行後 summary 提示

承認が無い場合は実行禁止。`don't ask again` 系の選択肢は `project_rules_db_v1.md §9` 原則により絶対拒否。

## 関連過去教訓

### 失敗43(本ルール作成の直接動機)

- **発生日時**: 2026-04-29(db_v0.10 セッション中)
- **直接原因**: `daily_update_prices_v3.py` の `--limit 20` および `--ticker 7203` で
  04-27 / 04-28 日付分のテスト実行を行ったが、target テーブルが本番 `raw.prices` で固定だったため、
  テスト残骸 **42 行**(20 銘柄 × 2 日 + 7203 × 2 日)が本番に残留
- **発覚タイミング**: db_v0.11 セッション(2026-05-10)で「最新日 04-28 が満数(4,300+件)かどうか」の
  full_count 検証で異常検知
- **復旧**: `rescue_drop_2026_04_27_28.py --confirm` で 04-27 / 04-28 完全空白化 → 最新日 04-24 に正常化
- **構造的対策の所在**: 本ルール本体 + `handoff_db_v11_1.md §5.1 / §5.2`(Claude Code 向け絶対命令)
- **継続発動策**: `handoff_db_v11.md §C-7` 新設(セッション開始時の 04-27/04-28 空白確認手順)

### SR-19(案)としての位置づけ

本ルールは `project_rules_db_v1.md` への **SR-19 採番候補**である。
db_v0.14 の範囲では `project_rules_db_v1.md` 改訂は実施しないため、
正式な SR-19 採番は別セッション(`project_rules_db_v1.md` 改訂作業)で行う。
本ルールファイルはその採番に先行する詳細仕様として機能する。

## レビュー時のチェックリスト

- [ ] スクリプトに `--limit` / `--ticker` / `--dry-run` / `--debug` 等のテストフラグがあるか確認した
- [ ] テストフラグ存在時、target テーブルが**自動で staging に切り替わる**ロジックがあるか確認した
- [ ] `TABLE_ID` / target テーブル名が**ハードコードで本番固定**になっていないか確認した
- [ ] BQ INSERT / MERGE / LOAD / DELETE / UPDATE の**直前に target テーブル名がログ出力**されるか確認した
- [ ] 本番テーブルへの書込は `--prod-write` 等の**明示フラグ**または**ユーザ承認**が必須化されているか確認した
- [ ] Claude Code 自律実行の場合、`handoff_db_v11_1.md §5.1` の **DRY RUN 提示 → 承認待ち** 手順を踏んでいるか確認した
- [ ] スクリプト末尾で**書込件数と target テーブル**が summary 出力されているか確認した
- [ ] `rescue_*` / `fix_*` 系スクリプト(本番書込が本来の役割)の場合、
       docstring と `--help` で「本番書込スクリプト」である旨が明示されているか確認した

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 同型構造 | 関連失敗 | 参照ルール |
|---|---|---|
| 本実行前の安全弁不足(DRY RUN なし) | 失敗41(BQ 全スキャン課金) | `.claude/rules/bq/dry-run-required.md` |
| テスト・debug 出力が本番に漏出 | 失敗39(Secrets ログ出力) | `.claude/rules/secrets/no-env-var-print.md` |
| 既存状態を確認せずに「推奨」を実装 | 失敗53(handoff 推奨の現状確認漏れ) | `handoff_db_v13.md §4 失敗53` |

これらは「テスト or 部分実行が本番リソースに影響する」という共通の構造的リスクを持つ。
本ルール違反を検出した際は、上記同型ルールの違反パターンも併せて確認する。

### コードベース内の同型箇所(レビュー対象候補)

以下のスクリプトは本ルール違反の同型リスクを抱える可能性があるため、
変更があった場合は本ルールでの照合を優先する:

| スクリプト | 同型リスクの所在 | 確認すべき項目 |
|---|---|---|
| `daily_update_prices_v3.py` | **失敗43 の事故箇所**(Phase 3.4 D6.1 で改修予定) | `--limit` / `--ticker` フラグの target ルーティング |
| `jquants_update.py` | yfinance / J-Quants データ取り込み本体 | `--limit` 相当フラグの有無・target 切替の存在 |
| `jquants_test_fetch.py` | スクリプト名に `test` を含む — 名前と実装の乖離リスク | 本番テーブル書込の有無(staging only であるべき) |
| `diag_recent_jquants_runs.py` | 診断用(SELECT only 想定) | 書込操作が無いことの確認(SELECT only であるべき) |
| `rescue_*.py` / `fix_*.py` 系 | 本番補修が本来の役割(例外的に本番書込が許容される) | `--confirm` フラグの必須化と docstring 明示 |

新規スクリプト追加時も同型かどうかを判定し、必要に応じて本表に追記すること。
