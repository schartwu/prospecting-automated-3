"""Read budget, bid date and (for plans) the expected announcement month from the documents of relevant
D0 / B0 / 15 / P0 announcements.

- D0 / B0 / 15: code patterns on the PDF text first (free). When they find nothing usable, Gemini
  (Flash-Lite first) reads the text; scanned PDFs with no text layer are sent to Gemini as files.
- P0: the plan page is an HTML table of plan lines (plan no, project, budget, expected month). One page
  covers many plan lines, so it is downloaded once and every relevant line on it gets its row.

Every announcement gets a details row, including failures (with the error), so it is not retried forever.
"""
import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp import docs  # noqa: E402
from egp.db import DB  # noqa: E402
from egp.gemini import LITE_FIRST, Gemini, QuotaExhausted  # noqa: E402

TYPES = ["D0", "B0", "15", "P0"]
SCAN_PROMPT_NOTE = "\n(เอกสารแนบเป็นไฟล์ PDF แบบสแกน ให้อ่านจากภาพในไฟล์)"


def ai_extract(gemini, text, pub, pdfs=()):
    """Gemini reads the text, or the PDF files themselves when there is no text layer."""
    def check(ans):
        if ans.get("bid_date"):
            date.fromisoformat(ans["bid_date"])  # raises ValueError on a malformed date
    if text.strip():
        prompt, attachments = docs.EXTRACT_PROMPT.format(text=text[:8000]), ()
    else:
        prompt = docs.EXTRACT_PROMPT.format(text="") + SCAN_PROMPT_NOTE
        attachments = [("application/pdf", b) for b in pdfs[:2]]
    ans, model = gemini.json(prompt, docs.EXTRACT_SCHEMA, LITE_FIRST, validate=check, max_output=1024,
                             attachments=attachments)
    bid = date.fromisoformat(ans["bid_date"]) if ans.get("bid_date") else None
    return ans.get("budget_thb"), (bid if docs.plausible(bid, pub) else None), ans.get("bid_time"), \
        ans.get("item_count"), model


class Enricher:
    def __init__(self, db: DB, gemini: Gemini, use_ai: bool):
        self.db, self.gemini, self.ai_ok = db, gemini, use_ai
        self.stats = defaultdict(int)

    def save(self, detail):
        self.db.upsert("announcement_details", [detail], on_conflict="announcement_id")

    def fix_department_name(self, r, text):
        if r.get("dept_needs_name") and r.get("dept_code"):
            name = docs.parse_department(text)
            if name:
                self.db.rpc("set_department_name", {"p_code": r["dept_code"], "p_name": name})

    def document(self, r):
        """D0 / B0 / 15: one document per announcement."""
        pub = date.fromisoformat(r["pub_date"]) if r.get("pub_date") else None
        detail = {"announcement_id": r["id"], "budget_thb": None, "bid_date": None, "item_count": None,
                  "extracted": {}, "error": None}
        try:
            raw, info, pdfs = docs.fetch_text(r["link"])
            text = docs.normalize(raw)
            budget = docs.parse_budget(text)
            bid, bid_time = docs.parse_bid_date(text)
            source = "regex"
            if not docs.plausible(bid, pub):
                bid, bid_time = None, None
            scanned = len(text) <= 200 and bool(pdfs)
            # Only D0 announces the bid date; drafts (B0) and reference prices (15) need just the budget.
            needs_ai = budget is None or (r["announce_type"] == "D0" and bid is None)
            if needs_ai and self.ai_ok and (len(text) > 200 or scanned):
                try:
                    a_budget, a_bid, a_time, items, model = ai_extract(self.gemini, text, pub, pdfs if scanned else ())
                    budget, bid = budget or a_budget, bid or a_bid
                    bid_time = bid_time or a_time
                    detail["item_count"] = items
                    source = f"ai:{model}" + (":scan" if scanned else "")
                except QuotaExhausted:
                    self.ai_ok = False
                    print("::warning::Gemini budget used up; remaining documents use code patterns only")
                except RuntimeError as e:
                    detail["error"] = f"ai: {str(e)[:200]}"
            self.fix_department_name(r, text)
            detail.update(budget_thb=budget, bid_date=bid.isoformat() if bid else None,
                          extracted={**info, "bid_time": bid_time, "source": source, "text_chars": len(text),
                                     "scanned": scanned})
            if budget is None and bid is None:
                self.stats["missing"] += 1
                detail["error"] = detail["error"] or (
                    "scanned document, not read" if scanned
                    else "no text in document" if len(text) <= 200 else "fields not found")
            else:
                self.stats["ai" if source.startswith("ai") else "regex"] += 1
        except Exception as e:  # recorded on the row so the digest still shows the announcement
            self.stats["error"] += 1
            detail["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        self.save(detail)

    def plan_page(self, link, rows):
        """P0: one plan page, many plan lines."""
        try:
            raw, info, _ = docs.fetch_text(link)
            lines = docs.parse_plan_lines(raw)
            self.fix_department_name(rows[0], docs.normalize(raw))  # all lines on a page share a department
        except Exception as e:
            lines, info, err = {}, {}, f"{type(e).__name__}: {str(e)[:300]}"
        else:
            err = None
        for r in rows:
            line = lines.get(r.get("plan_no") or "")
            self.save({"announcement_id": r["id"], "budget_thb": line["budget_thb"] if line else None,
                       "bid_date": None, "item_count": None,
                       "extracted": {**info, "source": "plan-page",
                                     "expected_month": line["expected_month"] if line else None},
                       "error": err or (None if line else "plan line not found on the page")})
            self.stats["plan" if line else "missing"] += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--min-score", type=int, default=50)
    ap.add_argument("--no-ai", action="store_true")
    args = ap.parse_args()

    db = DB()
    gemini = Gemini(os.environ.get("GEMINI_API_KEY", ""),
                    lambda model, budget: db.rpc("ai_take", {"p_model": model, "p_budget": budget}))
    rows = db.rpc("announcements_to_enrich", {"p_types": TYPES, "p_min_score": args.min_score,
                                              "p_limit": args.limit})
    plans = defaultdict(list)
    for r in rows:
        if r["announce_type"] == "P0":
            plans[r["link"]].append(r)
    others = [r for r in rows if r["announce_type"] != "P0"]
    print(f"{len(others)} documents and {len(plans)} plan pages ({len(rows) - len(others)} plan lines) to read",
          flush=True)

    e = Enricher(db, gemini, not args.no_ai)
    for r in others:
        e.document(r)
        time.sleep(1)  # be gentle with the e-GP document server
    for link, plan_rows in plans.items():
        e.plan_page(link, plan_rows)
        time.sleep(1)
    print("DONE", dict(e.stats))


if __name__ == "__main__":
    main()
