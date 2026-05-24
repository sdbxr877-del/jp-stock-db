---
rule_id: bq-partition-filter-required
category: bq
priority: critical
paths:
  - "*.py"
related_failures:
  - 失敗41
related_rules:
  - "project_rules_db_v1.md §4 (パーティションフィルタ必須)"
  - SR-1
  - G3
  - SR-11
last_updated: 2026-05-24
applies_to_environments:
  - claude_code
  - chat_claude
  - human
---

# BQ パーティションフィルタ必須ルール

## 規範

`raw.prices` および `PARTITION BY date` で構成された全テーブルを参照する SQL は、
`WHERE` 句に partition key(`date`)を含む**決定的なフィルタ条件**
(`=` / `IN` / `BETWEEN` / `>=` AND `<=` の組合せ)を必ず付与すること。

partition key を含まない `WHERE` 句、partition key を含むが pruning 不可な式
(左辺に関数適用・サブクエリ等)、`WHERE` 句完全欠落は、全パーティションスキャンによる
課金事故および G3 ゲート(BQ DRY RUN ≤ 1.5 GB)違反を引き起こす。

本ルールは `project_rules_db_v1.md §4` の「パーティションフィルタ必須」項目および
SR-1(BQ パーティションフィルタ必須)を**ファイル単位で照合可能な形に分解した詳細仕様**である。

### 対象テーブル(本ルール作成時点)

| 区分 | テーブル名 | 構成 | 適用 |
|---|---|---|---|
| 本番 | `raw.prices` | PARTITION BY date / CLUSTER BY ticker | ✅ 必須 |
| 本番 | `raw.tickers` | (PARTITION なし・マスタ) | ❌ 対象外 |
| 本番 | `raw.financials` | 未確認(本ルール作成時点) | ⏳ PARTITION 設定があれば適用 |
| staging(稼働中) | `raw.prices_jquants_staging` | TRUNCATE 運用 | ✅ 必須(将来 partition 化前提) |
| staging(計画) | `raw.prices_test_staging` | Phase 3.4 D6.1 で新設予定 | ✅ 必須(先回り適用) |

本ルールの判定基準は「**テーブル DDL に `PARTITION BY date` があるか**」である。
新規テーブル追加時は本表に追記し、PARTITION 構成を明示すること。

### 例外条項

- `INFORMATION_SCHEMA.*` 参照(スキーマ確認用): 対象外
- スキャン量が DRY RUN で `MAX_SCAN_GB` 以下と確認できた場合でも本ルールは適用(規範違反扱い)
  → 偶然 scan 量が小さくても、構造的に partition filter なしのコードは違反

### 主要パラメータ(本ルール作成時点)

| パラメータ | 値 | SSOT |
|---|---|---|
| partition key 列名 | `date` | `raw.prices` DDL(`handoff_db_v11.md §65`) |
| `MAX_SCAN_GB` | `1.5` | `project_rules_db_v1.md §4` |

## 違反パターン(検出すべきコード)

### Pattern 1: WHERE 句完全欠落

```python
# 違反例
from google.cloud import bigquery
client = bigquery.Client()

sql = "SELECT ticker, date, close FROM `project.raw.prices`"
client.query(sql).result()  # ❌ 全パーティションスキャン (約 0.4 GB スケール)
```

→ DRY RUN で検知可能(`total_bytes_processed` が大きく出る)だが、
本ルールは DRY RUN 以前の構造的予防として **WHERE 句に partition key 必須**を強制する。

### Pattern 2: WHERE 句に partition key (`date`) を含まない

```python
# 違反例
sql = """
SELECT ticker, date, close
FROM `project.raw.prices`
WHERE ticker = '7203.T'  -- ❌ ticker は CLUSTER 列・partition key ではない
"""
client.query(sql).result()
```

→ `ticker` は CLUSTER BY 列で、ある程度のスキャン量削減効果はあるが、
**全パーティションスキャン**になる(BQ 公式仕様)。partition key (`date`) と併用が必須。

### Pattern 3: partition pruning が機能しない式(機械的検出を裏切る型)

