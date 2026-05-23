---
rule_id: bq-dry-run-required
category: bq
priority: critical
paths:
  - "*.py"
related_failures:
  - 失敗41
related_rules:
  - G3
  - SR-11
last_updated: 2026-05-23
applies_to_environments:
  - claude_code
  - chat_claude
  - human
---

# BQ DRY RUN 必須ルール

## 規範

`raw.prices` / `raw.tickers` / `raw.financials` のいずれかを参照するクエリは、
本実行前に必ず `bigquery.QueryJobConfig(dry_run=True)` で DRY RUN を実行し、
`total_bytes_processed / (1024**3)` が `MAX_SCAN_GB` 以下であることを**コード上で検証**する
(目視確認だけでは不十分)。

本ルールは `project_rules_db_v1.md §4` の BQ 操作ルールおよび G3 ゲート
(BQ DRY RUN ≤ 1.5 GB)を**ファイル単位で照合可能な形に分解した詳細仕様**である。

### 主要パラメータ(本ルール作成時点)

| パラメータ | 値 | SSOT |
|---|---|---|
| `MAX_SCAN_GB` | `1.5` | `project_rules_db_v1.md §4`(現行値) |
| DRY RUN 必須対象 | `client.query(...)` の本実行を伴う全クエリ | `project_rules_db_v1.md §4` |
| MERGE で `WHEN NOT MATCHED INSERT` を含む文 | **使用禁止**(target partition pruning 不可) | `project_rules_db_v1.md §4 db_v0.10 強化(失敗41)` |
| 代替パターン | `BEGIN TRANSACTION; DELETE; INSERT; COMMIT;` | 同上(qualifying full partition DELETE は 0 byte 課金) |

将来 `MAX_SCAN_GB` の値が変更される場合は `project_rules_db_v1.md §4` を SSOT として更新。
本ルール内の数値はその時点のスナップショットである。

`bq query` コマンドの直接実行は `.claude/settings.json` で deny されており、
**BQ クエリは Python 経由(`google-cloud-bigquery` ライブラリ)+ DRY RUN 込み実行のみ**を許可する運用。

## 違反パターン(検出すべきコード)

### Pattern 1: DRY RUN を完全に省略

```python
# 違反例
from google.cloud import bigquery
client = bigquery.Client()

sql = "SELECT * FROM `project.raw.prices` WHERE date BETWEEN '2026-05-01' AND '2026-05-23'"
client.query(sql).result()  # ❌ DRY RUN なし・課金事故リスク
```

→ 失敗41 同型(全パーティションスキャンの可能性)。

### Pattern 2: DRY RUN は実行するが結果を検証しない

```python
# 違反例
job = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True))
# ❌ job.total_bytes_processed を変数に取らず即本実行
client.query(sql).result()
```

→ DRY RUN のコード形式だけで実質的な安全弁になっていない。

### Pattern 3: MAX_SCAN_GB 超過を print のみで継続

```python
# 違反例
MAX_SCAN_GB = 1.5
job = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True))
gb = job.total_bytes_processed / (1024 ** 3)
if gb > MAX_SCAN_GB:
    print(f"WARNING: {gb} GB")  # ❌ print だけで停止せず本実行
client.query(sql).result()
```

→ 規範違反。超過時は **`raise` または `exit(1)` で停止**が必須。

### Pattern 4: MERGE で WHEN NOT MATCHED INSERT を含む(失敗41 直接型)

```python
# 違反例
sql = """
MERGE `project.raw.prices` AS T
USING staging AS S
ON T.ticker = S.ticker AND T.date = S.date
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT (...) VALUES (...)  -- ❌ target partition pruning 不可
"""
client.query(sql).result()
# DRY RUN を通っても target 全パーティションスキャンで実行時課金が膨らむ
```

→ 失敗41 (2026-04 頃) と同型の事故再発リスク。DRY RUN 段階で察知できないこともある
(`total_bytes_processed` は scan 量を含むが、`WHEN NOT MATCHED` の target pruning 不可は
DRY RUN 数値に反映される ので、**Pattern 3 の MAX_SCAN_GB 検証で同時に検出可能**)。

