import sys

HOOK_PATH = r"C:\jp-stock-db\.git\hooks\pre-commit"

content = r"""#!/bin/bash
# pre-commit hook: G1 / G2 / SR-14 自動チェック

set -euo pipefail

echo "===== G1: 構文チェック ====="
for f in $(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true); do
    [ -z "$f" ] && continue
    python -m py_compile "$f" || { echo "G1 FAIL: $f"; exit 1; }
done
echo "G1 PASS"

echo "===== G2: Secrets 監査 (両 case mode) ====="
for f in $(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true); do
    [ -z "$f" ] && continue
    cs=$(grep -cE "print.*token|print.*key|print.*secret|print.*password" "$f" || true)
    ci=$(grep -ciE "print.*token|print.*key|print.*secret|print.*password" "$f" || true)
    # 合法ヒットリスト
    case "$f" in
        edinet_*.py|patch_daily_yml_v3.py|write_yaml.py|write_jquants_yaml.py|.claude/internal/_write_pre_commit.py)
            continue ;;
    esac
    if [ "$cs" -gt 0 ] || [ "$ci" -gt 0 ]; then
        echo "G2 FAIL: $f (cs=$cs ci=$ci)"
        grep -niE "print.*token|print.*key|print.*secret|print.*password" "$f" || true
        exit 1
    fi
done
echo "G2 PASS"

echo "===== SR-14: UTF-8 検証 ====="
for f in $(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(py|md|yml|yaml)$' || true); do
    [ -z "$f" ] && continue
    python -c "
with open('$f', 'rb') as fp:
    fp.read().decode('utf-8')
" || { echo "SR-14 FAIL: $f"; exit 1; }
done
echo "SR-14 PASS"

echo "===== ALL GATES PASS ====="
"""

# LF 強制書込 (newline='\n' で CRLF を抑止)
with open(HOOK_PATH, "w", newline="\n", encoding="utf-8") as fh:
    fh.write(content)

# 検証
with open(HOOK_PATH, "rb") as fh:
    raw = fh.read()

errors = []
if raw[:3] == b"\xef\xbb\xbf":
    errors.append("BOM detected")
if b"\r\n" in raw:
    errors.append("CRLF detected")
if not raw.startswith(b"#!/bin/bash"):
    errors.append("shebang missing")

if errors:
    print("FAIL: " + ", ".join(errors))
    sys.exit(1)

line_count = raw.count(b"\n")
print(f"[OK] Written: {len(raw)} bytes, {line_count} lines, LF-only, no BOM")
print(f"[OK] Path: {HOOK_PATH}")
