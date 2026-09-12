---
name: jp-stock-db-rules
description: jp_stock_db（東証銘柄の株価・財務データ分析パイプライン）固有の恒久的な安全ルール。このプロジェクトを扱うセッションでは必ず参照し、Tier A判断の根拠とする。
---

# jp_stock_db 恒久ルール

全プロジェクト共通の進め方は `skills/common/SKILL.md` を参照。本Skillはjp_stock_db固有の「安全上の恒久的な一線」を定める。

## 恒久ルール（Tier A）

1. **役割分担を守る。** 実ファイルの書き込みはClaude Code、設計はWeb Claude（Cowork側）が担当する。git・BigQuery・pythonの実行はユーザーがPowerShellで実測し、Web Claude側では実行しない。
2. **推測でSSOT（仕様）を埋めない。** ナレッジ現物か実測での裏取りができない内容は、仕様として確定させない。
3. **テスト実行は`raw.prices_test_staging`限定。** `--limit` / `--ticker` 等のテスト実行を本番`raw.prices`に書き込まない（過去に混入事故あり）。
4. **以下は自律実行禁止・事前承認必須（CLAUDE.md §9より）：**

   | 操作コード | 内容 |
   |---|---|
   | RM_RF_ANY_DIR | rm -rf / Remove-Item -Recurse の本実行 |
   | DROP_TABLE / TRUNCATE_TABLE / ALTER_TABLE | 任意の発行（staging含む全て要承認） |
   | DML_ON_RAW_PROD | raw.prices / raw.tickers / raw.financials への DML |
   | GIT_PUSH / GIT_FORCE_PUSH | push（force pushは全環境で例外なく禁止） |
   | GHA_DISPATCH | workflow_dispatch trigger（手動実行） |
   | ENV_VAR_PRINT | os.environ.get() の値をprint |
   | SUDO_INSTALL | winget / choco / pip系のグローバルインストール |

## 位置づけ

- 本Skillと `skills/common/SKILL.md` の内容が矛盾するように見える場合は、本Skillを優先する
- 詳細な背景は `second-brain_命令書.md` 5章を参照する
