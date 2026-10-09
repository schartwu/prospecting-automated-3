"""Phase 0 discovery: collect raw e-GP RSS data for every announce type, so we can see
what P0 / 15 / B0 / W0 look like, how many arrive per day, and which feeds hit the 20-item cap.

Modes:
  types  - known department codes x every announce type (run several times a day)
  sweep  - every 4-digit deptId 0001-9999 to find which codes exist (run once, manually)

Output: data/discovery/<mode>/<YYYY-MM-DD>/<HHMM>/{requests,items}.jsonl
"""
import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp.feed import ANNOUNCE_TYPES, fetch  # noqa: E402

BKK = ZoneInfo("Asia/Bangkok")
ROOT = os.path.join(os.path.dirname(__file__), "..")


def load_departments():
    with open(os.path.join(ROOT, "data", "departments_v2.csv"), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# Lower rank is sent first, so a run cut short by the time budget still answers the main questions:
# known 4-digit depts and nationwide before 10-digit sub-units, and unknown-format codes last;
# within a group, early-warning types (P0, 15, B0) before the rest.
TYPE_ORDER = ["P0", "15", "B0", "D0", "W0", "D2", "D1", "W2", "W1"]


def build_requests(mode):
    """Return (params, extra) pairs, ordered by priority."""
    reqs = []

    def add(group, params, dept_name):
        reqs.append(((group, TYPE_ORDER.index(params["anounceType"])), params, {"dept_name": dept_name}))

    if mode == "types":
        # Nationwide (no department): does the feed accept it, and what does it return?
        for t in ANNOUNCE_TYPES:
            add(0, {"anounceType": t}, "(ไม่ระบุหน่วยงาน)")
        for d in load_departments():
            if d["param"] == "deptId":
                for t in ANNOUNCE_TYPES:
                    add(0, {"deptId": d["code"], "anounceType": t}, d["name"])
            elif d["param"] == "deptsubId":
                for t in ("P0", "D0"):
                    add(1, {"deptsubId": d["code"], "anounceType": t}, d["name"])
            else:
                # Codes of unknown format from the v2 list: try both parameters once.
                for p in ("deptId", "deptsubId"):
                    add(2, {p: d["code"], "anounceType": "D0"}, d["name"])
    elif mode == "sweep":
        for n in range(1, 10000):
            add(0, {"deptId": f"{n:04d}", "anounceType": "D0"}, "")
    reqs.sort(key=lambda r: r[0])
    return [(params, extra) for _, params, extra in reqs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["types", "sweep"], default="types")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0, help="only send the first N requests (testing)")
    ap.add_argument("--max-minutes", type=float, default=45,
                    help="stop sending new requests after this long and keep what was collected")
    args = ap.parse_args()

    now = datetime.now(BKK)
    out_dir = os.path.join(ROOT, "data", "discovery", args.mode, now.strftime("%Y-%m-%d"), now.strftime("%H%M"))
    os.makedirs(out_dir, exist_ok=True)

    reqs = build_requests(args.mode)
    if args.limit:
        reqs = reqs[: args.limit]
    print(f"{now:%Y-%m-%d %H:%M} BKK | mode={args.mode} | {len(reqs)} requests | workers={args.workers}", flush=True)

    deadline = time.monotonic() + args.max_minutes * 60
    ok = failed = n_items = capped = 0
    with open(os.path.join(out_dir, "requests.jsonl"), "w", encoding="utf-8") as freq, \
         open(os.path.join(out_dir, "items.jsonl"), "w", encoding="utf-8") as fitem, \
         ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch, p): extra for p, extra in reqs}
        for i, fut in enumerate(as_completed(futures), 1):
            r, extra = fut.result(), futures[fut]
            ok += r.ok
            failed += not r.ok
            n_items += len(r.items)
            capped += r.capped
            freq.write(json.dumps({
                **r.params, **extra, "ok": r.ok, "http": r.http_status, "error": r.error,
                "n_items": len(r.items), "capped": r.capped, "elapsed": round(r.elapsed, 2),
                "channel": r.channel,
            }, ensure_ascii=False) + "\n")
            for it in r.items:
                fitem.write(json.dumps({**r.params, **extra, "fetched_at": now.isoformat(), **it},
                                       ensure_ascii=False) + "\n")
            if i % 200 == 0:
                print(f"  {i}/{len(reqs)} ok={ok} failed={failed} items={n_items} capped={capped}", flush=True)
                freq.flush()
                fitem.flush()
            if time.monotonic() > deadline:
                pool.shutdown(wait=False, cancel_futures=True)
                print(f"  time budget of {args.max_minutes} min reached after {i}/{len(reqs)} requests", flush=True)
                break

    print(f"DONE ok={ok} failed={failed} items={n_items} capped_feeds={capped} -> {out_dir}", flush=True)


if __name__ == "__main__":
    main()
