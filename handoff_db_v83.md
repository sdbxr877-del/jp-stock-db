# handoff_db_v83.md — v82以降の未記録差分の訂正（2026-09-12）

本ファイルは `handoff_db_v82.md` を置き換えるものではなく、v82作成後に別セッションで
実施・commit・push済みだった作業をv82に追記する訂正版。今回、cw-auto-collector等の
他プロジェクトと合わせて second-brain 運用の一元化セッション内で実測・作成した。

**運用変更（本セッションで確定）**: jp_stock_dbは今後、Web Claude（Project知識ベース）と
Claude Code（ファイル編集専用）とユーザーのPowerShell実行に3分割する従来方式ではなく、
第二の脳（second-brain）配下の他プロジェクトと同じく、単一のCoworkセッション内で
（a）現物ファイルの直接読み書き、（b）ユーザーのPC上でのgit/bq実行（device経由）、
（c）Tier A操作のみ事前確認、という一元運用に統合する。以後のnext_session_prompt冒頭も
このセッションへ渡す想定に切り替える。

---

## §1. v82以降に判明した差分（実測: 2026-09-12）

v82のhandoff作成後、**v82自身のHEAD `80451f7cd3503d5019f325733c4174ec3d69f37e` から
さらに3コミット**が既にpush済みだった（v83引き継ぎドキュメントの作成だけが漏れていた）。

```
a477bfa  2026-08-25  Wire supply_demand into 03_screening_candidates (50 -> 58 columns)
a22c72e  2026-08-25  Wire financial_distortion into 03_screening_candidates (43 -> 50 columns)
81be475  2026-08-20  Wire technicals_wilder into 03_screening_candidates (37 -> 43 columns)
                     + verify_03_dryrun.py 新規追加（パラメータ化 dry-run ゲート）
```

**つまりv82の「本日候補1（最優先）＝34/35/36/37を03へ結線する判断」は、
v82記載当時点ではまだ手つかずだったが、その後すでに完了している。**
`03_screening_candidates` は現在 **58列**（v82記載の37列から更新済み）。

## §2. 現HEAD時点の実測値（2026-09-12・本セッション実測）

```
HEAD = a477bfae184f8d0167e8e023fc2a60efc51e32b1（origin/main と一致）
tracked = 92 / sql = 38 / wf = 6 / untracked ≒ 329
h37 = acfc1baaef7faf32510bc8b6866448800efa2f25（不変）
h34 = 7352db32ebe86f32dce6f99380532d799465ce30（不変）
git status --short に A/M/D 行なし（未commit差分ゼロ、untrackedのみ）
RAW: 18テーブル / 10,598,095行 / 821.6 MB
screening_candidates: 336件 / fp=8421264652015289138 / mx=2026-09-11
  ★v82時点の344件・fpから変化。銘柄構成の自然な入れ替わりの可能性が高いが未確認。
今月クエリ消費: 0.0074 TB / 1TB・112 jobs（月替わりでリセット済と判断するのが妥当）
check_drift.py: drift_both_rows=0 / G3 PASS / exit=0
```

## §3. `.claude/rules/` 内訳（実測: 25件・v82補足の20件からさらに増加）

```
ルート          = 1  （README.md）
bq/            = 4
encoding/      = 1
general/       = 5
git/           = 3
process/       = 5
secrets/       = 3
shell/         = 1
yaml/          = 1
_process/      = 1
合計 = 25
```

`vault_status: draft` の残存は0件（本セッションで grep 確認済み）。
v82補足時点で draft だった新規5件（`general/dont-trust-success` 等）はレビュー済み・
active化済みとみて矛盾なし。

## §4. 【本日候補（v82記載）の更新】

- ~~候補1: `03`への結線判断~~ → **完了済（本ファイル§1参照）**
- 候補2以降（C17第3弾・C22バックテスト・ナレッジ更新・EDINET深掘り・GHA Node20対応等）は
  **v82記載のまま未着手**。次にjp_stock_dbへ着手する際は、この中から1つを選び
  「1ステップ1推奨・確認待ち」で進める。
- 追加で望ましい作業: `phase45_data_inventory.md` / `formula_inventory_v1.md` への
  v82の発見（`34`の中間欠落構造・RSI NULLの機序等）の反映（v82の候補4がまだ未処理）。

## §5. 未再測のまま（v82から持ち越し・本セッションでは範囲外につき未実施）

```
daily_update_prices_v3.py の母集団決定ロジック
jquants_update.py の V1/V2 の中身
GHA の Node.js 20 非推奨対応
raw 各テーブルの行数・サイズ内訳（合計のみ本セッションで再確認）
```

---

最終更新: 2026-09-12（second-brain 一元化セッション内で作成・訂正版）
