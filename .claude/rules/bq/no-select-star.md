---
rule_id: bq-no-select-star
category: bq
priority: critical
paths:
  - "*.py"
related_failures: []
related_rules:
  - "project_rules_db_v1.md §4 (SELECT * 禁止)"
  - SR-2
  - G3
  - SR-11
last_updated: 2026-05-24
applies_to_environments:
  - claude_code
  - chat_claude
  - human
---

# BQ SELECT * 禁止ルール

## 規範

`client.query()` で `raw.*` テーブルを参照する SELECT は、`SELECT *` ではなく
**必要な列を明示列挙**すること。

BigQuery は**列指向ストレージ**のため、`SELECT *` は不要列まで含めた全列の scan 量を
発生させ、G3 ゲート(BQ DRY RUN ≤ 1.5 GB)違反および無料枠消費を引き起こす。
本ルールは partition-filter-required.md(行方向の scan 抑制)と対をなす
**列方向の scan 抑制**ルールである。

本ルールは `project_rules_db_v1.md §4` の「SELECT * 禁止」項目および
SR-2(BQ SELECT * 禁止)を**ファイル単位で照合可能な形に分解した詳細仕様**である。

### 対象範囲

| 対象 | 範囲 |
|---|---|
| 必須 | `client.query()` 経由で `raw.*` テーブルを参照する全 SELECT |
| 必須 | `client.query().to_dataframe()` 経由の pandas 取り込み |
| 必須 | JOIN / サブクエリ内の SELECT も含む |

### 例外条項

| 例外 | 理由 |
|---|---|
| `INFORMATION_SCHEMA.*` 参照 | スキーマ確認用・行数小・列指向 scan の影響軽微 |
| `EXISTS (SELECT * FROM ...)` | 行存在検査・BQ optimizer が列読み込みを発生させない(公式仕様) |
| `COUNT(*)` 集約 | 集約関数の `*` は列読み込みなし(BQ 公式仕様) |
| `SELECT * EXCEPT (col1, col2)` | 明示的除外があれば「列指定の意図」が明確(Pattern B 参照) |

### 主要パラメータ(本ルール作成時点)

| パラメータ | 値 | SSOT |
|---|---|---|
| `MAX_SCAN_GB` | `1.5` | `project_rules_db_v1.md §4` |
| 列方向 scan 抑制対象 | `raw.prices` / `raw.financials` 等の多列テーブル | 本ルール |

`raw.prices` の主要列(本ルール作成時点):`ticker`, `date`, `open`, `high`, `low`, `close`, `volume`, `source`, `fetched_at`(9 列)。
9 列全部必要な処理は実態として少なく、多くの場合 `ticker, date, close` 等の 3〜4 列で済む。

## 違反パターン(検出すべきコード)

### Pattern 1: 単純な `SELECT *`

```python
# 違反例
from google.cloud import bigquery
client = bigquery.Client()

sql = """
SELECT *
FROM `project.raw.prices`
WHERE date BETWEEN '2026-05-01' AND '2026-05-23'
"""
client.query(sql).result()  # ❌ 不要列を含む全列 scan
```

→ partition filter (`date BETWEEN`) で行方向は絞っても、列方向の scan は全列分発生。
9 列のうち 3 列しか使わない場合、scan 量は理論上 **3 倍**に膨らむ。

### Pattern 2: テーブルエイリアス経由の `t.*`(検出されにくい型)

```python
# 違反例
sql = """
SELECT t.*
FROM `project.raw.prices` t
WHERE t.date = '2026-05-23'
"""
client.query(sql).result()  # ❌ Pattern 1 と同等の列方向 scan 量
```

→ 機械的に `SELECT *` を grep すると検出漏れする型(`t.*` / `a.*` / `prices.*` 等)。
レビュー時は `\.\*` 正規表現での追加検出が必要。

### Pattern 3: JOIN での両側 `*`(列爆発)

```python
# 違反例
sql = """
SELECT a.*, b.*
FROM `project.raw.prices` a
JOIN `project.raw.tickers` b ON a.ticker = b.ticker
WHERE a.date = '2026-05-23'
"""
client.query(sql).result()  # ❌ 両テーブルの全列 scan
```