## 正しい実装パターン

### Pattern A: DRY RUN 検証 → 本実行(SELECT / 単純 DML 用)

```python
from google.cloud import bigquery

MAX_SCAN_GB = 1.5  # ✅ スクリプト先頭で明示定義
client = bigquery.Client()

sql = """
SELECT ticker, date, close
FROM `project.raw.prices`
WHERE date BETWEEN @start_date AND @end_date
"""

# Step 1: DRY RUN(use_query_cache=False で正確なスキャン量取得)
cfg_dry = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
job = client.query(sql, job_config=cfg_dry)
gb = job.total_bytes_processed / (1024 ** 3)
print(f"[DRY RUN] Scan: {gb:.6f} GB (MAX_SCAN_GB={MAX_SCAN_GB})")

if gb > MAX_SCAN_GB:
    raise SystemExit(f"DRY RUN over MAX_SCAN_GB: {gb:.6f} > {MAX_SCAN_GB}")  # ✅ 停止

# Step 2: DRY RUN PASS してから本実行
result = client.query(sql).result()
print(f"[LIVE] Rows: {result.total_rows}")
```

### Pattern B: DELETE+INSERT in transaction(失敗41 教訓の MERGE 代替パターン)

target 側の特定パーティションを置換したい場合(MERGE の典型用途)は、MERGE ではなく
**`BEGIN TRANSACTION; DELETE; INSERT; COMMIT;`** を使う。
qualifying full partition DELETE は **0 byte 課金**(BQ 公式)で、失敗41 修正実績では
**0.368 GB → 0.000312 GB(99.92% 削減)** を達成。

```python
sql = """
BEGIN TRANSACTION;

DELETE FROM `project.raw.prices`
WHERE date IN (@target_dates);  -- partition pruning 効く

INSERT INTO `project.raw.prices` (ticker, date, open, high, low, close, volume, source, fetched_at)
SELECT ticker, date, open, high, low, close, volume, source, fetched_at
FROM `project.staging.prices_jquants_staging`
WHERE date IN (@target_dates);

COMMIT TRANSACTION;
"""

# DRY RUN(Pattern A と同じ手順)
cfg_dry = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
job = client.query(sql, job_config=cfg_dry)
gb = job.total_bytes_processed / (1024 ** 3)
if gb > MAX_SCAN_GB:
    raise SystemExit(f"DRY RUN over MAX_SCAN_GB: {gb:.6f} > {MAX_SCAN_GB}")

client.query(sql).result()  # ✅ DRY RUN PASS 後の本実行
```

**重要**: `BEGIN TRANSACTION` ブロック内で DELETE のパーティションフィルタが
正しく機能していることを DRY RUN 数値で確認(0.000XXX GB レベルになるはず)。
DRY RUN が想定外に大きい場合は、フィルタ条件 / partition 指定の見直しが必要。

## 関連過去教訓

### 失敗41(本ルール作成の直接動機)

- **発生**: db_v0.10 セッション中(2026-04 月頃)
- **直接原因**: BQ MERGE 1 本での全パーティションスキャン課金
- **真因**: MERGE 文の `WHEN NOT MATCHED THEN INSERT` を含む場合、target 側 partition pruning が効かない(BQ 公式 docs 記載)
- **修正**: `BEGIN TRANSACTION; DELETE; INSERT; COMMIT;` パターンへ変更
- **効果**: **0.368 GB → 0.000312 GB(99.92% 削減)**
- **検証実績**: db_v0.11 セッションの `rescue_drop_2026_04_27_28.py --dry → --confirm` で
  **DRY RUN 0.000000 GB** 実証(`handoff_db_v11.md` Pre-A4 参照)
- **教訓**: DRY RUN は本実行前に必ず実行し、コード上で `MAX_SCAN_GB` と比較・超過時は停止

### 関連ルール

