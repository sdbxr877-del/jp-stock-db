"""tests/test_edinet_parse_regression.py

edinet_import.parse_csv の連結/個別解決ロジックに対する固定ケース回帰テスト。

目的:
  parse_csv を変更した際、既知の4類型で値が退行していないことを検出する。
    4080 型 : 連結財務諸表を持たない単体決算会社(net_income が全年 None)
    5191 型 : Member 候補のみ + IFRS 連結あり
    6758 型 : 金融コングロ型 IFRS
    4502/4568 型 : 標準製薬型 IFRS(op は endswith 3段 tier)

方式:
  - parse_csv(csv_bytes) は純関数なので、EDINET CSV バイト列を fixture に固定すれば
    決定論的に比較できる。
  - fixture は tests/fixtures/<docID>.csv に生バイトでキャッシュ(.gitignore 済・未追跡)。
    欠落時のみ edinet_import.download_csv_bytes で取得する。
  - 期待値は BigQuery raw.financials(source='edinet')の実測値。
    equity 列は BQ に存在しない(roe に逆算格納)ため、期待値は v48 セッションで
    parse_csv の実測値を固定したもの。

使い方:
    python tests\\test_edinet_parse_regression.py
  終了コード 0 = 全ケース一致 / 1 = 差分あり or 取得失敗
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import edinet_import as E  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SLEEP_SEC = 1.2
ASSERT_KEYS = ["revenue", "op_profit", "net_income", "eps", "rd_expenses", "equity"]

# (ticker, fiscal_year, docID, (revenue, op_profit, net_income, eps, rd_expenses, equity))
CASES = [
    ("4080", "22/3", "S100OF41", (40531.32, 769.06, None, 22.5, 945.0, 13360.15)),
    ("4080", "23/3", "S100R2IJ", (57672.0, 1579.0, None, 39.66, 971.0, 14657.0)),
    ("4080", "24/3", "S100TVN2", (47987.0, 2782.0, None, 78.57, 1020.0, 17234.0)),
    ("4080", "25/3", "S100W16T", (36497.0, -373.0, None, -7.93, 647.0, 16841.0)),
    ("4502", "21/3", "S100LR7D", (3197812.0, 509269.0, 376005.0, 240.72, 455833.0, 4434889.0)),
    ("4502", "22/3", "S100OBQE", (3569006.0, 460844.0, 230059.0, 147.14, 526100.0, 4294899.0)),
    ("4502", "23/3", "S100R3K7", (4027478.0, 490505.0, 317017.0, 204.29, 633300.0, 4206219.0)),
    ("4502", "24/3", "S100TNTP", (4263762.0, 214075.0, 144067.0, 92.09, 729900.0, 4088198.0)),
    ("4502", "25/3", "S100W07G", (4581551.0, 342586.0, 107928.0, 68.36, 730200.0, 3989355.0)),
    ("4502", "26/3", "S100YB5L", (4505720.0, 6217.0, -152390.0, -96.75, 675900.0, 3758926.0)),
    ("4568", "21/3", "S100LKS9", (962516.0, 63795.0, 75958.0, 39.17, 227400.0, 1272053.0)),
    ("4568", "22/3", "S100ODRB", (1044892.0, 73025.0, 66972.0, 34.94, 260200.0, 1350872.0)),
    ("4568", "23/3", "S100QYCY", (1278478.0, 120580.0, 109188.0, 56.96, 341600.0, 1445854.0)),
    ("4568", "24/3", "S100TLVV", (1601688.0, 211588.0, 200731.0, 104.69, 365200.0, 1688173.0)),
    ("4568", "25/3", "S100W17I", (1886256.0, 331925.0, 295756.0, 155.96, 436000.0, 1623416.0)),
    ("4568", "26/3", "S100YEY0", (2123045.0, 229089.0, 259874.0, 140.44, 466000.0, 1664179.0)),
    ("5191", "22/3", "S100O9PM", (445985.0, 1110.0, -6357.0, -61.23, 14302.0, 157876.0)),
    ("5191", "23/3", "S100QYFA", (541010.0, 16560.0, 6683.0, 64.37, 14377.0, 167105.0)),
    ("5191", "24/3", "S100TONQ", (615449.0, 33977.0, 18641.0, 179.54, 16758.0, 196364.0)),
    ("5191", "25/3", "S100VZJC", (633331.0, 41573.0, 27419.0, 264.09, 18249.0, 214767.0)),
    ("6758", "22/3", "S100OJ0K", (9921513.0, 1202339.0, 882178.0, 711.84, 618400.0, 7144471.0)),
    ("6758", "23/3", "S100QZT6", (11539837.0, 1208206.0, 937126.0, 758.38, 735700.0, 7229709.0)),
    ("6758", "24/3", "S100TS7P", (13020768.0, 1208831.0, 970573.0, 788.29, 742800.0, 7587177.0)),
    ("6758", "25/3", "S100W19Q", (12957064.0, 1407163.0, 1141600.0, 188.71, 734600.0, 8179745.0)),
    ("6758", "26/3", "S100YE2C", (12479620.0, 1447507.0, -326865.0, -54.7, 762000.0, 8119011.0)),
]


def load_fixture(doc_id):
    """fixture を返す。無ければ EDINET から取得してキャッシュする。"""
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    path = os.path.join(FIXTURE_DIR, doc_id + ".csv")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read(), False
    data = E.download_csv_bytes(doc_id)
    if data is None:
        return None, True
    with open(path, "wb") as f:
        f.write(data)
    time.sleep(SLEEP_SEC)
    return data, True


def eq(actual, expected):
    if expected is None or actual is None:
        return actual is expected or actual == expected
    try:
        return abs(float(actual) - float(expected)) <= max(0.01, abs(float(expected)) * 1e-9)
    except (TypeError, ValueError):
        return False


def main():
    failures = []
    fetched = 0
    equity_report = []
    for i, (ticker, fy, doc_id, expected) in enumerate(CASES, 1):
        data, was_fetched = load_fixture(doc_id)
        if was_fetched:
            fetched += 1
        if data is None:
            print("[%d/%d] %s %s %s: DOWNLOAD_FAIL" % (i, len(CASES), ticker, fy, doc_id))
            failures.append((ticker, fy, doc_id, "DOWNLOAD_FAIL", None, None))
            continue
        r = E.parse_csv(data)
        equity_report.append((ticker, fy, r.get("equity")))
        bad = []
        for field, exp in zip(ASSERT_KEYS, expected):
            act = r.get(field)
            if not eq(act, exp):
                bad.append(field)
                failures.append((ticker, fy, doc_id, field, exp, act))
        status = "OK" if not bad else "MISMATCH:" + ",".join(bad)
        print("[%d/%d] %s %s %s %s" % (i, len(CASES), ticker, fy, doc_id, status))

    print("")
    print("--- equity 実測値(参考出力) ---")
    for ticker, fy, val in equity_report:
        print("%s %s equity=%s" % (ticker, fy, val))

    print("")
    print("cases=%d fetched=%d cached=%d failures=%d"
          % (len(CASES), fetched, len(CASES) - fetched, len(failures)))
    if failures:
        print("")
        print("--- FAILURES ---")
        for ticker, fy, doc_id, field, exp, act in failures:
            print("%s %s %s %s expected=%s actual=%s" % (ticker, fy, doc_id, field, exp, act))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
