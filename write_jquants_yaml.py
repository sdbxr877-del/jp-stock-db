"""
write_jquants_yaml.py - J-Quants 補完更新用 GitHub Actions YAML を書き込む (SR-12/SR-13準拠)

【目的】
  jquants_update.yml を新規作成・更新する際に使用。
  PowerShell @"..."@ ヒアドキュメントは ${{ }} を破壊するため使用禁止 (SR-13)。

【役割】
  J-Quants は yfinance の補完 (data_strategy_v2.md L57: 公式値で精度補正) として
  週次バッチ的に動かす. 13週前直近営業日のみを置換するため、
  新規データ追加ではなく既存パーティションの上書きに特化.

【トリガー】
  - cron: '30 23 * * 1-5'  (UTC 23:30 平日 = JST 翌朝 08:30)
    → yfinance daily の 16時間後に実行・DB アクセス競合なし
  - workflow_dispatch (手動)

【使用方法】
  cd C:\\jp-stock-db
  python write_jquants_yaml.py

【失敗教訓】
  - 失敗38 (pipefail): set -euo pipefail で tee の exit code 0 問題を完全回避
  - 失敗36: cron は 13週前という公式仕様の保守的設計 (12週遅延+1週マージン)
  - 失敗37: J-Quants は 1 req/日なので yfinance のような rate-limit 不要

【注意】
  Workload Identity の値はプロジェクト固有 (db_v0.9 で確立済).
"""
import sys
import os

# ===== プロジェクト固有定数 =====
WIF_PROVIDER = "projects/874756684682/locations/global/workloadIdentityPools/github-actions-pool/providers/github-provider"
SA_EMAIL     = "jp-stock-db-sa@project-3eaadce9-f852-40e1-932.iam.gserviceaccount.com"
OUTPUT_PATH  = r"C:\jp-stock-db\.github\workflows\jquants_update.yml"
# ================================

content = f"""\
name: J-Quants Daily Update (Backfill Correction)

on:
  schedule:
    - cron: '30 23 * * 1-5'  # UTC 23:30 平日 = JST 翌朝 08:30 (yfinance の16h後)
  workflow_dispatch:
    inputs:
      date:
        description: 'target date YYYYMMDD e.g. 20260130  (blank = 13 weeks ago)'
        required: false
        default: ''
      limit:
        description: 'process first N rows after fetch  (blank = all)'
        required: false
        default: ''
      dry:
        description: 'dry mode (fetch+staging only, skip DML)'
        required: false
        default: 'false'
        type: choice
        options:
          - 'false'
          - 'true'

permissions:
  contents: read
  id-token: write

jobs:
  jquants-update:
    name: J-Quants Backfill Correction
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v3
        with:
          workload_identity_provider: '{WIF_PROVIDER}'
          service_account: '{SA_EMAIL}'

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: |
          set -euo pipefail
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Syntax check G1
        run: |
          set -euo pipefail
          python -m py_compile jquants_update.py
          echo G1 PASS

      - name: Secrets audit G2
        run: |
          set -euo pipefail
          hits=$(grep -nE 'print.*token|print.*key|print.*secret|print.*password' jquants_update.py | wc -l)
          if [ "$hits" -gt 0 ]; then echo G2 FAIL; exit 1; fi
          echo G2 PASS

      - name: Run J-Quants update
        run: |
          set -euo pipefail
          ARGS=""
          DATE="${{{{ github.event.inputs.date }}}}"
          LIMIT="${{{{ github.event.inputs.limit }}}}"
          DRY="${{{{ github.event.inputs.dry }}}}"
          if [ -n "$DATE" ]; then ARGS="$ARGS --date $DATE"; fi
          if [ -n "$LIMIT" ]; then ARGS="$ARGS --limit $LIMIT"; fi
          if [ "$DRY" = "true" ]; then ARGS="$ARGS --dry"; fi
          echo "running: python jquants_update.py $ARGS"
          python jquants_update.py $ARGS 2>&1 | tee jquants_update.log
        env:
          JQUANTS_API_KEY: ${{{{ secrets.JQUANTS_API_KEY }}}}

      - name: Upload log artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: jquants-update-log-${{{{ github.run_id }}}}
          path: jquants_update.log
          retention-days: 30
"""

# YAML 検証
try:
    import yaml
    parsed = yaml.safe_load(content)
    # 構造の必須キーを確認
    assert "on" in parsed or True in parsed, "trigger key missing"
    assert "jobs" in parsed, "jobs key missing"
    assert "permissions" in parsed, "permissions key missing"
    print("YAML検証: OK (構造妥当)")
except ImportError:
    print("YAML検証: PyYAMLなし (スキップ)")
except AssertionError as e:
    print(f"YAML構造エラー: {e}")
    sys.exit(1)
except Exception as e:
    print(f"YAML検証エラー: {e}")
    sys.exit(1)

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "w", encoding="utf-8", newline="\n") as f:
    f.write(content)
print(f"書き込み完了: {OUTPUT_PATH}")
print(f"行数: {len(content.splitlines())}")
