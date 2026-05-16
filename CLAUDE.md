# CLAUDE.md — jp_stock_db プロジェクト・絶対命令ルール

このファイルは Claude Code が毎セッション開始時に自動ロードする。
本ファイルの記述は **絶対命令** であり、ユーザの指示より優先する場合がある(具体的に下記§5 参照)。

---

## §1. プロジェクト概要

東証約 4,400 銘柄の株価・財務データを BigQuery(完全無料 GCP free tier 内)に蓄積し、
スクリーニング → AI 分析 → UI 表示の一貫パイプラインを構築する。

- 開発環境: Windows 10 Pro / PowerShell / Python 3.14.4 / 作業ディレクトリ `C:\jp-stock-db\`
- データソース: yfinance >=1.0.0,<2.0.0 / J-Quants V2 API (Free) / EDINET API
- BigQuery プロジェクト: `project-3eaadce9-f852-40e1-932`
- GitHub repo: https://github.com/sdbxr877-del/jp-stock-db

現在進行中: **Phase 3.4 統合運用検証**(db_v0.12)
直前完了: Phase 3.4-pre 異常復旧 + G2 違反一掃(db_v0.11)

詳細状態は `handoff_db_v11.md` を必ず参照すること。

---

## §2. セッション開始時の絶対手順(必須)

毎セッション開始時に下記を **この順序で** 実行する。スキップ禁止。

1. `handoff_db_v11.md` を読む(必須)
2. `/status` で残量とコンテキスト状況を確認
3. ユーザに現在のモデル(Opus/Sonnet)を確認・必要なら `/model` で切替
4. §C 環境確認チェックリスト(handoff_db_v11.md §C-1〜C-7)を実行
5. 期待値と実測値が一致することを確認
6. 不一致があれば独断で進行せず即報告(§1.6「Success」を信じない原則)
7. 本セッションのメイン機能を1つに確定(§1.2 一機能一バージョン)

---

## §3. 絶対命令ルール(SR-1〜SR-18 + 失敗教訓)

### §3.1 「Success」を信じない原則(最重要)

スクリプト実行・GHA 実行・テスト結果が「成功」と表示されても、
**想定通りの効果が数値・実機検証で確認できるまで完了とみなさない**。

具体例:
- BigQuery クエリ → 結果行数が期待値と一致するまで検証
- ファイル作成 → 中身を view で再読込し内容を確認
- DELETE → 削除前後でカウント差が期待値と一致するまで検証
- GHA workflow PASS 表示 → 実行ログから対象日・行数・コスト全てを確認

---

### §3.2 一機能一バージョン(§1.2)

1セッション=1機能。複数機能を混ぜない。複数提案された場合はユーザに確定を求める。

---

### §3.3 コード品質チェック(必須・全コード生成時)

新規・修正ファイル作成後は **必ず以下を順番に実行**:

1. UTF-8 検証: `python verify_utf8.py <file>.py`
2. 構文検証: `python -m py_compile <file>.py`
3. G2 Secrets 監査:
   - PowerShell: `Select-String -Path <file>.py -Pattern "print.*token|print.*key|print.*secret|print.*password"`
   - Bash 等価: `grep -nE 'print.*token|print.*key|print.*secret|print.*password' <file>.py`
   - **両 case mode で 0 hit** を確認(失敗39 教訓: case-sensitive と case-insensitive 両方)

合法ヒットリスト(2026-05-16 時点):
- `edinet_fetch_index.py:164` (EDINET 環境変数読込)
- `patch_daily_yml_v3.py:30, 31, 89` (G2 監査ロジック自体)
- `write_jquants_yaml.py:118` (G2 監査ロジック自体)
- `write_yaml.py:70` (G2 監査ロジック自体)
- `.claude/internal/_write_pre_commit.py:20, 21, 29` (pre-commit hook 生成スクリプト - G2 監査パターンを文字列として内包)

これら以外で hit したら **「誤検知だから OK」と独断判定禁止**(失敗39 教訓)。即修正。

---

### §3.4 BigQuery 操作ルール(SR-1〜SR-3 関連)

- **DRY RUN 必須**: 全クエリで `bigquery.QueryJobConfig(dry_run=True)` を先行実行
- **MAX_SCAN_GB = 1.5**: DRY RUN 結果が 1.5 GB を超えたら実行禁止・即停止
- **パーティションフィルタ必須**: `raw.prices` は PARTITION BY date / `WHERE date IN/=/BETWEEN ...` で日付指定必須
- **SELECT * 禁止**: 必ず明示列指定
- **ストリーミング挿入禁止**: load job または DML のみ使用
- **DELETE+INSERT パターン**(失敗41 教訓): MERGE ではなく `BEGIN TRANSACTION; DELETE; INSERT; COMMIT;` で 0 byte 課金実現

---

### §3.5 段階テストルール(SR-11)

書込系操作は **DRY → CONFIRM** の2段階:

1. `--dry` モードで対象範囲・行数を確認
2. 期待値と一致したら `--confirm` で本実行
3. 実行後、検証クエリで結果を再確認

DRY RUN 単独で品質保証としない(SR-11 厳守)。
少銘柄スケールから本番投入(例: 1ティッカー → 10 → 全件)。

---

### §3.6 PowerShell ルール(SR-12 / SR-15)

- `python -c "..."` でバッククォート含む SQL を渡さない(SR-12: PowerShell エスケープ問題)
- 必ず `python <file>.py` 形式で独立スクリプトとして実行
- 1コマンド = 1コードブロック表示(対話的説明時)

---

### §3.7 YAML/設定ファイル生成(SR-13)

YAML や JSON 設定ファイルは PowerShell heredoc では絶対に作らない(YAML が壊れる)。
必ず Python スクリプト(`write_yaml.py` 等)で生成する。

---

### §3.8 UTF-8 必須(SR-14)

全 Python スクリプト・YAML・MD ファイルは UTF-8 BOM なし。
Shift-JIS / CP932 は GHA Ubuntu runner で失敗する。

---

### §3.9 GHA pre-flight シミュレート(SR-17)

`.github/workflows/*.yml` の各 step に書かれた bash コマンドは、
ローカルで bash 実機シミュレートしてから push する。

---

### §3.10 集約関数の精度確認(SR-18)

SUM / AVG / MIN / MAX 使用時は対象行数と NULL 比率を必ず確認。
`BIT_XOR(FARM_FINGERPRINT(TO_JSON_STRING(STRUCT(全列))))` を行レベル等価検証に使用可能。

---

## §4. リリースゲート(commit/push 前必須)

下記 G1〜G10 が全て緑になるまで commit/push しない。
**Pre-commit hook で自動チェック**(本リポジトリの `.git/hooks/pre-commit`)。

| ゲート | 内容 | 自動化方法 |
|---|---|---|
| G1 | 構文エラー 0 | `python -m py_compile` |
| G2 | Secrets ログなし(両 case mode) | `grep -nE` + `grep -niE` |
| G3 | BQ DRY RUN ≤ 1.5 GB | スクリプト内で検証 |
| G4 / G9 | 重複なし | `python dedup_check.py` |
| G5 | handoff §B 進捗更新済 | 手動確認(セッション末) |
| G6 | リリース判定 | 手動確認(セッション末) |
| G7 | requirements.txt 整合 | 手動確認 |
| G8 | テスト PASS | (該当時のみ) |
| G10 | GHA bash pre-flight PASS | bash でシミュレート |

---

## §5. Claude Code 特有の絶対命令(失敗43 教訓を踏まえた追加ルール)

### §5.1 本番テーブルへの書込は事前承認制

下記操作はユーザの**明示的な承認なしに自律実行禁止**:

- `raw.prices` への INSERT / UPDATE / DELETE / MERGE
- `raw.tickers` への変更
- `raw.financials` への変更
- 任意のテーブルの DROP / TRUNCATE
- スキーマ変更(ALTER TABLE)
- GitHub への push
- 任意の workflow_dispatch trigger

**実行前に必ず**:
1. 「これから実行する操作: ...」と明示
2. DRY RUN 結果を提示
3. 期待値と実測値の整合確認
4. **ユーザの「実行してよい」の確認を待つ**

### §5.2 テスト系スクリプトは staging テーブル限定

`daily_update_prices_v3.py --limit N` や `--ticker T` などのテスト実行は、
本番 `raw.prices` ではなく **`raw.prices_test_staging` テーブルにのみ書き込む**。

(失敗43 教訓: db_v0.10 で --limit 20 + --ticker 7203 のテスト残骸が本番に書き込まれていた事故の構造的対策)

Phase 3.4 D6.1 で `daily_update_prices_v3.py` を改修するまでは、
テスト実行を要求された場合は**まずユーザに「staging に書きますか?本番に書きますか?」と確認**。

### §5.3 自動再実行・自走の禁止

リミット到達後の自動リトライループや、
ユーザ不在での連続自走は禁止。
各機能区切りで必ず実行結果をユーザに提示し、次へ進む確認を取る。

### §5.4 環境変数の表示禁止

`os.environ.get(...)` の値を print してはならない。
`echo $env:JQUANTS_API_KEY` のような PowerShell コマンドも実行禁止。

### §5.5 SR-15/SR-16 の扱い変更

Claude Code は直接ファイル作成・コマンド実行できるため:
- SR-15(PowerShell コードブロック配信)→ **不要化**(直接実行)
- SR-16(ファイル配信予告)→ **作業ログとして記録**(配信ではなく直接保存)

ただし**ユーザに見せるためのコマンド表示**は引き続き SR-15 形式で。

---

## §6. リミット管理戦略

### §6.1 Pro プランの制約

- **5時間セッションウィンドウ**: 約 200〜800 Claude Code プロンプト
- **週次キャップ**: Sonnet 約 240〜480 時間/週 / Opus 約 24〜40 時間/週
- Web/モバイル Claude と Claude Code は使用量共有
- **自動再開なし**: リミット到達でハードストップ → 手動 `claude --continue` 再開

### §6.2 モデル使い分け(Opus 週次キャップ温存)

| 作業性質 | モデル | 例 |
|---|---|---|
| **判断系・監査系・原因究明** | Opus | 失敗教訓の真因特定 / 復旧戦略立案 / 重要 PR レビュー |
| **実装・コーディング・ルーチン** | Sonnet | スクリプト書き起こし / 単純な修正 / ログ確認 |
| **観測・データ集計** | Sonnet | source_check.py 実行 / dedup_check.py 実行 |

切替コマンド: `/model claude-opus-4-7` / `/model claude-sonnet-4-6`

**デフォルトは Sonnet**、判断局面のみ Opus に切替。完了後は Sonnet に戻す。

### §6.3 セッション設計

- **§1.2 一機能一バージョン** が 5時間ウィンドウとも整合
- 1機能 ≒ 1セッション ≒ 5時間以内に収める
- リミット表示が出たら必ずユーザに報告し、リセット時刻を伝える

### §6.4 CLAUDE.md スリム化

CLAUDE.md は毎回ロードされるため、肥大化はトークン消費を増やす。
- handoff_db_v11.md の全文を CLAUDE.md にコピーしない(参照のみ)
- 過去の履歴は `handoff_db_v06〜v10.md` を参照
- 失敗教訓も**最新の3〜5件のみ抜粋**

---

## §7. 環境情報(変更不要)

### §7.1 GCP / BigQuery

- Project ID: `project-3eaadce9-f852-40e1-932`
- Service Account: `jp-stock-db-sa@project-3eaadce9-f852-40e1-932.iam.gserviceaccount.com`
- WIF Pool: `github-actions-pool` / Provider: `github-provider`
- Project Number: `874756684682`
- ロール: `roles/bigquery.jobUser` + `roles/bigquery.dataEditor`

### §7.2 環境変数

- `JQUANTS_API_KEY`: J-Quants V2 認証(.env または GitHub Secrets)
- `EDINET_API_KEY`: EDINET 補完用(将来 Phase 2.5)
- `GOOGLE_APPLICATION_CREDENTIALS`: ローカル BQ 認証(WIF または SA キー)

これらの **値を print 文に出力してはならない**(失敗39 教訓)。

### §7.3 主要スクリプト

| ファイル | 役割 |
|---|---|
| `daily_update_prices_v3.py` | yfinance 毎日更新(Phase 3.2 凍結中) |
| `jquants_update.py` (rev5) | J-Quants 13週前直近営業日補完 |
| `jquants_test_fetch.py` (rev2) | J-Quants 単体動作確認 |
| `check_max_date.py` | 件数サマリ |
| `dedup_check.py` | G9 重複検査 |
| `verify_utf8.py` | UTF-8 検証(SR-14) |
| `source_check.py` | source 別件数 |
| `rescue_drop_2026_04_27_28.py` | 04-27/04-28 partition 空白化(完了済) |
| `diag_recent_partitions.py` / `diag_21rows_detail.py` | 診断用 |

---

## §8. 失敗教訓(最新4件・他は handoff_db_v06〜v11.md 参照)

| # | 概要 | 教訓 |
|---|---|---|
| 失敗39 | print 文に env var name を含めて Secret 監査が hit | 変数名は変数経由で出力・両 case mode 検証 |
| 失敗41 | MERGE で全パーティションスキャン課金 | DELETE+INSERT in transaction で 0 byte 課金 |
| **失敗43** | **テスト実行 (--limit/--ticker) が本番テーブルに残留** | **テスト系は staging 限定・本番書込は事前承認** |
| 失敗44 (観察) | GHA scheduled cron 発火時刻が yml 設定と乖離 | 実害なし・db_v0.12 D0.1 で再観測 |

---

## §9. 危険操作の禁止リスト(自律実行禁止・ユーザ承認必須)

```
RM_RF_ANY_DIR        rm -rf / Remove-Item -Recurse の本実行
DROP_TABLE           DROP TABLE 任意の発行
TRUNCATE_TABLE       TRUNCATE TABLE 任意の発行(staging 含む全て要承認)
ALTER_TABLE          ALTER TABLE 任意の発行
DML_ON_RAW_PROD      raw.prices / raw.tickers / raw.financials への DML
GIT_PUSH             git push origin main(任意のブランチ)
GIT_FORCE_PUSH       git push --force(全環境で禁止・例外なし)
GHA_DISPATCH         workflow_dispatch trigger(手動実行)
ENV_VAR_PRINT        os.environ.get() の値を print
SUDO_INSTALL         winget / choco / pip 系のグローバルインストール
```

これらに該当する操作の前は必ず:
> 「これから {操作名} を実行します。理由: {根拠}。よろしいですか?」

と確認を求めること。

---

## §10. 緊急停止手順

Claude Code が暴走または誤操作した場合:

1. **Ctrl+C** で即中断
2. `/clear` で会話履歴リセット(コンテキスト汚染回復)
3. `/exit` でセッション終了
4. PowerShell に戻って状態確認:
   ```
   python check_max_date.py
   python dedup_check.py
   ```
5. BQ で誤書込が発生していたら `rescue_drop_*.py` パターンで復旧
6. ハンドオフに失敗教訓として記録

---

## §11. このファイルの更新ルール

- 失敗教訓が新規発生したら §8 に追記
- 新ルールが必要になったら §3 / §5 に追記し、`project_rules_db_v1.md` 本体も同時更新
- セッション末に handoff_db_v{N}.md を作成して状態スナップショット

---

最終更新: 2026-05-10 (db_v0.11 / handoff_db_v11.1 から生成)