```python
# 違反例 3a: 左辺に関数を適用
sql = """
SELECT ticker, date, close
FROM `project.raw.prices`
WHERE DATE_DIFF(date, CURRENT_DATE(), DAY) > -30  -- ❌ pruning 不可
"""

# 違反例 3b: CAST 経由
sql = """
SELECT ticker, date, close
FROM `project.raw.prices`
WHERE CAST(date AS STRING) >= '2026-05-01'  -- ❌ pruning 不可
"""

# 違反例 3c: サブクエリで partition 列を絞る
sql = """
SELECT ticker, date, close
FROM `project.raw.prices`
WHERE date IN (SELECT MAX(date) FROM `project.raw.prices`)  -- ❌ pruning 不安定
"""
```

→ 「`WHERE date ...` という文字列は存在するが pruning が効かない」最も発見しにくい型。
DRY RUN の `total_bytes_processed` 数値検証(`bq/dry-run-required.md`)と併用で検出する。

**正解パターンへの変換**:
- 3a: `WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)`(右辺に関数・左辺はそのまま)
- 3b: `WHERE date >= '2026-05-01'`(CAST 不要・DATE リテラルは自動推論)
- 3c: 別クエリで MAX(date) を先にスカラー取得 → パラメタライズで渡す(Pattern B 参照)

### Pattern 4: 動的 SQL での文字列連結による条件落ち

```python
# 違反例
def build_query(where_clause=""):
    return f"""
    SELECT ticker, date, close
    FROM `project.raw.prices`
    {where_clause}
    """

# 呼び出し側で where_clause を渡し忘れる経路
sql = build_query()  # ❌ where_clause が空文字 → WHERE 句なしクエリ生成
client.query(sql).result()
```

→ 静的検査で発見しにくい。動的 SQL 生成関数は **partition filter を必須引数化**し、
デフォルト値を持たせない(`where_clause: str` を必須位置引数にする)設計が望ましい。

### Pattern 5: MERGE で WHEN NOT MATCHED INSERT を含む(失敗41 直接型)

```python
# 違反例
sql = """
MERGE `project.raw.prices` AS T
USING staging AS S
ON T.ticker = S.ticker AND T.date = S.date
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT (...) VALUES (...)  -- ❌ target 側 partition pruning 不可
"""
client.query(sql).result()
```

→ 失敗41 (2026-04 頃) と同型。`ON` 句に partition key (`T.date = S.date`) を含めても、
`WHEN NOT MATCHED THEN INSERT` が存在する限り **target 全パーティションスキャン**
(BQ 公式 docs 記載)。

詳細と DELETE+INSERT 代替パターンは `bq/dry-run-required.md` Pattern 4 / Pattern B を参照。

## 正しい実装パターン

### Pattern A: 期間フィルタ + DRY RUN 連動検証(パラメタライズ推奨)

```python
from google.cloud import bigquery
from datetime import date

MAX_SCAN_GB = 1.5
client = bigquery.Client()

sql = """
SELECT ticker, date, close
FROM `project.raw.prices`
WHERE date BETWEEN @start_date AND @end_date  -- ✅ partition key + 決定的フィルタ
"""

params = [
    bigquery.ScalarQueryParameter("start_date", "DATE", date(2026, 5, 1)),
    bigquery.ScalarQueryParameter("end_date", "DATE", date(2026, 5, 23)),
]

# Step 1: DRY RUN で partition pruning が効いていることを確認
cfg_dry = bigquery.QueryJobConfig(
    dry_run=True,
    use_query_cache=False,
    query_parameters=params,
)
job = client.query(sql, job_config=cfg_dry)
gb = job.total_bytes_processed / (1024 ** 3)
print(f"[DRY RUN] Scan: {gb:.6f} GB (MAX_SCAN_GB={MAX_SCAN_GB})")

if gb > MAX_SCAN_GB:
    raise SystemExit(f"DRY RUN over MAX_SCAN_GB: {gb:.6f} > {MAX_SCAN_GB}")

# 参考: 全テーブル scan の約 0.4 GB から、23日分の partition pruning で
#       0.01 GB 未満のオーダーに削減されるはず

# Step 2: 本実行
cfg_live = bigquery.QueryJobConfig(query_parameters=params)
result = client.query(sql, job_config=cfg_live).result()
print(f"[LIVE] Rows: {result.total_rows}")
```

