"""Read-only probe: does the RSS feed answer for a department code that is not 4 digits?

Prints what the feed returns for each (param, code, type); touches no database and writes no file.
Example: python scripts/probe_dept.py 3100001 310000110000330 --find 69109124627
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp.feed import fetch  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--params", default="deptId,deptsubId")
    ap.add_argument("--types", default="D0,15,B0,W0,P0")
    ap.add_argument("--find", default="", help="a project number to look for in the items")
    args = ap.parse_args()

    for code in args.codes:
        for param in args.params.split(","):
            for t in args.types.split(","):
                r = fetch({param: code, "anounceType": t}, max_seconds=60, retries=1)
                if not r.ok:
                    print(f"{param}={code} {t}: FAILED {r.error}", flush=True)
                    continue
                hit = [i for i in r.items if args.find and args.find in i.get("description", "")]
                dates = sorted(i.get("pubDate", "") for i in r.items)
                print(f"{param}={code} {t}: {len(r.items)} items"
                      f"{f' ({dates[0]} .. {dates[-1]})' if dates else ''}"
                      f" title={r.channel.get('title', '')!r}{'  << FOUND ' + args.find if hit else ''}", flush=True)
                for i in r.items[:3]:
                    print(f"    {i.get('pubDate', '')} | {i.get('description', '')[:60]} | {i.get('title', '')[:70]}")
                time.sleep(1)


if __name__ == "__main__":
    main()
