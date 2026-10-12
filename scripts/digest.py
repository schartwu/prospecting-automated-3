"""Build the morning digest email from Supabase and send it (or just write a preview).

Daily: new D0 (bid now), B0 (prepare stock), 15 (new reference prices). Mondays also add the week's
new P0 plans and W0 results. Only items first seen since the previous digest are included.
"""
import argparse
import html
import os
import smtplib
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp.db import DB  # noqa: E402

BKK = ZoneInfo("Asia/Bangkok")
ROOT = os.path.join(os.path.dirname(__file__), "..")

SECTIONS = [
    # (types, heading, what Sales/Merchandise should do, weekly_only)
    (["D0"], "🔥 ประกาศเชิญชวน — ยื่นราคาได้แล้ว", "เปิดเอกสาร ตรวจคุณสมบัติ และเตรียมยื่นราคา", False),
    (["B0"], "🛠 ร่าง TOR — เตรียมหาสินค้า (ประกาศจริงตามมาใน ~5 วัน)", "ให้ Merchandise ดู spec และเช็คสต็อก/ราคาทุน", False),
    (["15"], "💰 ประกาศราคากลาง", "รู้งบประมาณของโครงการ", False),
    (["P0"], "📅 แผนจัดซื้อใหม่ (สรุปรายสัปดาห์)", "โอกาสล่วงหน้า วางแผนเข้าพบหน่วยงาน", True),
    (["W0"], "📊 ผลผู้ชนะในหมวดของเรา (สรุปรายสัปดาห์)", "ดูว่าใครชนะ และหน่วยงานไหนซื้อของสำนักงานบ่อย", True),
]
TYPE_LABEL = {"P0": "แผน", "15": "ราคากลาง", "B0": "ร่าง TOR", "D0": "เชิญชวน", "W0": "ผู้ชนะ", "D1": "ยกเลิก"}


def fmt_money(v):
    return f"{float(v):,.0f}" if v not in (None, "") and pd.notna(v) else "-"


def section_html(heading, hint, rows):
    out = [f'<h3 style="margin:24px 0 4px">{html.escape(heading)} ({len(rows)})</h3>',
           f'<div style="color:#666;font-size:13px;margin-bottom:8px">{html.escape(hint)}</div>']
    if not rows:
        out.append('<div style="color:#999;font-size:13px">ไม่มีรายการใหม่</div>')
        return "\n".join(out)
    out.append('<table cellpadding="6" style="border-collapse:collapse;font-size:13px;width:100%">'
               '<tr style="background:#f2f2f2;text-align:left"><th>คะแนน</th><th>โครงการ</th><th>หน่วยงาน</th>'
               '<th>หมวด</th><th>งบ (บาท)</th><th>ประกาศ</th></tr>')
    for r in rows:
        flags = " ".join(TYPE_LABEL.get(s, s) for s in (r.get("stages") or []) if s != r["announce_type"])
        cancelled = ' <b style="color:#c00">[ยกเลิกแล้ว]</b>' if r.get("cancelled") else ""
        out.append(
            "<tr style='border-top:1px solid #eee;vertical-align:top'>"
            f"<td><b>{r['score']}</b></td>"
            f"<td><a href=\"{html.escape(r['link'])}\">{html.escape(r['title'][:220])}</a>{cancelled}"
            f"<div style='color:#888;font-size:12px'>{html.escape(r.get('reason') or '')}"
            f"{' · มีประกาศ: ' + html.escape(flags) if flags else ''}</div></td>"
            f"<td>{html.escape(r.get('dept_name') or '')}</td>"
            f"<td>{html.escape(r.get('category') or '')}</td>"
            f"<td style='text-align:right'>{fmt_money(r.get('budget_thb'))}</td>"
            f"<td>{r.get('pub_date') or ''}</td></tr>")
    out.append("</table>")
    return "\n".join(out)