### Pattern B: 単一日 / 複数日指定(UNNEST パターン)

```python
target_dates = [date(2026, 4, 27), date(2026, 4, 28)]

sql = """
SELECT ticker, date, close
FROM `project.raw.prices`
WHERE date IN UNNEST(@target_dates)  -- ✅ 配列パラメタライズ
"""

params = [
    bigquery.ArrayQueryParameter("target_dates", "DATE", target_dates),
]

# DRY RUN(Pattern A と同じ手順)
cfg_dry = bigquery.QueryJobConfig(
    dry_run=True,
    use_query_cache=False,
    query_parameters=params,
)
job = client.query(sql, job_config=cfg_dry)
gb = job.total_bytes_processed / (1024 ** 3)
if gb > MAX_SCAN_GB:
    raise SystemExit(f"DRY RUN over MAX_SCAN_GB: {gb:.6f} > {MAX_SCAN_GB}")

cfg_live = bigquery.QueryJobConfig(query_parameters=params)
result = client.query(sql, job_config=cfg_live).result()
```

`rescue_drop_2026_04_27_28.py` で **DRY RUN 0.000000 GB**(完全な partition pruning)を
実証済(`handoff_db_v11.md` Pre-A4 参照)。

### Pattern C: MERGE 代替 DELETE+INSERT(失敗41 教訓・partition pruning 観点)

target 側の特定パーティションを置換する場合、MERGE ではなく
**`BEGIN TRANSACTION; DELETE; INSERT; COMMIT;`** を使う。
DELETE 文の `WHERE` 句に partition key が入っていることが pruning 成立の鍵。

```python
sql = """
BEGIN TRANSACTION;

DELETE FROM `project.raw.prices`
WHERE date IN UNNEST(@target_dates);  -- ✅ partition key 直接指定 → pruning 成立

INSERT INTO `project.raw.prices` (ticker, date, open, high, low, close, volume, source, fetched_at)
SELECT ticker, date, open, high, low, close, volume, source, fetched_at
FROM `project.raw.prices_jquants_staging`
WHERE date IN UNNEST(@target_dates);  -- ✅ source 側 partition も同様に指定

COMMIT TRANSACTION;
"""

# DRY RUN + 本実行手順は Pattern A と同様
```

実績: **0.368 GB → 0.000312 GB(99.92% 削減)**(失敗41 修正実績・`handoff_db_v11.md`)。

詳細は `bq/dry-run-required.md` Pattern B 参照。

## 関連過去教訓

### 失敗41(同型関連)

- **発生**: db_v0.10 セッション中(2026-04 月頃)
- **直接原因**: BQ MERGE 1 本での全パーティションスキャン課金
- **真因**: MERGE 文の `WHEN NOT MATCHED THEN INSERT` を含む場合、
  target 側 partition pruning が効かない(BQ 公式 docs 記載)
- **本ルールとの関係**: 失敗41 は「**partition filter があっても pruning が機能しない**」型。
  本ルールはより広く「**partition filter そのものを必須化**」する上位概念
- **修正**: `BEGIN TRANSACTION; DELETE; INSERT; COMMIT;` パターン(Pattern C)
- **効果**: 0.368 GB → 0.000312 GB(99.92% 削減)
- **教訓**: WHERE 句に partition key を含めることは**必要条件**であり、
  pruning が実際に効くかは DRY RUN 数値で検証する(`bq/dry-run-required.md` と二段防御)

### 関連ルール

- `project_rules_db_v1.md §4`: BQ 操作ルール本体(本ルールの SSOT)
- SR-1: BQ パーティションフィルタ必須(本ルールが詳細仕様)
- `project_rules_db_v1.md G3`: BQ DRY RUN ≤ 1.5 GB ゲート(本ルール違反は G3 違反に直結)
- `project_rules_db_v1.md SR-11`: DRY RUN 単独で品質保証しない・少銘柄スケールから本番投入
  (本ルールと併用: partition filter PASS でも段階テスト必須)
