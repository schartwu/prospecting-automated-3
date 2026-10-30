"""After the evening collection is loaded: email the admin when e-GP's RSS mostly failed.

On 22-24 Oct 2026 the RSS server did not answer in the evening (100%, 100% and 62% of requests failed),
yet the workflow still ended green because each failure is logged rather than raised. This step looks at
the collect_runs rows of this evening's daily run and writes to ADMIN_ALERT_EMAIL when
  - no run was loaded at all, or fewer than SHARDS (a collecting machine produced nothing), or
  - more than FAIL_LIMIT of the requests failed, or
  - the database passed DB_LIMIT_MB (the Free plan stops writes at 500 MB; local governments were added on
    29 Oct 2026 and roughly doubled the daily rows).
A normal evening fails 1-2%. The pipeline goes on either way; the next evening fetches back about a week.
"""
import os
import smtplib
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp.db import DB  # noqa: E402

FAIL_LIMIT = 0.5
SHARDS = 8            # daily.yml collects on eight machines
LOOK_BACK_HOURS = 8   # the run starts at 18:00 and loads by about 21:00
DB_LIMIT_MB = 350


def problems(runs, db_mb=0):
    requests = sum(r["n_requests"] or 0 for r in runs)
    failed = sum(r["n_failed"] or 0 for r in runs)
    found = []
    if not runs:
        found.append("ไม่มีผลการดึงข้อมูลของรอบนี้เลย (ขั้น collect อาจล้มทั้งหมด)")
    elif len(runs) < SHARDS:
        found.append(f"ได้ผลจาก {len(runs)} จาก {SHARDS} เครื่อง (บางเครื่องไม่ได้ส่งผล)")
    if requests and failed / requests > FAIL_LIMIT:
        found.append(f"ดึงไม่สำเร็จ {failed:,} จาก {requests:,} ครั้ง ({failed / requests:.0%}) "
                     "ปกติไม่เกิน 2% · เซิร์ฟเวอร์ RSS ของ e-GP อาจไม่ตอบช่วงนี้")
    if db_mb > DB_LIMIT_MB:
        found.append(f"ฐานข้อมูลใช้พื้นที่ {db_mb:,} MB แล้ว (Free plan เต็มที่ 500 MB) "
                     "ควรลดระยะเก็บข้อมูลใน cleanup_old_data()")
    return found, requests, failed


def main():
    db = DB()
    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    since = (now - timedelta(hours=LOOK_BACK_HOURS)).isoformat()
    runs = db.select("collect_runs", select="n_requests,n_ok,n_failed,n_items,n_new_items",
                     mode="eq.daily", started_at=f"gte.{since}")
    db_mb = db.rpc("db_size_mb", {})
    found, requests, failed = problems(runs, db_mb)
    items = sum(r["n_items"] or 0 for r in runs)
    print(f"daily collection: {len(runs)} run(s), {requests} requests, {failed} failed, {items} items, "
          f"database {db_mb} MB")
    if not found:
        return
    for p in found:
        print(f"::warning::{p}")
    to = [e.strip() for e in (os.environ.get("ADMIN_ALERT_EMAIL") or "").split(",") if e.strip()]
    if not to:
        print("::warning::ADMIN_ALERT_EMAIL is empty; no alert email sent")
        return
    msg = EmailMessage()
    msg["From"] = os.environ["SENDER_EMAIL"]
    msg["To"] = ", ".join(to)
    msg["Subject"] = f"⚠️ e-GP Alert {now:%d/%m/%Y}: ดึงข้อมูลรอบเย็นมีปัญหา"
    msg.set_content(
        "รอบดึงข้อมูลเย็นนี้ (Daily pipeline) มีปัญหา:\n\n"
        + "\n".join(f"- {p}" for p in found)
        + f"\n\nได้รายการ {items:,} รายการ (ก่อนเพิ่มหน่วยงานท้องถิ่นวันที่ 29 ต.ค. 69 ปกติราว 3,000–4,000)\n\n"
          "ผลที่ตามมา: อีเมลเช้าพรุ่งนี้อาจมีรายการน้อยกว่าปกติ\n"
          "ไม่ต้องทำอะไรถ้าเป็นแค่คืนเดียว: RSS ย้อนหลังได้ราว 1 สัปดาห์ รอบเย็นถัดไปจะเก็บย้อนให้เอง\n"
          "ถ้าเกิดหลายคืนติดกัน: ดู log ของ job collect ใน GitHub Actions → Daily pipeline "
          "และลองเปิด http://process3.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml?anounceType=D0\n")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(os.environ["SENDER_EMAIL"], os.environ["SENDER_PASSWORD"])
        smtp.send_message(msg)
    print(f"alert sent to {len(to)} recipient(s)")


if __name__ == "__main__":
    main()
