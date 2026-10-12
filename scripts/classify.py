"""Classify every not-yet-classified announcement title with Gemini and store the verdicts in Supabase.

Only announcement types that lead to a sale or tell us who buys what are classified. Cancellations and
changes (D1, W1, D2, W2) are looked up by project number when the digest is built.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp.classify import DEFAULT_MODEL, classify_titles, list_models  # noqa: E402
from egp.db import DB  # noqa: E402

TYPES = ["P0", "15", "B0", "D0", "W0"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=40, help="titles per Gemini request")
    ap.add_argument("--max-titles", type=int, default=5000)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--list-models", action="store_true")
    args = ap.parse_args()

    key = os.environ["GEMINI_API_KEY"]
    if args.list_models:
        print("\n".join(list_models(key)))
        return

    db = DB()
    done_titles = saved = relevant = 0
    seen = set()
    while done_titles < args.max_titles:
        rows = db.rpc("unclassified_titles", {"p_types": TYPES, "p_limit": args.batch})
        if not rows or all(r["title"] in seen for r in rows):
            break  # nothing left, or the same titles came back unsaved: stop instead of looping
        seen.update(r["title"] for r in rows)
        verdicts = classify_titles(rows, key, args.model)
        saved += db.rpc("save_title_classifications", {"p_types": TYPES, "p_rows": verdicts})
        done_titles += len(rows)
        relevant += sum(v["relevant"] for v in verdicts)
        print(f"  {done_titles} titles classified ({relevant} relevant), {saved} announcements saved", flush=True)
    print(f"DONE model={args.model} titles={done_titles} relevant={relevant} announcements={saved}")


if __name__ == "__main__":
    main()
