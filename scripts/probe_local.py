"""Sweep for local-government codes in Sales' provinces; with --save, new ones join the daily collection.

Local governments have 7-digit deptId codes: type + province + district + number, e.g. 2200101 อบจ.ชลบุรี,
3120101 เทศบาลนครนนทบุรี, 6200102 an อบต. in ชลบุรี (2 อบจ., 3 เทศบาลนคร, 4 เทศบาลเมือง, 5 เทศบาลตำบล,
6 อบต.). กรุงเทพมหานคร (3100001) is one feed that fills its 20 items a day; its purchasing units answer
as 15-digit deptsubId codes (310000110000330 รพ.ตากสิน). Found 29 Oct 2026 (815 + 18).

A code counts as found when W0 (the most frequent type) or, failing that, P0 answers with items, so a
local government with no winner announced that week is still found by its plans. Run monthly by
local-sweep.yml (Supabase pg_cron), because a code with nothing published in the feed's window is missed.
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp.feed import fetch  # noqa: E402

# Province code -> (name, number of districts), the 14 target provinces outside Bangkok.
PROVINCES = {"11": ("สมุทรปราการ", 6), "12": ("นนทบุรี", 6), "13": ("ปทุมธานี", 7),
             "14": ("พระนครศรีอยุธยา", 16), "19": ("สระบุรี", 13), "20": ("ชลบุรี", 11),
             "21": ("ระยอง", 8), "22": ("จันทบุรี", 10), "24": ("ฉะเชิงเทรา", 11), "25": ("ปราจีนบุรี", 7),
             "26": ("นครนายก", 4), "73": ("นครปฐม", 7), "74": ("สมุทรสาคร", 3), "75": ("สมุทรสงคราม", 3)}
# Type -> (name, how many numbers to try per district). The first sweep stopped at 20 อบต. and found
# number 20 in เมืองนครปฐม, so the ranges have room above what was found.
TYPES = {"3": ("เทศบาลนคร", 4), "4": ("เทศบาลเมือง", 8), "5": ("เทศบาลตำบล", 20), "6": ("อบต.", 30)}
BMA_UNITS = 1000  # 31000011 + 7 digits; the first sweep found units up to 368


def codes() -> list[tuple[str, str]]:
    out = [("deptId", f"2{p}0101") for p in PROVINCES]
    for t, (_, n) in TYPES.items():
        for p, (_, d) in PROVINCES.items():
            for a in range(1, d + 2):  # one district more, in case the count is off
                out += [("deptId", f"{t}{p}{a:02d}{o:02d}") for o in range(1, n + 1)]
    out += [("deptsubId", f"31000011{n:07d}") for n in range(1, BMA_UNITS + 1)]
    return out


def name(param: str, code: str) -> str:
    """Placeholder until enrich.py reads the real name from a document (set_department_name)."""
    if param == "deptsubId":
        return f"หน่วยงานรหัส {code} (กรุงเทพมหานคร)"
    kind = "อบจ." if code[0] == "2" else TYPES[code[0]][0]
    return f"หน่วยงานรหัส {code} ({kind} จ.{PROVINCES[code[1:3]][0]})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-minutes", type=float, default=150)
    ap.add_argument("--save", action="store_true", help="add found codes to departments (needs Supabase)")
    args = ap.parse_args()

    db = known = None
    if args.save:
        from egp.db import DB
        db = DB()
        known = set()
        while True:  # the API returns at most 1,000 rows per call
            page = db.select("departments", select="code", order="code", limit=1000, offset=len(known))
            known |= {r["code"] for r in page}
            if len(page) < 1000:
                break
    todo = [c for c in codes() if not known or c[1] not in known]
    mine = [c for i, c in enumerate(todo) if i % args.shards == args.shard]
    print(f"{len(mine)} codes on this shard ({len(known or ())} departments known)", flush=True)
    started = time.monotonic()

    def one(pc):
        param, code = pc
        for t in ("W0", "P0"):
            if time.monotonic() - started > args.max_minutes * 60:
                return pc, None
            r = fetch({param: code, "anounceType": t}, max_seconds=60, retries=2)
            if not r.ok or r.items:
                return pc, r
        return pc, r

    failed, skipped, found = [], 0, []
    with ThreadPoolExecutor(args.workers) as ex:
        for (param, code), r in ex.map(one, mine):
            if r is None:
                skipped += 1
            elif not r.ok:
                failed.append(code)
                print(f"FAILED {param} {code} {r.error}", flush=True)
            elif r.items:
                found.append({"code": code, "param": param, "name": name(param, code),
                              "source": "probe_local", "active": True})
                print(f"FOUND {param} {code} {len(r.items)} | {r.items[0].get('title', '')[:80]}", flush=True)
    if db and found:
        db.upsert("departments", found, on_conflict="code")
    print(f"done: {len(found)} found{' and saved' if db and found else ''}, {len(failed)} failed "
          f"(tried again next sweep), {skipped} skipped (time cap)", flush=True)


if __name__ == "__main__":
    main()
