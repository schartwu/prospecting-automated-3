"""Read budget and bid date from the documents of relevant D0 / B0 / 15 announcements.

Code patterns first (free); Gemini Flash-Lite only when the patterns find nothing usable. Every
announcement gets a details row, including failures (with the error), so it is not retried forever.
"""
import argparse
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp import docs  # noqa: E402
from egp.db import DB  # noqa: E402
from egp.gemini import LITE_FIRST, Gemini, QuotaExhausted  # noqa: E402

TYPES = ["D0", "B0", "15"]


def ai_extract(gemini, text, pub):
    def check(ans):
        if ans.get("bid_date"):
            date.fromisoformat(ans["bid_date"])  # raises ValueError on a malformed date
    ans, model = gemini.json(docs.EXTRACT_PROMPT.format(text=text[:8000]), docs.EXTRACT_SCHEMA,
                             LITE_FIRST, validate=check, max_output=1024)
    bid = date.fromisoformat(ans["bid_date"]) if ans.get("bid_date") else None
    return ans.get("budget_thb"), (bid if docs.plausible(bid, pub) else None), ans.get("bid_time"), \
        ans.get("item_count"), model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--min-score", type=int, default=50)
    ap.add_argument("--no-ai", action="store_true")
    args = ap.parse_args()

    db = DB()
    gemini = Gemini(os.environ.get("GEMINI_API_KEY", ""),
                    lambda model, budget: db.rpc("ai_take", {"p_model": model, "p_budget": budget}))
    ai_ok = not args.no_ai
    rows = db.rpc("announcements_to_enrich", {"p_types": TYPES, "p_min_score": args.min_score,
                                              "p_limit": args.limit})
    print(f"{len(rows)} documents to read", flush=True)

    stats = {"regex": 0, "ai": 0, "missing": 0, "error": 0}
    for r in rows:
        pub = date.fromisoformat(r["pub_date"]) if r.get("pub_date") else None
        detail = {"announcement_id": r["id"], "budget_thb": None, "bid_date": None, "item_count": None,
                  "extracted": {}, "error": None}
        try:
            raw, info = docs.fetch_text(r["link"])
            text = docs.normalize(raw)
            budget = docs.parse_budget(text)
            bid, bid_time = docs.parse_bid_date(text)
            source = "regex"
            if not docs.plausible(bid, pub):
                bid, bid_time = None, None
            # Only D0 announces the bid date; drafts (B0) and reference prices (15) need just the budget.
            needs_ai = budget is None or (r["announce_type"] == "D0" and bid is None)
            if needs_ai and ai_ok and len(text) > 200:
                try:
                    a_budget, a_bid, a_time, items, model = ai_extract(gemini, text, pub)
                    budget, bid = budget or a_budget, bid or a_bid
                    bid_time = bid_time or a_time
                    detail["item_count"] = items
                    source = f"ai:{model}"
                except QuotaExhausted:
                    ai_ok = False
                    print("::warning::Gemini budget used up; remaining documents use code patterns only")
                except RuntimeError as e:
                    detail["error"] = f"ai: {str(e)[:200]}"
            detail.update(budget_thb=budget, bid_date=bid.isoformat() if bid else None,
                          extracted={**info, "bid_time": bid_time, "source": source, "text_chars": len(text)})
            if budget is None and bid is None:
                stats["missing"] += 1
                detail["error"] = detail["error"] or ("no text in document" if len(text) <= 200
                                                      else "fields not found")
            else:
                stats["ai" if source.startswith("ai") else "regex"] += 1
        except Exception as e:  # recorded on the row so the digest still shows the announcement
            stats["error"] += 1
            detail["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        db.upsert("announcement_details", [detail], on_conflict="announcement_id")
        time.sleep(1)  # be gentle with the e-GP document server
    print("DONE", stats)


if __name__ == "__main__":
    main()
