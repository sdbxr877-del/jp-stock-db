import os
import requests
from collections import Counter
from dotenv import load_dotenv

load_dotenv(dotenv_path=r"C:\jp-stock-db\.env")

TARGETS = ["2593", "5076", "7550", "9202", "9434"]


def fetch_master():
    cred = os.environ["JQUANTS_API_KEY"]
    r = requests.get(
        "https://api.jquants.com/v2/equities/master",
        headers={"x-api-key": cred},
    )
    if r.status_code != 200:
        raise RuntimeError(f"J-Quants error {r.status_code}: {r.text}")
    return r.json().get("data", [])


def main():
    print("=== probe_jquants_code_format.py / read only, no BigQuery ===")
    records = fetch_master()
    print(f"records: {len(records)}")

    codes = [str(r.get("Code", "")).strip() for r in records]
    codes = [c for c in codes if c]
    print(f"non empty codes: {len(codes)}")

    print("\n--- code length distribution ---")
    for k, v in sorted(Counter(len(c) for c in codes).items()):
        print(f"  len={k}: {v}")

    print("\n--- last char distribution ---")
    for k, v in sorted(Counter(c[-1] for c in codes).items()):
        print(f"  last={k}: {v}")

    print("\n--- head4 collision summary ---")
    head4 = Counter(c[:4] for c in codes)
    dup_heads = sorted([h for h, n in head4.items() if n > 1])
    print(f"  distinct head4: {len(head4)}")
    print(f"  head4 with more than one code: {len(dup_heads)}")
    print(f"  total codes in those groups: {sum(head4[h] for h in dup_heads)}")

    print("\n--- all colliding groups ---")
    by_head = {}
    for r in records:
        c = str(r.get("Code", "")).strip()
        if not c:
            continue
        by_head.setdefault(c[:4], []).append(r)
    for h in dup_heads:
        print(f"  head4={h}")
        for r in sorted(by_head[h], key=lambda x: str(x.get("Code", ""))):
            print(
                f"    Code={r.get('Code')} MktNm={r.get('MktNm')} CoName={r.get('CoName')}"
            )

    print("\n--- target tickers ---")
    for t in TARGETS:
        group = by_head.get(t, [])
        print(f"  target={t} count={len(group)}")
        for r in sorted(group, key=lambda x: str(x.get("Code", ""))):
            print(
                f"    Code={r.get('Code')} MktNm={r.get('MktNm')} CoName={r.get('CoName')}"
            )

    print("\n=== done ===")


if __name__ == "__main__":
    main()
