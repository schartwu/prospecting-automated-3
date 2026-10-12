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
TYPE_LABEL = {
    "P0": "แผนจัดซื้อ",
    "15": "ราคากลาง",
    "B0": "ร่าง TOR",
    "D0": "ประกาศเชิญชวน",
    "W0": "ประกาศผู้ชนะ",
    "D1": "ยกเลิกประกาศเชิญชวน",
    "W1": "ยกเลิกประกาศผู้ชนะ",
    "D2": "แก้ไขประกาศเชิญชวน",
    "W2": "แก้ไขประกาศผู้ชนะ",
}
TYPE_MEANING = {
    "P0": "แผนจัดซื้อจัดจ้างประจำปี — รู้ล่วงหน้าหลายเดือน ใช้วางแผนเข้าพบหน่วยงาน",
    "15": "ประกาศราคากลาง — บอกงบประมาณ ส่วนใหญ่ออกวันเดียวกับประกาศเชิญชวน",
    "B0": "ร่าง TOR / ร่างเอกสารประกวดราคา — ประกาศเชิญชวนจริงตามมาราว 5 วัน ให้เตรียมสินค้า",
    "D0": "ประกาศเชิญชวน — เปิดให้ยื่นราคาแล้ว ดูวันยื่นซอง",
    "W0": "ประกาศผู้ชนะ — ใครชนะ ใช้ดูคู่แข่งและหน่วยงานที่ซื้อของสำนักงานบ่อย",
    "D1": "ยกเลิกประกาศเชิญชวน",
    "W1": "ยกเลิกประกาศผู้ชนะ",
    "D2": "แก้ไข/เปลี่ยนแปลงประกาศเชิญชวน",
    "W2": "แก้ไข/เปลี่ยนแปลงประกาศผู้ชนะ",
}
SCORE_BANDS = [
    ("90-100", "สินค้าหลัก: วัสดุสำนักงาน กระดาษ หมึกพิมพ์ เครื่องเขียน"),
    ("75-89", "ซื้อ/เช่า คอมพิวเตอร์และไอที เฟอร์นิเจอร์ เครื่องใช้สำนักงาน"),
    ("60-74", "โครงการผสม มีสินค้าของเราเป็นส่วนสำคัญ"),
    ("40-59", "ก้ำกึ่ง: เครื่องใช้ไฟฟ้า เครื่องมือช่าง อุปกรณ์ความปลอดภัย"),
    ("0-39", "ไม่ใช่สินค้าที่ OfficeMate ขาย (ไม่แสดงในอีเมล)"),
]


def fmt_money(v):
    return f"{float(v):,.0f}" if v not in (None, "") and pd.notna(v) else "-"


def days_left(r, today):
    return (datetime.fromisoformat(r["bid_date"]).date() - today).days if r.get("bid_date") else None


def bid_cell(r, today):
    if not r.get("bid_date"):
        return "-"
    left = days_left(r, today)
    when = datetime.fromisoformat(r["bid_date"]).strftime("%d/%m")
    time_ = f" {r['bid_time']}" if r.get("bid_time") else ""
    color = "#c00" if left <= 3 else "#333"
    note = "ผ่านไปแล้ว" if left < 0 else ("วันนี้" if left == 0 else f"อีก {left} วัน")
    return f"{when}{time_}<div style='color:{color};font-size:12px'><b>{note}</b></div>"


EMAIL_ROW_LIMIT = 30  # per section; the attached Excel always has every row