→ scan 量は両テーブル全列分。出力サイズも肥大化し、後続の pandas 処理メモリも圧迫。

### Pattern 4: pandas DataFrame 用途での「念のため」全列取得

```python
# 違反例
sql = "SELECT * FROM `project.raw.prices` WHERE date = '2026-05-23'"
df = client.query(sql).to_dataframe()
close_prices = df["close"]  # ❌ 実際に使うのは 1 列なのに全列 scan + DataFrame 構築
```

→ 「将来カラム追加で壊れないように」という意図でも `SELECT *` は不可。
列追加時の影響範囲が逆に**不明確になる**(明示列挙のほうが下流の依存関係が追跡可能)。

### Pattern 5: サブクエリ内の `SELECT *`(機械的検出を裏切る型)

```python
# 違反例
sql = """
SELECT ticker, date, close
FROM (
    SELECT *  -- ❌ サブクエリ内 *・最外側で絞っても scan 量に影響しうる
    FROM `project.raw.prices`
    WHERE date = '2026-05-23'
)
"""
client.query(sql).result()
```

→ BQ optimizer は最外側の SELECT 列に基づき必要列を逆伝播するが、複雑なクエリでは
optimizer が完全に追跡できない場合がある。**サブクエリ内でも明示列挙**が安全側。
DRY RUN の `total_bytes_processed` 数値検証(`bq/dry-run-required.md`)と併用で検出する。

## 正しい実装パターン

### Pattern A: 必要列の明示列挙 + DRY RUN 連動検証(基本)

```python
from google.cloud import bigquery
from datetime import date

MAX_SCAN_GB = 1.5
client = bigquery.Client()

sql = """
SELECT ticker, date, close  -- ✅ 必要列のみ明示列挙
FROM `project.raw.prices`
WHERE date BETWEEN @start_date AND @end_date
"""

params = [
    bigquery.ScalarQueryParameter("start_date", "DATE", date(2026, 5, 1)),
    bigquery.ScalarQueryParameter("end_date", "DATE", date(2026, 5, 23)),
]

# DRY RUN: partition filter + 列指定の二段効果が反映された scan 量
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

# 参考: SELECT * の場合と比較し、列数比に応じて scan 量が削減されているはず
# 例: 9 列中 3 列指定 → scan 量は理論上 1/3 オーダーに削減

cfg_live = bigquery.QueryJobConfig(query_parameters=params)
result = client.query(sql, job_config=cfg_live).result()
```

### Pattern B: `SELECT * EXCEPT` パターン(多列除外少数の例外)

多列テーブルで「ほぼ全列必要・除外は 1〜2 列」のケースのみ許容。

```python
# 許容例(例外条項)
sql = """
SELECT * EXCEPT (fetched_at, source)
FROM `project.raw.prices`
WHERE date = @target_date
"""
```

→ 明示的除外があれば「列指定の意図」が読み取れる。
ただし `EXCEPT` で除外する列が**過半数**になる場合は Pattern A(明示列挙)に切り替えること。

### Pattern C: pandas DataFrame 用途での列指定

```python
# DataFrame に取り込む列を明示
sql = """
SELECT ticker, date, close, volume  -- ✅ 後続処理で使う列のみ
FROM `project.raw.prices`
WHERE date BETWEEN @start_date AND @end_date
"""

# DRY RUN(Pattern A と同じ手順)
# ...

df = client.query(sql, job_config=cfg_live).to_dataframe()
# df は ticker / date / close / volume の 4 列のみ・メモリ効率良好
```

→ DataFrame の列構成が SQL から明確に追跡可能になり、下流コードの保守性が向上。

## 関連過去教訓

### 直接の事故記録

本ルール作成時点では `SELECT *` 起因の事故記録は無い(予防的ルール)。
ただし以下の構造的リスクは partition-filter-required.md と同型:

- **行方向の scan 量問題**(partition pruning 失敗)→ 失敗41(MERGE WHEN NOT MATCHED)
- **列方向の scan 量問題**(列指向ストレージで `*` 使用)→ 本ルールが予防

両者は二段防御(行 × 列)で BQ 無料枠を守る関係。

### 関連ルール