- `.claude/rules/bq/dry-run-required.md`: DRY RUN 数値検証の詳細(本ルールとの二段防御)
- `.claude/rules/bq/no-select-star.md`(本日 第2ルールで作成予定): SELECT * 禁止と併用で課金事故予防

## レビュー時のチェックリスト

- [ ] `raw.prices` および partition 化された全テーブルを参照する SQL に `WHERE` 句があるか確認した
- [ ] `WHERE` 句に partition key (`date`) を含むフィルタ条件があるか確認した
- [ ] `WHERE date ...` の**左辺**に関数(`DATE_DIFF` / `CAST` 等)が適用されていないか確認した
- [ ] サブクエリで partition 列を絞っていないか確認した(スカラー値として事前取得すべき)
- [ ] 動的 SQL 生成関数は partition filter を必須パラメータ化しているか確認した
- [ ] MERGE 文に `WHEN NOT MATCHED THEN INSERT` が含まれていないか確認した(Pattern 5)
- [ ] DELETE+INSERT パターンの DELETE 文に partition key 直接指定があるか確認した(Pattern C)
- [ ] DRY RUN の `total_bytes_processed` が想定オーダー(partition pruning 効果分削減)になっているか確認した
- [ ] partition key の値はパラメタライズ(`ScalarQueryParameter` / `ArrayQueryParameter`)で渡しているか確認した

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 同型構造 | 関連失敗 | 参照ルール |
|---|---|---|
| 機械的検出を裏切る式の書き方(`WHERE` 句はあるが pruning 不可) | 失敗41 | `.claude/rules/bq/dry-run-required.md` Pattern 4 |
| 全件スキャン課金事故の予防 | 失敗41 | `.claude/rules/bq/dry-run-required.md`(DRY RUN 数値検証) |
| 本番テーブルへの無制限アクセス | 失敗43(本番テーブル汚染) | `.claude/rules/bq/staging-only-tests.md` |
| 課金事故予防の二重防御(scan 量 × 列数) | (SR-2) | `.claude/rules/bq/no-select-star.md`(本日 第2ルールで作成予定) |
| 機械的検査の hit を独断判定で見逃す | 失敗39 | `.claude/rules/secrets/no-env-var-print.md` |

これらは「**本実行前の安全弁を機械的に強制する**」あるいは
「**構造的予防で偶然の課金事故を避ける**」という共通の構造的リスクを持つ。
本ルール違反を検出した際は、上記同型ルールの違反パターンも併せて確認する。

### コードベース内の同型箇所(レビュー対象候補)

| スクリプト | 同型リスクの所在 | 確認すべき項目 |
|---|---|---|
| `daily_update_prices_v3.py` | BQ INSERT/SELECT の WHERE 句(Phase 3.4 D6.1 改修予定) | `date` フィルタ有無・関数経由参照の有無 |
| `jquants_update.py` (rev5) | J-Quants 取り込みの SELECT/MERGE | partition key 指定・MERGE → DELETE+INSERT 変換 |
| `rescue_drop_2026_04_27_28.py` | **本ルール Pattern B / C の模範例**(DRY RUN 0.000000 GB 実証済) | 参照模範 |
| `diag_recent_partitions.py` / `diag_21rows_detail.py` / `diag_partition.py` | 診断系 SELECT(SELECT only 想定) | partition フィルタ・SELECT * 禁止(SR-2)併用確認 |
| `dedup_check.py` / `dedup_fix.py` / `dedup_fix_v07.py` | 重複検査・修正の SELECT/DELETE | partition フィルタ・MAX_SCAN_GB 検証 |
| 新規 BQ 参照スクリプト全般 | `client.query(...)` の SELECT/UPDATE/DELETE/MERGE | Pattern A〜C テンプレ流用 |

新規スクリプト追加時も同型かどうかを判定し、必要に応じて本表に追記すること。