def section_html(heading, hint, rows, today):
    out = [f'<h3 style="margin:24px 0 4px">{html.escape(heading)} ({len(rows)})</h3>',
           f'<div style="color:#666;font-size:13px;margin-bottom:8px">{html.escape(hint)}</div>']
    shown, rows = rows, rows[:EMAIL_ROW_LIMIT]
    if not rows:
        out.append('<div style="color:#999;font-size:13px">ไม่มีรายการใหม่</div>')
        return "\n".join(out)
    out.append('<table cellpadding="6" style="border-collapse:collapse;font-size:13px;width:100%">'
               '<tr style="background:#f2f2f2;text-align:left"><th>คะแนน</th><th>โครงการ</th><th>หน่วยงาน</th>'
               '<th>งบ (บาท)</th><th>วันยื่นซอง</th><th>วันที่ประกาศ</th></tr>')
    for r in rows:
        flags = ", ".join(TYPE_LABEL.get(s, s) for s in (r.get("stages") or []) if s != r["announce_type"])
        badges = ""
        if r.get("cancelled"):
            badges += ' <b style="color:#c00">[ยกเลิกแล้ว]</b>'
        if r.get("amended"):
            badges += ' <b style="color:#d97706">[มีการแก้ไขประกาศ]</b>'
        sub = " · ".join(filter(None, [r.get("category"), r.get("reason"),
                                       f"มีประกาศ: {flags}" if flags else None]))
        out.append(
            "<tr style='border-top:1px solid #eee;vertical-align:top'>"
            f"<td><b>{r['score']}</b></td>"
            f"<td><a href=\"{html.escape(r['link'])}\">{html.escape(r['title'][:220])}</a>{badges}"
            f"<div style='color:#888;font-size:12px'>{html.escape(sub)}</div></td>"
            f"<td>{html.escape(r.get('dept_name') or '')}</td>"
            f"<td style='text-align:right'>{fmt_money(r.get('budget_thb'))}</td>"
            f"<td>{bid_cell(r, today)}</td>"
            f"<td>{r.get('pub_date') or ''}</td></tr>")
    out.append("</table>")
    if len(shown) > len(rows):
        out.append(f'<div style="color:#666;font-size:12px">แสดง {len(rows)} อันดับแรก '
                   f'จาก {len(shown)} รายการ · ดูทั้งหมดในไฟล์ Excel แนบ</div>')
    return "\n".join(out)


def build(db: DB, since: datetime, now: datetime, weekly: bool, min_score: int):
    today = now.date()
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
        if types == ["D0"]:
            # Bids closing soonest first; unknown or past deadlines after them.
            def urgency(r):
                left = days_left(r, today)
                return (left is None or left < 0, left if left is not None else 999, -r["score"])
            rows.sort(key=urgency)
        parts.append(section_html(heading, hint, rows, today))
        all_rows += [{**r, "section": heading, "days_left": days_left(r, today)} for r in rows]

    total = len(all_rows)
    head = (f'<div style="font-family:Tahoma,sans-serif;max-width:980px">'
            f'<h2 style="margin:0">e-GP Alert — {now:%d/%m/%Y}</h2>'
            f'<div style="color:#666">ประกาศใหม่ที่เกี่ยวกับ OfficeMate ตั้งแต่ {since.astimezone(BKK):%d/%m %H:%M} น. '
            f'รวม {total} รายการ (คะแนน ≥ {min_score})</div>')
    bands = " · ".join(f"{b} {d}" for b, d in SCORE_BANDS[:4])
    foot = (f'<p style="color:#999;font-size:12px;margin-top:24px">คะแนน = ความตรงกับสินค้า OfficeMate: '
            f'{html.escape(bands)}<br>งบ = ราคากลางจากเอกสารประกาศ · ไฟล์ Excel แนบมีรายการทั้งหมดและแท็บคำอธิบาย '
            '· ระบบ e-GP Alert v3</p></div>')
    return head + "\n".join(parts) + foot, all_rows


