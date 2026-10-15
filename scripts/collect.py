"""Collect announcements from the e-GP RSS feed into data/runs/<mode>/<date>/<HHMM>[-s<k>]/.

Modes:
  daily   - nationwide + every active department (Supabase `departments`) x DAILY_TYPES.
            --shard k --shards n splits the departments so n machines (each with its own IP)
            can share the work; the server answers HTTP 429 above ~2 parallel requests per IP.
  capped  - only the (department, type) feeds that hit the 20-item cap in the last 7 days
            (Supabase `capped_feeds`), re-read during the afternoon so busy departments lose less.
  sweep   - deptId codes --start..--end that are not known yet, with W0 (the most frequent type,
            ~1,300 a week), to discover departments that exist. Run by hand, in chunks.

Each run writes requests.jsonl (one line per feed request) and items.jsonl (one line per RSS item);
scripts/load_runs.py loads them into Supabase.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp.db import DB  # noqa: E402
from egp.feed import fetch  # noqa: E402

BKK = ZoneInfo("Asia/Bangkok")
ROOT = os.path.join(os.path.dirname(__file__), "..")

# The types the digest uses. W1/W2 (cancelled/changed winners) are never shown.
DAILY_TYPES = ["P0", "15", "B0", "D0", "W0", "D1", "D2"]
NATIONWIDE = "(ไม่ระบุหน่วยงาน)"


def build_requests(db: DB, args) -> list[tuple[dict, dict]]:
    """(params, extra) pairs. extra is stored next to each item (dept_name)."""
    if args.mode == "daily":
        depts = db.select("departments", param="eq.deptId", active="is.true", select="code,name",
                          order="code")
        mine = [d for i, d in enumerate(depts) if i % args.shards == args.shard]
        reqs = [({"anounceType": t}, {"dept_name": NATIONWIDE}) for t in DAILY_TYPES] if args.shard == 0 else []
        reqs += [({"deptId": d["code"], "anounceType": t}, {"dept_name": d["name"]})
                 for d in mine for t in DAILY_TYPES]
        return reqs
    if args.mode == "capped":
        feeds = db.rpc("recent_capped_feeds", {"p_days": 7})
        return [({"deptId": f["dept_code"], "anounceType": f["announce_type"]}, {"dept_name": f["dept_name"]})
                for f in feeds]
    if args.mode == "sweep":
        known = {d["code"] for d in db.select("departments", select="code")}
        return [({"deptId": f"{n:04d}", "anounceType": "W0"}, {"dept_name": ""})
                for n in range(args.start, args.end + 1) if f"{n:04d}" not in known]
    raise ValueError(args.mode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["daily", "capped", "sweep"], required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--start", type=int, default=1, help="sweep: first deptId number")
    ap.add_argument("--end", type=int, default=9999, help="sweep: last deptId number")
    ap.add_argument("--max-minutes", type=float, default=170,
                    help="stop sending new requests after this long and keep what was collected")
    args = ap.parse_args()

    now = datetime.now(BKK)
    suffix = f"-s{args.shard}" if args.shards > 1 else ""
    out_dir = os.path.join(ROOT, "data", "runs", args.mode, now.strftime("%Y-%m-%d"), now.strftime("%H%M") + suffix)
    os.makedirs(out_dir, exist_ok=True)

    reqs = build_requests(DB(), args)
    print(f"{now:%Y-%m-%d %H:%M} BKK | mode={args.mode} shard={args.shard}/{args.shards} | "
          f"{len(reqs)} requests | workers={args.workers}", flush=True)

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
