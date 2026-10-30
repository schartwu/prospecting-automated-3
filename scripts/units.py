"""Turn the purchasing units seen in documents (dept_units, noted by enrich.py) into departments to collect.

1. promote_units: units of a department whose feed hit the 20-item cap, in Sales' provinces, join the evening
   collection as deptsubId (the department's own feed keeps only its 20 latest items a day). Units added
   45 days ago with no announcement since are switched off again.
2. Codes of agencies the collection does not know (their announcements came from the nationwide feed only,
   e.g. universities: 1410400700 มหาวิทยาลัยรามคำแหง) are tried on the RSS as deptId, then deptsubId, with
   W0 then P0; found ones are added, the rest are tried again after 30 days. The 198 ten-digit codes from v2
   (switched off after failing as deptsubId) are tried first: 1410400700 answered as deptId on 30 Oct 2026.

Runs after the evening pipeline (daily.yml job "units"), when the RSS answers.
"""
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp import provinces  # noqa: E402
from egp.db import DB  # noqa: E402
from egp.feed import fetch  # noqa: E402


def try_code(code):
    """(param, None) when the feed answers with items, ('', None) when empty, (None, error) on failure."""
    error = None
    for param in ("deptId", "deptsubId"):
        for t in ("W0", "P0"):
            r = fetch({param: code, "anounceType": t}, max_seconds=60, retries=2)
            if not r.ok:
                error = r.error
            elif r.items:
                return param, None
    return ("", None) if error is None else (None, error)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=int, default=80, help="unknown agencies' codes to try on the RSS per run")
    args = ap.parse_args()

    db = DB()
    targets = sorted(provinces.targets())
    print("promote:", db.rpc("promote_units", {"p_provinces": targets}), flush=True)

    candidates = db.rpc("unit_candidates", {"p_provinces": targets, "p_limit": args.test}) if args.test else []
    found = []
    with ThreadPoolExecutor(2) as ex:  # the RSS answers HTTP 429 above ~2 requests in flight per IP
        for c, (param, error) in zip(candidates, ex.map(lambda c: try_code(c["code"]), candidates)):
            if param is None:
                print(f"FAILED {c['code']} {error}", flush=True)  # tried again next run
                continue
            if param:
                found.append(c["code"])
                print(f"FOUND {param} {c['code']}", flush=True)
                if db.select("departments", code=f"eq.{c['code']}", select="code"):
                    # A v2 code: keep its name, switch it back on with the parameter that answered.
                    db.update("departments", {"param": param, "active": True}, code=f"eq.{c['code']}")
                else:
                    # enrich.py replaces the placeholder from one of the agency's pages (departments_to_name).
                    db.insert("departments", {"code": c["code"], "param": param, "active": True, "source": "unit",
                                              "name": f"หน่วยงานรหัส {c['code']} (จ.{c['province']})"},
                              returning=False)
            db.rpc("mark_unit", {"p_code": c["code"], "p_status": "added" if param else "not_found"})
    print(f"done: {len(candidates)} codes tried, {len(found)} added", flush=True)


if __name__ == "__main__":
    main()