def build(db: DB, since: datetime, now: datetime, weekly: bool, min_score: int):
    parts, all_rows = [], []
    for types, heading, hint, weekly_only in SECTIONS:
        if weekly_only and not weekly:
            continue
        # Weekly sections look back 7 days regardless of when the last daily digest went out.
        sec_since = min(since, now - timedelta(days=7)) if weekly_only else since
        rows = db.rpc("digest_items", {"p_since": sec_since.isoformat(), "p_types": types,
                                       "p_min_score": min_score})
        if types == ["15"]:
            # Reference prices for projects that also got a D0 are already shown under D0.
            rows = [r for r in rows if "D0" not in (r.get("stages") or [])]
        parts.append(section_html(heading, hint, rows))
        all_rows += [{**r, "section": heading} for r in rows]

    total = len(all_rows)
    head = (f'<div style="font-family:Tahoma,sans-serif;max-width:960px">'
            f'<h2 style="margin:0">e-GP Alert — {now:%d/%m/%Y}</h2>'
            f'<div style="color:#666">ประกาศใหม่ที่เกี่ยวกับ OfficeMate ตั้งแต่ {since.astimezone(BKK):%d/%m %H:%M} น. '
            f'รวม {total} รายการ (คัดกรองโดย AI คะแนน ≥ {min_score})</div>')
    foot = ('<p style="color:#999;font-size:12px;margin-top:24px">คะแนน = ความมั่นใจว่า OfficeMate ขายได้ (0-100) · '
            'ไฟล์ Excel แนบมีรายการทั้งหมด · ระบบ e-GP Alert v3</p></div>')
    return head + "\n".join(parts) + foot, all_rows


def write_xlsx(rows, path):
    cols = {"section": "หมวดอีเมล", "score": "คะแนน", "announce_type": "ประเภท", "title": "ชื่อโครงการ",
            "dept_name": "หน่วยงาน", "category": "หมวดสินค้า", "reason": "เหตุผล AI", "budget_thb": "งบประมาณ",
            "bid_date": "วันยื่นซอง", "pub_date": "วันที่ประกาศ", "method": "วิธีจัดหา",
            "project_no": "เลขโครงการ", "plan_no": "เลขแผน", "cancelled": "ยกเลิกแล้ว", "link": "ลิงก์"}
    df = pd.DataFrame(rows, columns=list(cols)).rename(columns=cols)
    df.to_excel(path, index=False)


def send(subject, html_body, attachment, recipients):
    msg = EmailMessage()
    msg["From"] = os.environ["SENDER_EMAIL"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content("กรุณาเปิดอีเมลนี้ในโหมด HTML")
    msg.add_alternative(html_body, subtype="html")
    with open(attachment, "rb") as f:
        msg.add_attachment(f.read(), maintype="application",
                           subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           filename=os.path.basename(attachment))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(os.environ["SENDER_EMAIL"], os.environ["SENDER_PASSWORD"])
        smtp.send_message(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="actually email it (default: preview files only)")
    ap.add_argument("--to", default="", help="override recipients (comma separated) for tests")
    ap.add_argument("--since-days", type=float, default=0, help="ignore the last digest; look back N days")
    ap.add_argument("--weekly", choices=["auto", "yes", "no"], default="auto")
    ap.add_argument("--min-score", type=int, default=50)
    args = ap.parse_args()

    db = DB()
    now = datetime.now(BKK)
    last = db.select("digests", kind="eq.daily", order="sent_at.desc", limit=1)
    if args.since_days:
        since = now - timedelta(days=args.since_days)
    elif last:
        since = datetime.fromisoformat(last[0]["sent_at"])
    else:
        since = now - timedelta(days=1)
    weekly = now.weekday() == 0 if args.weekly == "auto" else args.weekly == "yes"

    body, rows = build(db, since, now, weekly, args.min_score)
    out = os.path.join(ROOT, "out")
    os.makedirs(out, exist_ok=True)
    xlsx = os.path.join(out, f"eGP_Alert_{now:%Y%m%d}.xlsx")
    write_xlsx(rows, xlsx)
    with open(os.path.join(out, "digest_preview.html"), "w", encoding="utf-8") as f:
        f.write(body)
    print(f"digest since {since:%Y-%m-%d %H:%M} weekly={weekly}: {len(rows)} items -> {out}")

    if args.send:
        recipients = [e.strip() for e in (args.to or os.environ["RECEIVER_EMAIL"]).split(",") if e.strip()]
        n_new = len(rows)
        subject = (f"🚨 e-GP Alert {now:%d/%m/%Y}: {n_new} โครงการใหม่ที่เกี่ยวกับ OfficeMate" if n_new
                   else f"ℹ️ e-GP Alert {now:%d/%m/%Y}: ไม่มีโครงการใหม่")
        send(subject, body, xlsx, recipients)
        if not args.to:  # test sends don't move the "since" window for the real digest
            db.insert("digests", {"kind": "daily", "since": since.isoformat(), "n_items": n_new,
                                  "recipients": ",".join(recipients)}, returning=False)
        print(f"sent to {len(recipients)} recipient(s)")


if __name__ == "__main__":
    main()
