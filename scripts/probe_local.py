"""Read-only sweep: which local-government codes exist in Sales' provinces (29 Oct 2026).

Local governments have 7-digit deptId codes: type + province + district + number, e.g. 2200101 อบจ.ชลบุรี,
3120101 เทศบาลนครนนทบุรี, 6200102 an อบต. in ชลบุรี (2 อบจ., 3 เทศบาลนคร, 4 เทศบาลเมือง, 5 เทศบาลตำบล,
6 อบต.). กรุงเทพมหานคร (3100001) is one feed that fills its 20 items a day; its purchasing units answer
as 15-digit deptsubId codes (310000110000330 รพ.ตากสิน). Asks for W0, the most frequent type, and prints
FOUND <param> <code> <items> for every code that answers with items. Touches no database.
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp.feed import fetch  # noqa: E402

# Province code -> number of districts (อำเภอ), the 14 target provinces outside Bangkok.
DISTRICTS = {"11": 6, "12": 6, "13": 7, "14": 16, "19": 13, "20": 11, "21": 8, "22": 10,
             "24": 11, "25": 7, "26": 4, "73": 7, "74": 3, "75": 3}
# How many numbers to try per district for each type.
PER_DISTRICT = {"3": 3, "4": 5, "5": 15, "6": 20}


def codes() -> list[tuple[str, str]]:
    out = [("deptId", f"2{p}0101") for p in DISTRICTS]
    for t, n in PER_DISTRICT.items():
        for p, d in DISTRICTS.items():
            for a in range(1, d + 2):  # one district more, in case the count is off
                out += [("deptId", f"{t}{p}{a:02d}{o:02d}") for o in range(1, n + 1)]
    out += [("deptsubId", f"31000011{n:07d}") for n in range(1, 1001)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-minutes", type=float, default=80)
    args = ap.parse_args()

    mine = [c for i, c in enumerate(codes()) if i % args.shards == args.shard]
    print(f"{len(mine)} codes on this shard", flush=True)
    started = time.monotonic()

    def one(pc):
        if time.monotonic() - started > args.max_minutes * 60:
            return pc, None
        return pc, fetch({pc[0]: pc[1], "anounceType": "W0"}, max_seconds=60, retries=2)

    failed = skipped = found = 0
    with ThreadPoolExecutor(args.workers) as ex:
        for (param, code), r in ex.map(one, mine):
            if r is None:
                skipped += 1
            elif not r.ok:
                failed += 1
                print(f"FAILED {param} {code} {r.error}", flush=True)
            elif r.items:
                found += 1
                print(f"FOUND {param} {code} {len(r.items)} | {r.items[0].get('title', '')[:80]}", flush=True)
    print(f"done: {found} found, {failed} failed, {skipped} skipped (time cap)", flush=True)


if __name__ == "__main__":
    main()
