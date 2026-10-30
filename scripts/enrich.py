"""Read budget, bid date and (for plans) the expected announcement month from the documents of relevant
D0 / B0 / 15 / P0 announcements, the winner and winning price from W0, and the province from all of them.

- D0 / B0 / 15: code patterns on the PDF text first (free). When they find nothing usable, Gemini
  (Flash-Lite first) reads the text; scanned PDFs with no text layer are sent to Gemini as files.
- P0: the plan page is an HTML table of plan lines (plan no, project, budget, expected month). One page
  covers many plan lines, so it is downloaded once and every relevant line on it gets its row.
- W0: most are an HTML page the code reads ("ได้แก่ <winner> โดยเสนอราคา ... บาท"); e-bidding results are
  a PDF whose text comes out jumbled, so Gemini (Flash-Lite first) reads those.
- Province: the feed names only the top-level department, so it comes from the title and the document
  (egp/provinces.py). Central offices usually name none; the digest keeps those.

Every announcement gets a details row, including failures (with the error), so it is not retried forever.
"""
import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import date

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp import docs, provinces  # noqa: E402
from egp.db import DB  # noqa: E402
from egp.gemini import FLASH_FIRST, LITE_FIRST, Gemini, QuotaExhausted  # noqa: E402

TYPES = ["D0", "B0", "15", "P0", "W0", "W2"]  # W2: winners changed, read like a W0
SCAN_MODELS = [m for m in FLASH_FIRST if "lite" not in m]
def transient(e: Exception) -> bool:
    """Server-side hiccups (HTTP 5xx such as 511, timeouts): leave the row unsaved so the next run retries."""
    if isinstance(e, (requests.ConnectionError, requests.Timeout)):
        return True
    return isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code >= 500


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
    # Reading numbers off a scanned image is where Flash-Lite slipped (dropped digits, a line item instead
    # of the total; 2026-10-15 check against code-read D0 budgets), so scans use only the Flash models and
    # wait for the next run when those are busy. Plain text is easy and goes to Flash-Lite first.
    models = SCAN_MODELS if attachments else LITE_FIRST
    ans, model = gemini.json(prompt, docs.EXTRACT_SCHEMA, models, validate=check, max_output=1024,
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
            if r["announce_type"] in ("W0", "W2"):
                return self.winner(r, text, info, detail)
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
                    if scanned:
                        self.stats["retry later"] += 1  # Flash models used up today; read it next run
                        return
                    self.ai_ok = False
                    print("::warning::Gemini budget used up; remaining documents use code patterns only")
                except RuntimeError as e:
                    if scanned:
                        self.stats["retry later"] += 1
                        return
                    detail["error"] = f"ai: {str(e)[:200]}"
            self.fix_department_name(r, text)
            detail.update(budget_thb=budget, bid_date=bid.isoformat() if bid else None,
                          extracted={**info, "bid_time": bid_time, "source": source, "text_chars": len(text),
                                     "scanned": scanned, "province": provinces.from_dept(r.get("dept_code")) or provinces.detect(r["title"], text)})
            if budget is None and bid is None:
                self.stats["missing"] += 1
                detail["error"] = detail["error"] or (
                    "scanned document, not read" if scanned
                    else "no text in document" if len(text) <= 200 else "fields not found")
            else:
                self.stats["ai" if source.startswith("ai") else "regex"] += 1
        except Exception as e:  # recorded on the row so the digest still shows the announcement
            if transient(e):
                self.stats["retry later"] += 1
                return
            self.stats["error"] += 1
            detail["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        self.save(detail)

    def winner(self, r, text, info, detail):
        """W0 / W2: who won and at what price."""
        winners, price = docs.parse_winners(text)
        source = "regex"
        if not winners and len(text) > 200 and self.ai_ok:
            try:
                ans, model = self.gemini.json(docs.WINNER_PROMPT.format(text=text[:8000]), docs.WINNER_SCHEMA,
                                              LITE_FIRST, max_output=1024)
                winners = [w.strip() for w in ans["winners"] if w and w.strip()]
                price, source = ans["price_thb"], f"ai:{model}"
            except QuotaExhausted:
                self.ai_ok = False
                print("::warning::Gemini budget used up; remaining documents use code patterns only")
            except RuntimeError as e:
                detail["error"] = f"ai: {str(e)[:200]}"
        detail["extracted"] = {**info, "source": source, "text_chars": len(text), "winners": winners,
                               "winner_price": price, "province": provinces.from_dept(r.get("dept_code")) or provinces.detect(r["title"], text)}
        if winners:
            self.stats["winner " + source.split(":")[0]] += 1
        else:
            self.stats["missing"] += 1
            detail["error"] = detail["error"] or ("no text in document" if len(text) <= 200 else "winner not found")
        self.save(detail)

    def add_province(self, link, rows):
        """Rows read before provinces were added: fetch the document again and add only the province."""
        try:
            page = docs.normalize(docs.fetch_text(link)[0])
        except Exception as e:  # the title may still name the province
            print(f"  {link[:80]}: {type(e).__name__}")
            page = ""
        for r in rows:
            self.db.update("announcement_details",
                           {"extracted": {**(r["extracted"] or {}), "province": provinces.from_dept(r.get("dept_code")) or provinces.detect(r["title"], page)}},
                           announcement_id=f"eq.{r['id']}")
            self.stats["province added"] += 1

    def plan_page(self, link, rows):
        """P0: one plan page, many plan lines."""
        try:
            raw, info, _ = docs.fetch_text(link)
            lines = docs.parse_plan_lines(raw)
            page = docs.normalize(raw)
            self.fix_department_name(rows[0], page)  # all lines on a page share a department
        except Exception as e:
            if transient(e):
                self.stats["retry later"] += len(rows)
                return
            lines, info, page, err = {}, {}, "", f"{type(e).__name__}: {str(e)[:300]}"
        else:
            err = None
        for r in rows:
            line = lines.get(r.get("plan_no") or "")
            self.save({"announcement_id": r["id"], "budget_thb": line["budget_thb"] if line else None,
                       "bid_date": None, "item_count": None,
                       "extracted": {**info, "source": "plan-page",
                                     "expected_month": line["expected_month"] if line else None,
                                     "province": provinces.from_dept(r.get("dept_code")) or provinces.detect(r["title"], page)},
                       "error": err or (None if line else "plan line not found on the page")})
            self.stats["plan" if line else "missing"] += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=800)  # ~830 relevant W0 a day since local governments were added
    ap.add_argument("--min-score", type=int, default=50)
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--add-province-days", type=int, default=0,
                    help="instead: add the province to documents read in the last N days without one")
    args = ap.parse_args()

    db = DB()
    gemini = Gemini(os.environ.get("GEMINI_API_KEY", ""),
                    lambda model, budget: db.rpc("ai_take", {"p_model": model, "p_budget": budget}))
    if args.add_province_days:
        e = Enricher(db, gemini, False)
        pages = defaultdict(list)
        for r in db.rpc("details_without_province", {"p_days": args.add_province_days, "p_limit": args.limit}):
            pages[r["link"]].append(r)
        print(f"{len(pages)} documents to read for the province", flush=True)
        for link, page_rows in pages.items():
            e.add_province(link, page_rows)
            time.sleep(1)
        print("DONE", dict(e.stats))
        return

    rows = db.rpc("announcements_to_enrich", {"p_types": TYPES, "p_min_score": args.min_score,
                                              "p_limit": args.limit})
    plans = defaultdict(list)
    for r in rows:
        if r["announce_type"] == "P0":
            plans[r["link"]].append(r)
    others = [r for r in rows if r["announce_type"] != "P0"]  # W0 come last (see the SQL order)
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