- `project_rules_db_v1.md §4`: BQ 操作ルール本体(本ルールの SSOT)
- `project_rules_db_v1.md G3`: BQ DRY RUN ≤ 1.5 GB ゲート
- `project_rules_db_v1.md SR-11`: DRY RUN 単独で品質保証しない・少銘柄スケールから本番投入
  (本ルールと併用:DRY RUN PASS でも段階テスト必須)
- `.claude/settings.json`(db_v0.12 配置): `Bash(bq query *)` deny で BQ クエリの
  Python 経由実行を設定レベルで強制

## レビュー時のチェックリスト

- [ ] 全ての `client.query(...).result()` 呼び出しの直前に DRY RUN 検証があるか確認した
- [ ] DRY RUN の `total_bytes_processed` を実際に変数(`gb` 等)に取って `MAX_SCAN_GB` と比較しているか確認した
- [ ] MAX_SCAN_GB 超過時に `raise` または `exit(1)` で**停止**しているか確認した(`print` のみで継続は NG)
- [ ] `MAX_SCAN_GB` 定数がスクリプト先頭で明示的に定義されているか確認した
- [ ] DRY RUN 時の `QueryJobConfig` に `use_query_cache=False` が指定されているか確認した(キャッシュヒットでスキャン量が 0 に見えると検知漏れ)
- [ ] MERGE 文に `WHEN NOT MATCHED THEN INSERT` が含まれていないか確認した(Pattern 4)
- [ ] target 側 partition 置換が必要な場合、`BEGIN TRANSACTION; DELETE; INSERT; COMMIT;` パターンを使っているか確認した
- [ ] DELETE 文に partition pruning が効くフィルタ条件(`WHERE date IN ...` / `WHERE date BETWEEN ...`)があるか確認した

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 同型構造 | 関連失敗 | 参照ルール |
|---|---|---|
| テスト・部分実行が本番リソースに影響 | 失敗43(本番テーブル汚染) | `.claude/rules/bq/staging-only-tests.md` |
| 機械的検査の hit を独断判定で見逃す | 失敗39(G2 grep の誤検知判定) | `.claude/rules/secrets/no-env-var-print.md` |
| 環境差検証漏れ(Linux と Windows の挙動差) | 失敗54(CRLF/LF) | `handoff_db_v13.md §4 失敗54` |
| 既存状態を確認せずに「推奨」を実装 | 失敗53(handoff 推奨の現状確認漏れ) | `handoff_db_v13.md §4 失敗53` |

これらは「**本実行前の安全弁を機械的に強制する**」あるいは「**目視確認だけで済ませず数値検証する**」
という共通の構造的リスクを持つ。本ルール違反を検出した際は、上記同型ルールの違反パターンも併せて確認する。

### コードベース内の同型箇所(レビュー対象候補)

| スクリプト | 同型リスクの所在 | 確認すべき項目 |
|---|---|---|
| `daily_update_prices_v3.py` | BQ INSERT/MERGE 発行本体(Phase 3.4 D6.1 改修予定) | DRY RUN 有無・MAX_SCAN_GB 検証・MERGE 使用箇所 |
| `jquants_update.py` (rev5) | J-Quants データ取り込み + BQ 書込 | DRY RUN 有無・DELETE+INSERT パターンの採用状況 |
| `rescue_drop_2026_04_27_28.py` | **失敗41 教訓検証で DRY RUN 0.000000 GB 実証済** | 本ルールの Pattern B 模範例として参照 |
| `dedup_check.py` / `dedup_fix.py` / `dedup_fix_v07.py` | 重複検査・修正で BQ SELECT/DELETE 発行 | DRY RUN 有無・SELECT * 禁止(別ルール SR-2)併せて確認 |
| `diag_*.py` 系(`diag_partition.py` / `diag_recent_partitions.py` / `diag_21rows_detail.py` 等) | 診断用(SELECT only 想定) | DRY RUN 有無・パーティションフィルタ・SELECT * 禁止 |
| 新規 BQ 書込スクリプト全般 | `client.query(...).result()` 呼び出し箇所 | Pattern A / Pattern B のテンプレート流用 |

新規スクリプト追加時も同型かどうかを判定し、必要に応じて本表に追記すること。
