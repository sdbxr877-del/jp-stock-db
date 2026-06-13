# Phase 3 スクリーニング層(MVP v1)

東証銘柄を BigQuery 上で日次スクリーニングし、UI が読む `analytics.screening_candidates` を生成する。

## データフロー

```
raw.prices ─────┐
                ├─ 01 → analytics.daily_metrics        (日次・価格由来指標・冪等 append)
raw.financials ─── 02 → analytics.fundamentals_latest  (銘柄ごと最新財務)
raw.tickers ────┐
01 / 02 ────────┴─ 03 → analytics.screening_candidates (最新日・絞り込み済・UI 対象)
```

- materialization 方式(ビュー不採用): 日次1回計算 → 以降の read は激安(無料枠の繰返し課金を回避)
- `daily_metrics` は対象日の `DELETE`→`INSERT`(MERGE は partition pruning 阻害のため不使用)
- `fundamentals_latest` / `screening_candidates` は `CREATE OR REPLACE`

## 実行

```powershell
cd C:\jp-stock-db
python analytics\screening\run_screening.py            # 初回(DDL 込み)
python analytics\screening\run_screening.py --skip-ddl # 通常運用(daily_metrics 作成済)
```

各クエリは dry-run でスキャン量を表示してから本実行する(dry-run-required)。
自動化は価格 ingestion 完了後に GHA cron / scheduled query から `run_screening.py` を呼ぶ。

## 実装初回の3点確認(db_v0.19・2026-06-13 実測で確定済)

1. **period_type**: 全件 `annual`(16,835件)。`02` で `AND period_type = 'annual'` を有効化済(防御的)。
2. **`raw.tickers.market`**: 日本語3区分(プライム1602/スタンダード1569/グロース612)。
   「その他489」「TOKYO PRO MARKET 163」は `allowed_markets` 不指定で自動除外。
3. **`raw.financials.roe`**: 百分率表記(中央値7.5 = 7.5%)。`roe_is_percentage: true` / `roe_min: 8.0`。
   ±13000%級の外れ値があるため `roe_cap: 100.0` で異常値ガード(PBR 近似の発散防止)。
   eps 正値率 約87%(正12,594 / 非正1,879)。

## 指標の定義メモ

- SMA / リターン / 52w 高安 / ボラは **adj_close** ベース(分割・配当の不連続を回避)
- 売買代金は **close × volume**(実取引価格)
- 52w 高安は intraday high/low ではなく **adj_close ベース**(調整後 high/low が無いため)
- `PER = close / eps`、`PBR近似 = PER × clip(ROE, ±roe_cap) × roe_scale`(配当・純資産が入れば将来正確化)
- `composite_score` は業種内 PERCENT_RANK(PER昇順 / ROE降順 / 3Mリターン降順)の平均。小さいほど上位

## 既知の保留

- `financials` は 4/25 更新で停滞の可能性 → `fin_reported_at` を出力に併記し UI で鮮度判別
- 配当利回り・自己資本比率・PBR(正確値)は元データ未取得 → Phase 4+(EDINET 拡張)で対応
