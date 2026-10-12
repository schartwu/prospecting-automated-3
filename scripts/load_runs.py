"""Load collected run folders (data/discovery/<mode>/<date>/<HHMM>) into Supabase.

Idempotent: each folder becomes one collect_runs row keyed by its path, and folders already loaded
are skipped. Announcements are upserted, so items repeated across runs are stored once.
"""
import csv
import glob
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp.db import DB  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
BKK = ZoneInfo("Asia/Bangkok")
BATCH = 500


def parse_item(row: dict) -> dict:
    """Map a raw RSS item (plus the request params we stored with it) to an announcements row.
    description is '<id>, <method>, <type label>'; id is an 11-digit project no, or P... for P0 plans."""
    parts = [p.strip() for p in (row.get("description") or "").split(",")]
    first = parts[0] if parts else ""
    method = parts[1].strip(" '") if len(parts) > 1 else None
    pub = row.get("pubDate") or ""
    return {
        "announce_type": row["anounceType"],
        "project_no": first if re.fullmatch(r"\d{11}", first) else None,
        "plan_no": first if re.fullmatch(r"P\d+", first) else None,
        "method": method or None,
        "title": row.get("title") or "",
        "link": row.get("link") or "",
        "description": row.get("description"),
        "pub_date": pub[:10] if re.match(r"\d{4}-\d{2}-\d{2}", pub) else None,
        "dept_code": row.get("deptId") or row.get("deptsubId"),
        "dept_name": row.get("dept_name"),
        "seen_at": row.get("fetched_at"),
        "raw": {k: v for k, v in row.items() if k not in ("fetched_at",)},
    }


def load_departments(db: DB):
    with open(os.path.join(ROOT, "data", "departments_v2.csv"), encoding="utf-8-sig") as f:
        rows = [{"code": r["code"], "param": r["param"], "name": r["name"], "source": "v2_list"}
                for r in csv.DictReader(f) if r["param"] in ("deptId", "deptsubId")]
    db.upsert("departments", rows, on_conflict="code")
    print(f"departments: {len(rows)} upserted")


def load_folder(db: DB, folder: str):
    source = os.path.relpath(folder, os.path.join(ROOT, "data")).replace(os.sep, "/")
    existing = db.select("collect_runs", source=f"eq.{source}", select="id,finished_at")
    if existing and existing[0]["finished_at"]:
        print(f"skip {source} (already loaded)")
        return

    with open(os.path.join(folder, "requests.jsonl"), encoding="utf-8") as f:
        reqs = [json.loads(line) for line in f]
    with open(os.path.join(folder, "items.jsonl"), encoding="utf-8") as f:
        items = [parse_item(json.loads(line)) for line in f]

    # Same item can come back from several requests in one run; the upsert needs each key once per batch.
    unique = list({(i["announce_type"], i["link"]): i for i in items if i["link"]}.values())

    _, mode, day, hhmm = source.split("/")
    started = datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H%M").replace(tzinfo=BKK)
    stats = {
        "source": source, "mode": mode, "started_at": started.isoformat(),
        "n_requests": len(reqs), "n_ok": sum(r["ok"] for r in reqs),
        "n_failed": sum(not r["ok"] for r in reqs), "n_items": len(items),
        "n_capped": sum(bool(r.get("capped")) for r in reqs),
    }
    # A run row without finished_at means an earlier load died midway: reuse it and finish the upsert.
    run = existing[0] if existing else db.insert("collect_runs", stats)[0]

    new = 0
    for i in range(0, len(unique), BATCH):
        new += db.rpc("upsert_announcements", {"p_run_id": run["id"], "p_items": unique[i:i + BATCH]})
    db.update("collect_runs", {"n_new_items": new, "finished_at": datetime.now(BKK).isoformat()},
              id=f"eq.{run['id']}")
    print(f"loaded {source}: {len(unique)} unique items, {new} new")


def main():
    db = DB()
    load_departments(db)
    folders = sorted(glob.glob(os.path.join(ROOT, "data", "discovery", "*", "*", "*")))
    for folder in folders:
        if os.path.exists(os.path.join(folder, "items.jsonl")):
            load_folder(db, folder)


if __name__ == "__main__":
    main()
