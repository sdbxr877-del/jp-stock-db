---
rule_id: general-dont-trust-success
category: general
priority: high
paths: []
related_failures:
  - DB-36
  - DB-39
  - DB-40
  - DB-41
  - DB-42
  - DB-43
related_rules:
  - "§1-6"
applies_to_environments: [claude_code, chat_claude, human]
last_updated: 2026-09-11
scope: global
source_project: FX-db
vault_version: 1.0
vault_imported: 2026-08-29
origin_path: C:\FX-db\.claude\rules\general\dont-trust-success.md
---

# 「Success」を信じない原則

<!-- portability-note -->
> **他プロジェクトでの読み替え** — 本ルールは `second-brain` から配布されている。
> 文中の `SR-xx` / `G-x` / `失敗NN` / `handoff_db_vNN.md` / `project_rules_db_v1.md` は
> **発祥プロジェクトでの出自の記録**であり、参照先が自プロジェクトに存在しなくてもよい。
> **規範・違反パターン・チェックリストはそのまま有効**。教訓の原文は
> `C:\second-brain\20_failures\` にある。
<!-- portability-note -->


## 規範
スクリプト・バックテスト・発注・CI が「成功」「200 OK」「PASS」と表示されても、
**想定通りの効果が数値・実機・約定結果で確認できるまで完了とみなさない**。
FX では特に「バックテスト良好 ≠ 実戦で勝てる」「発注 200 ≠ 意図した価格で約定」の乖離が致命傷になる。

## 違反パターン(検出すべきコード)

### Pattern 1: 戻り値/例外なしを成功と即断
```python
# 違反例
broker.place_order(order)      # 戻り値・約定結果を検証せず「発注成功」とみなす
print("done")
```

### Pattern 2: バックテストのプラス収益だけで採用
```python
# 違反例
if result.pnl > 0:
    deploy(strategy)           # OOS 検証・コスト計上・約定前提の確認なし
```

## 正しい実装パターン
```python
res = broker.place_order(order)
assert res.status == "FILLED", f"未約定: {res.status}"
assert abs(res.fill_price - order.entry) <= max_slippage, "スリッページ超過"
log.info("filled %s @ %s", res.ticket, res.fill_price)
```

## 関連過去教訓
- DB-36/39/40/41/42/43: いずれも「成功表示」を鵜呑みにした結果の事故。数値・実機で再確認する。
  ただし DB-42（`set -euo pipefail` × grep no-match exit 1）は逆方向（本来PASSがFAIL表示された）の事故であり、
  本ルールの「成功を鵜呑みにしない」規範そのものの実例ではない。shell の終了コード設計ミスという別種の罠として、
  関連はあるが Pattern 化はしていない（2026-09-11 監査時点の判断）。

## レビュー時のチェックリスト
- [ ] 発注後に約定結果（status/fill_price/slippage）を検証しているか
- [ ] 戦略採用の前に OOS・コスト計上・約定前提を確認しているか
- [ ] 「成功ログ」だけで完了宣言していないか
