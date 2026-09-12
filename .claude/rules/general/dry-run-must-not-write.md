---
rule_id: general-dry-run-must-not-write
category: general
priority: critical
paths: []
related_failures:
  - DB-26
  - DB-31
  - "CW-03"
related_rules:
  - "general/dont-trust-success"
  - "bq/dry-run-required"
  - "bq/staging-only-tests"
applies_to_environments: [claude_code, chat_claude, human]
scope: global
source_project: jp-stock-db
vault_version: 1.0
vault_status: active
vault_imported: 2026-08-31
last_updated: 2026-09-11
---

# DRY RUN は副作用を持たず、本番と同じ条件で走る

<!-- portability-note -->
> **他プロジェクトでの読み替え** — 本ルールは `second-brain` から配布されている。
> 文中の `SR-xx` / `G-x` / `失敗NN` / `handoff_db_vNN.md` / `project_rules_db_v1.md` は
> **発祥プロジェクトでの出自の記録**であり、参照先が自プロジェクトに存在しなくてもよい。
> **規範・違反パターン・チェックリストはそのまま有効**。教訓の原文は
> `C:\second-brain\20_failures\` にある。
<!-- portability-note -->



## 規範

DRY RUN・テスト・バックテストには**2つの絶対条件**がある。

1. **副作用ゼロ**: 本番テーブル・チェックポイント・状態ファイル・外部送信に一切書き込まない
2. **本番同条件**: 期間・処理順・件数上限・データ経路を本番と同じにする

どちらか一方でも崩れると、DRY RUN は「安心を与えるだけで何も検証していない」ものになる。
これは `general/dont-trust-success` の姉妹ルールであり、**通ったこと自体が嘘になる**ぶん質が悪い。

過去の実害:

| 失敗 | 崩れた条件 | 結果 |
|---|---|---|
| [[DB-26]] | 副作用ゼロ | DRY RUN がチェックポイントに完了を書き、本番実行で**全銘柄スキップ・投入0行** |
| [[DB-31]] | 本番同条件 | DRY RUN は0件、本番で**471行の重複（余剰238行）** |
| [[CW-03]] | 本番同条件 | テストが本番と違う処理順で動き、実運用で起きない失敗を検出していた |

## 違反パターン(検出すべきコード)

### Pattern 1: DRY RUN 分岐が書き込みの手前で終わっていない（DB-26 直接型）
```python
# 違反例
def upload_chunk(rows, dry: bool):
    if not dry:
        client.insert_rows(table, rows)
    save_checkpoint(done=True)     # ← DRY RUN でも実行される
```

### Pattern 2: テストだけ期間・件数が違う（DB-31 直接型）
```python
# 違反例: DRY RUN は 3日分、本番は 30日分。重複は本番でしか出ない
SCAN_DAYS = 3 if dry else 30
```

### Pattern 3: テストが本番と違う順序で走る（CW-03 直接型）
```python
# 違反例: 本番は collect→filter→score の順。テストは score から始める
def test_score():
    score(load_fixture())          # collect / filter を通っていない
```

## 正しい実装パターン

```python
# ✅ 副作用は1か所に集め、DRY RUN はそこに入る前で return する
def upload_chunk(rows, dry: bool) -> int:
    if dry:
        print(f"[DRY] would insert {len(rows)} rows")
        return len(rows)           # 状態は一切変更しない
    client.insert_rows(table, rows)
    save_checkpoint(done=True)
    return len(rows)
```

```python
# ✅ 条件は本番と共有し、書き込み先だけを差し替える
SCAN_DAYS = 30                      # dry でも本番でも同じ
TABLE = STAGING_TABLE if dry else PROD_TABLE
```

```python
# ✅ テストは本番のエントリポイントを呼ぶ（処理順を再現する）
def test_pipeline():
    run_pipeline(source=FIXTURE, table=STAGING_TABLE)
```

## レビュー時のチェックリスト

- [ ] DRY RUN 分岐の**後ろ**に書き込み・状態更新が残っていないか（checkpoint / ログDB / メール送信）
- [ ] DRY RUN と本番で期間・件数上限・処理順が同一か
- [ ] テストが本番のエントリポイントを経由しているか
- [ ] DRY RUN 実行後に状態ファイルの mtime が変わっていないことを実測したか
- [ ] 「DRY RUN 0件」を根拠に本番を実行しようとしていないか