- `project_rules_db_v1.md §4`: BQ 操作ルール本体(本ルールの SSOT)
- SR-2: BQ SELECT * 禁止(本ルールが詳細仕様)
- `project_rules_db_v1.md G3`: BQ DRY RUN ≤ 1.5 GB ゲート(本ルール違反は G3 違反に直結)
- `project_rules_db_v1.md SR-11`: DRY RUN 単独で品質保証しない・少銘柄スケールから本番投入
- `.claude/rules/bq/partition-filter-required.md`: 行方向 scan 抑制(本ルールと対をなす)
- `.claude/rules/bq/dry-run-required.md`: DRY RUN 数値検証(本ルール違反の数値検出)

## レビュー時のチェックリスト

- [ ] `client.query()` 経由の全 SELECT に `SELECT *` が含まれていないか確認した
- [ ] テーブルエイリアス経由の `t.*` / `a.*` 等が含まれていないか確認した(Pattern 2)
- [ ] JOIN での両側 `.*` が含まれていないか確認した(Pattern 3)
- [ ] サブクエリ内の `SELECT *` が含まれていないか確認した(Pattern 5)
- [ ] `to_dataframe()` 用途でも明示列挙されているか確認した(Pattern 4)
- [ ] 例外条項該当箇所(`INFORMATION_SCHEMA` / `EXISTS` / `COUNT(*)` / `SELECT * EXCEPT`)は意図的に許容しているか確認した
- [ ] `SELECT * EXCEPT` 使用箇所で除外列が過半数を超えていないか確認した(過半数なら明示列挙に変更)
- [ ] DRY RUN の `total_bytes_processed` が列数比に応じて削減されているか確認した

## 同型ケースの参照

### 横断: 他カテゴリの関連ルール

| 同型構造 | 関連失敗 | 参照ルール |
|---|---|---|
| 全件スキャン課金事故の予防(行方向) | 失敗41 | `.claude/rules/bq/partition-filter-required.md` |
| 機械的検出を裏切る式の書き方(`t.*` / サブクエリ内 `*`) | (本ルール) | 本ルール Pattern 2 / Pattern 5 |
| DRY RUN 数値検証との二段防御 | 失敗41 | `.claude/rules/bq/dry-run-required.md` |
| 本番テーブルへの無制限アクセス | 失敗43 | `.claude/rules/bq/staging-only-tests.md` |
| 機械的検査の hit を独断判定で見逃す | 失敗39 | `.claude/rules/secrets/no-env-var-print.md` |

これらは「**本実行前の安全弁を機械的に強制する**」あるいは
「**構造的予防で偶然の課金事故を避ける**」という共通の構造的リスクを持つ。
本ルール違反を検出した際は、上記同型ルールの違反パターンも併せて確認する。

特に partition-filter-required.md と本ルールは**行 × 列の二段防御**として
常に併用してレビューすること。片方だけ守っても scan 量削減効果は限定的。

### コードベース内の同型箇所(レビュー対象候補)

| スクリプト | 同型リスクの所在 | 確認すべき項目 |
|---|---|---|
| `daily_update_prices_v3.py` | BQ SELECT/INSERT/MERGE | `SELECT *` 有無・JOIN 両側 `.*` 有無 |
| `jquants_update.py` (rev5) | J-Quants 取り込み + BQ 書込 | `SELECT *` 有無・staging→prod 移送時の列指定 |
| `dedup_check.py` / `dedup_fix.py` / `dedup_fix_v07.py` | 重複検査 SELECT | `SELECT *` 有無・サブクエリ内 `*` 有無 |
| `diag_partition.py` / `diag_recent_partitions.py` / `diag_21rows_detail.py` | 診断系 SELECT | `SELECT *` 有無(診断目的でも明示列挙) |
| `rescue_drop_2026_04_27_28.py` | DELETE + INSERT 内の SELECT | INSERT...SELECT の列指定確認(Pattern C 模範) |
| `quality_check.py` / `quality_check_fin.py` | 品質検査 SELECT | `SELECT *` 有無・`COUNT(*)` 例外条項適用確認 |
| 新規 BQ 参照スクリプト全般 | `client.query(...)` 全般 | Pattern A〜C テンプレ流用 |

新規スクリプト追加時も同型かどうかを判定し、必要に応じて本表に追記すること。