def write_xlsx(rows, path):
    cols = {"section": "หมวดอีเมล", "score": "คะแนน", "type_label": "ประเภทประกาศ", "title": "ชื่อโครงการ",
            "dept_name": "หน่วยงาน", "category": "หมวดสินค้า", "reason": "เหตุผล", "budget_thb": "งบประมาณ (บาท)",
            "bid_date": "วันยื่นซอง", "bid_time": "เวลายื่น", "days_left": "เหลือ (วัน)",
            "pub_date": "วันที่ประกาศ", "method": "วิธีจัดหา", "project_no": "เลขโครงการ", "plan_no": "เลขแผน",
            "cancelled": "ยกเลิกแล้ว", "amended": "มีการแก้ไขประกาศ", "link": "ลิงก์"}
    data = [{**r, "type_label": f"{TYPE_LABEL.get(r['announce_type'], r['announce_type'])} ({r['announce_type']})"}
            for r in rows]
    df = pd.DataFrame(data, columns=list(cols)).rename(columns=cols)

    columns_help = [
        ("งบประมาณ (บาท)", "ราคากลางที่อ่านจากเอกสารประกาศ (ว่าง = เอกสารเปิดไม่ได้หรือไม่ระบุ)"),
        ("วันยื่นซอง / เวลายื่น", "วันและช่วงเวลาเสนอราคาในระบบ e-GP (มีเฉพาะประกาศเชิญชวน)"),
        ("เหลือ (วัน)", "จำนวนวันจากวันที่ส่งอีเมลถึงวันยื่นซอง"),
        ("ยกเลิกแล้ว", "โครงการเดียวกันมีประกาศยกเลิกประกาศเชิญชวน (D1) ตามมา — ไม่ต้องตามต่อ"),
        ("มีการแก้ไขประกาศ", "โครงการเดียวกันมีประกาศแก้ไขประกาศเชิญชวน (D2) — เปิดดูรายละเอียดใหม่"),
        ("เลขโครงการ", "เลข 11 หลักของ e-GP ใช้ค้นหาโครงการในเว็บ e-GP"),
    ]
    legend = ([{"หัวข้อ": "ประเภทประกาศ", "ค่า": f"{TYPE_LABEL[k]} ({k})", "ความหมาย": v}
               for k, v in TYPE_MEANING.items()]
              + [{"หัวข้อ": "คะแนน", "ค่า": b, "ความหมาย": d} for b, d in SCORE_BANDS]
              + [{"หัวข้อ": "คอลัมน์", "ค่า": k, "ความหมาย": v} for k, v in columns_help])
    with pd.ExcelWriter(path) as xw:
        df.to_excel(xw, sheet_name="รายการ", index=False)
        pd.DataFrame(legend).to_excel(xw, sheet_name="คำอธิบาย", index=False)
        style_sheet(xw.sheets["รายการ"], number_cols={"งบประมาณ (บาท)"},
                    wrap_cols={"ชื่อโครงการ": 60, "เหตุผล": 35, "หน่วยงาน": 28,
                               "หมวดอีเมล": 24, "หมวดสินค้า": 22, "วิธีจัดหา": 24})
        style_sheet(xw.sheets["คำอธิบาย"], wrap_cols={"ความหมาย": 80})


# Column widths in Excel character units. Long text columns (wrap_cols: name -> width) get a fixed
# width and wrap instead of stretching the sheet; the rest are sized to their content within bounds.
MIN_WIDTH, MAX_WIDTH = 8, 45


def style_sheet(ws, number_cols=frozenset(), wrap_cols=None):
    wrap_cols = wrap_cols or {}
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    header = {cell.value: cell.column for cell in ws[1]}
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="F2F2F2")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for name, col in header.items():
        letter = get_column_letter(col)
        cells = [c for (c,) in ws.iter_rows(min_row=2, min_col=col, max_col=col)]
        if name in number_cols:
            for c in cells:
                c.number_format = "#,##0"  # 4,992,128 — no decimals
        if name in wrap_cols:
            width = wrap_cols[name]
            for c in cells:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        else:
            longest = max([len(str(name))] + [len(f"{c.value:,.0f}") if name in number_cols and isinstance(
                c.value, (int, float)) else len(str(c.value)) for c in cells if c.value is not None])
            width = min(MAX_WIDTH, max(MIN_WIDTH, longest + 2))
            for c in cells:
                c.alignment = Alignment(vertical="top")
        ws.column_dimensions[letter].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


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
        # DIGEST_RECIPIENTS (a repository variable) overrides the team list, e.g. for a trial period.
        to = args.to or os.environ.get("DIGEST_RECIPIENTS") or os.environ["RECEIVER_EMAIL"]
        recipients = [e.strip() for e in to.split(",") if e.strip()]
        n_new = len(rows)
        weekly_headings = {h for _, h, _, weekly_only in SECTIONS if weekly_only}
        n_daily = sum(r["section"] not in weekly_headings for r in rows)
        n_bid = sum(r["announce_type"] == "D0" for r in rows)
        n_prep = sum(r["announce_type"] == "B0" for r in rows)
        weekly_note = f" + สรุปรายสัปดาห์ {n_new - n_daily} รายการ" if n_new > n_daily else ""
        subject = (f"🚨 e-GP Alert {now:%d/%m/%Y}: ยื่นราคาได้ {n_bid} · เตรียมของ {n_prep} · "
                   f"ใหม่รวม {n_daily} โครงการ{weekly_note}" if n_daily
                   else f"ℹ️ e-GP Alert {now:%d/%m/%Y}: ไม่มีโครงการใหม่{weekly_note}")
        send(subject, body, xlsx, recipients)
        if not args.to:  # test sends don't move the "since" window for the real digest
            db.insert("digests", {"kind": "daily", "since": since.isoformat(), "n_items": n_new,
                                  "recipients": ",".join(recipients)}, returning=False)
        print(f"sent to {len(recipients)} recipient(s)")


if __name__ == "__main__":
    main()
