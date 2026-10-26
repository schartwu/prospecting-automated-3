"""Build the morning digest email from Supabase and send it (or just write a preview).

Daily: new D0 (bid now), B0 (prepare stock), 15 (new reference prices). Mondays also add the week's
new P0 plans and W0 results. Only items first seen since the previous digest are included.

Only Sales' provinces go in the email (TARGET_PROVINCES, a repository variable, else DEFAULT_PROVINCES).
Announcements whose province could not be read (mostly central offices in Bangkok/Nonthaburi) stay in;
those clearly in another province go to a separate Excel tab instead of being dropped.
"""
import argparse
import html
import os
import re
import smtplib
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from egp import provinces  # noqa: E402
from egp.db import DB  # noqa: E402

BKK = ZoneInfo("Asia/Bangkok")
ROOT = os.path.join(os.path.dirname(__file__), "..")
# Bangkok, its surrounding provinces and the east: the area the Sales team covers (2026-10-19).
DEFAULT_PROVINCES = ("กรุงเทพมหานคร, นนทบุรี, ปทุมธานี, สมุทรปราการ, สมุทรสาคร, สมุทรสงคราม, นครปฐม, "
                     "พระนครศรีอยุธยา, สระบุรี, นครนายก, ปราจีนบุรี, ฉะเชิงเทรา, ชลบุรี, ระยอง, จันทบุรี")

SECTIONS = [
    # (types, heading, what Sales/Merchandise should do, when, min score or None for the default)
    # when: "daily" = every digest, "weekly" = Mondays only (last 7 days), "not_weekly" = Tue-Fri only.
    (["D0"], "🔥 ประกาศเชิญชวน — ยื่นราคาได้แล้ว", "เปิดเอกสาร ตรวจคุณสมบัติ และเตรียมยื่นราคา", "daily", None),
    (["B0"], "🛠 ร่าง TOR — เตรียมหาสินค้า (ประกาศจริงตามมาใน ~5 วัน)", "ให้ Merchandise ดู spec และเช็คสต็อก/ราคาทุน",
     "daily", None),
    (["15"], "💰 ประกาศราคากลาง", "รู้งบประมาณของโครงการ", "daily", None),
    # Plans are the earliest signal for Merchandise, so the strongest ones go out daily; Monday has them all.
    (["P0"], "📅 แผนจัดซื้อใหม่ (คะแนน 75 ขึ้นไป)", "รู้ล่วงหน้าหลายเดือน วางแผนสินค้าและเข้าพบหน่วยงาน",
     "not_weekly", 75),
    (["P0"], "📅 แผนจัดซื้อใหม่ (สรุปรายสัปดาห์)", "โอกาสล่วงหน้า วางแผนเข้าพบหน่วยงาน", "weekly", None),
    (["W0"], "📊 ผลผู้ชนะในหมวดของเรา (สรุปรายสัปดาห์)", "ดูว่าใครชนะ และหน่วยงานไหนซื้อของสำนักงานบ่อย",
     "weekly", None),
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


def expected_label(r):
    """Plans carry the month the department expects to announce, e.g. '2026-10' -> 'ต.ค. 2569'."""
    if not r.get("expected_month"):
        return None
    year, month = (int(x) for x in r["expected_month"].split("-"))
    names = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    return f"{names[month - 1]} {year + 543}"


def bid_cell(r, today):
    if not r.get("bid_date"):
        expected = expected_label(r)
        return f"<span style='color:#666;font-size:12px'>คาดว่าประกาศ</span><br>{expected}" if expected else "-"
    left = days_left(r, today)
    when = datetime.fromisoformat(r["bid_date"]).strftime("%d/%m")
    time_ = f" {r['bid_time']}" if r.get("bid_time") else ""
    color = "#c00" if left <= 3 else "#333"
    note = "ผ่านไปแล้ว" if left < 0 else ("วันนี้" if left == 0 else f"อีก {left} วัน")
    return f"{when}{time_}<div style='color:{color};font-size:12px'><b>{note}</b></div>"


EMAIL_ROW_LIMIT = 30  # per section; the attached Excel always has every row


def section_html(heading, hint, rows, today, results=False):
    """results=True (W0): the money and date columns show the winning price and the winner instead."""
    out = [f'<h3 style="margin:24px 0 4px">{html.escape(heading)} ({len(rows)})</h3>',
           f'<div style="color:#666;font-size:13px;margin-bottom:8px">{html.escape(hint)}</div>']
    shown, rows = rows, rows[:EMAIL_ROW_LIMIT]
    if not rows:
        out.append('<div style="color:#999;font-size:13px">ไม่มีรายการใหม่</div>')
        return "\n".join(out)
    money_head, last_head = ("ราคาที่ชนะ (บาท)", "ผู้ชนะ") if results else ("งบ (บาท)", "วันยื่นซอง")
    out.append('<table cellpadding="6" style="border-collapse:collapse;font-size:13px;width:100%">'
               '<tr style="background:#f2f2f2;text-align:left"><th>คะแนน</th><th>โครงการ</th><th>หน่วยงาน</th>'
               f'<th>{money_head}</th><th>{last_head}</th><th>วันที่ประกาศ</th></tr>')
    for r in rows:
        flags = ", ".join(TYPE_LABEL.get(s, s) for s in (r.get("stages") or []) if s != r["announce_type"])
        badges = ' <b style="color:#1f7a3a">[OfficeMate ชนะ]</b>' if results and is_ours(r.get("winners")) else ""
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
            f"<td>{html.escape(r.get('dept_name') or '')}"
            f"<div style='color:#888;font-size:12px'>{html.escape(r.get('province') or 'ไม่ระบุจังหวัด')}</div></td>"
            f"<td style='text-align:right'>{fmt_money(r.get('winner_price') if results else r.get('budget_thb'))}</td>"
            f"<td>{html.escape(r.get('winners') or '-') if results else bid_cell(r, today)}</td>"
            f"<td>{r.get('pub_date') or ''}</td></tr>")
    out.append("</table>")
    if len(shown) > len(rows):
        out.append(f'<div style="color:#666;font-size:12px">แสดง {len(rows)} อันดับแรก '
                   f'จาก {len(shown)} รายการ · ดูทั้งหมดในไฟล์ Excel แนบ</div>')
    return "\n".join(out)


def is_ours(winners) -> bool:
    """OfficeMate bids as "บริษัท ออฟฟิศเมท (ไทย) จำกัด"; some documents spell ำ as ํ + า."""
    return bool(winners) and re.search(r"ออฟฟิศ\s*เมท", winners.replace("ํา", "ำ")) is not None


def small_table(headers, rows, numeric=()):
    """rows: lists of cell values; columns named in `numeric` are money, right-aligned."""
    out = ['<table cellpadding="6" style="border-collapse:collapse;font-size:13px;width:100%;margin-bottom:8px">'
           '<tr style="background:#f2f2f2;text-align:left">' + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"]
    for cells in rows[:EMAIL_ROW_LIMIT]:
        tds = []
        for h, v in zip(headers, cells):
            if h in numeric:
                tds.append(f"<td style='text-align:right;white-space:nowrap'>{fmt_money(v)}</td>")
            else:
                tds.append(f"<td>{v}</td>")  # callers pass escaped HTML
        out.append("<tr style='border-top:1px solid #eee;vertical-align:top'>" + "".join(tds) + "</tr>")
    out.append("</table>")
    if len(rows) > EMAIL_ROW_LIMIT:
        out.append(f'<div style="color:#666;font-size:12px">แสดง {EMAIL_ROW_LIMIT} จาก {len(rows)} รายการ '
                   '· ดูทั้งหมดในแท็บ "ผลลัพธ์" ของไฟล์ Excel</div>')
    return "\n".join(out)


def outcomes_html(rows, targets):
    """Monday: what happened to the leads, read from e-GP itself (W0 winners, D1 cancellations).
    Returns (html, rows for the Excel tab)."""
    def link(r):
        return f"<a href=\"{html.escape(r['link'])}\">{html.escape(r['title'][:160])}</a>"

    def where(r):
        return (f"{html.escape(r.get('dept_name') or '')}"
                f"<div style='color:#888;font-size:12px'>{html.escape(r.get('province') or 'ไม่ระบุจังหวัด')}</div>")

    def ours_area(r):  # same rule as the rest of the email: Sales' provinces plus unplaced ones
        return not r.get("province") or r["province"] in targets

    results = [r for r in rows if r["kind"] == "result"]
    wins = sorted([r for r in results if r["ours"]], key=lambda r: -(r.get("winner_price") or 0))
    lead_results = [r for r in results if r.get("lead_types")]
    lost = sorted([r for r in lead_results if not r["ours"] and ours_area(r)],
                  key=lambda r: -(r.get("winner_price") or 0))
    cancelled = [r for r in rows if r["kind"] == "cancelled" and ours_area(r)]
    rivals = {}
    for r in results:
        if not r["ours"] and ours_area(r) and r.get("winners"):
            n, total = rivals.get(r["winners"], (0, 0.0))
            rivals[r["winners"]] = (n + 1, total + float(r.get("winner_price") or 0))
    top = sorted(rivals.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))[:10]

    win_value = sum(float(r.get("winner_price") or 0) for r in wins)
    out = ['<h3 style="margin:24px 0 4px">🏆 ผลลัพธ์ประจำสัปดาห์</h3>',
           '<div style="color:#666;font-size:13px;margin-bottom:8px">ระบบตรวจเองจากประกาศผู้ชนะ (W0) และประกาศยกเลิก (D1) '
           'ของ 7 วันที่ผ่านมา นับเฉพาะประกาศผู้ชนะในหมวดสินค้าของเรา (คะแนน ≥ 50) ที่ระบบอ่านแล้ว</div>',
           '<div style="background:#f6f8f9;border:1px solid #e3e8eb;border-radius:6px;padding:10px 12px;font-size:14px;'
           'margin-bottom:10px">'
           f'<b>OfficeMate ชนะ {len(wins)} รายการ มูลค่า {fmt_money(win_value)} บาท</b> (ทุกจังหวัด) · '
           f'Lead ที่ประกาศผลแล้ว {len(lead_results)} รายการ: เราชนะ {sum(r["ours"] for r in lead_results)} · '
           f'บริษัทอื่นชนะ {len(lost)} · Lead ถูกยกเลิก {len(cancelled)}</div>']
    if wins:
        out.append("<b>OfficeMate ชนะ</b>")
        out.append(small_table(
            ["โครงการ", "หน่วยงาน", "ราคาที่ชนะ (บาท)", "มาจาก Lead"],
            [[link(r), where(r), r.get("winner_price"),
              ", ".join(TYPE_LABEL.get(t, t) for t in r["lead_types"]) if r.get("lead_types")
              else "<span style='color:#888'>ไม่มี (เช่น เฉพาะเจาะจง)</span>"] for r in wins],
            numeric={"ราคาที่ชนะ (บาท)"}))
    if lost:
        out.append("<b>Lead ที่บริษัทอื่นชนะ</b> <span style='color:#888;font-size:12px'>"
                   "(เคยส่งเป็นประกาศเชิญชวน/ร่าง TOR/ราคากลาง)</span>")
        out.append(small_table(
            ["โครงการ", "หน่วยงาน", "ผู้ชนะ", "ราคาที่ชนะ (บาท)", "งบ (บาท)"],
            [[link(r), where(r), html.escape(r["winners"]), r.get("winner_price"), r.get("budget_thb")] for r in lost],
            numeric={"ราคาที่ชนะ (บาท)", "งบ (บาท)"}))
    if cancelled:
        out.append("<b>Lead ที่ถูกยกเลิก</b>")
        out.append(small_table(["โครงการ", "หน่วยงาน", "งบ (บาท)"],
                               [[link(r), where(r), r.get("budget_thb")] for r in cancelled], numeric={"งบ (บาท)"}))
    if top:
        out.append("<b>คู่แข่งที่ชนะบ่อย</b> <span style='color:#888;font-size:12px'>(จังหวัดเป้าหมายและไม่ระบุจังหวัด)</span>")
        out.append(small_table(["ผู้ชนะ", "ครั้ง", "มูลค่ารวม (บาท)"],
                               [[html.escape(name), n, total] for name, (n, total) in top],
                               numeric={"มูลค่ารวม (บาท)"}))

    def label(r):
        if r["kind"] == "cancelled":
            return "Lead ถูกยกเลิก"
        if r["ours"]:
            return "OfficeMate ชนะ"
        return "บริษัทอื่นชนะ (เคยเป็น Lead)" if r.get("lead_types") else "บริษัทอื่นชนะ"
    order = ["OfficeMate ชนะ", "บริษัทอื่นชนะ (เคยเป็น Lead)", "Lead ถูกยกเลิก", "บริษัทอื่นชนะ"]
    sheet = sorted(({**r, "outcome": label(r), "lead_from": ", ".join(r.get("lead_types") or [])} for r in rows),
                   key=lambda r: (order.index(r["outcome"]), -(r.get("winner_price") or 0)))
    return "\n".join(out), sheet


def build(db: DB, since: datetime, now: datetime, weekly: bool, min_score: int, targets: set[str],
          with_outcomes: bool = True):
    """Returns (email html, rows in the email, rows clearly in other provinces, Monday outcome rows)."""
    today = now.date()
    parts, all_rows, elsewhere, outcome_rows = [], [], [], []
    if weekly and with_outcomes:
        rows = db.rpc("outcome_items", {"p_since": (now - timedelta(days=7)).isoformat()})
        section, outcome_rows = outcomes_html(rows, targets)
        parts.append(section)
    for types, heading, hint, when, sec_min in SECTIONS:
        if (when == "weekly" and not weekly) or (when == "not_weekly" and weekly):
            continue
        # Weekly sections look back 7 days regardless of when the last daily digest went out.
        sec_since = min(since, now - timedelta(days=7)) if when == "weekly" else since
        rows = db.rpc("digest_items", {"p_since": sec_since.isoformat(), "p_types": types,
                                       "p_min_score": max(min_score, sec_min or 0)})
        # Keep Sales' provinces and the ones nobody could place; set the rest aside for the Excel tab.
        elsewhere += [{**r, "section": heading, "days_left": days_left(r, today)} for r in rows
                      if r.get("province") and r["province"] not in targets]
        rows = [r for r in rows if not r.get("province") or r["province"] in targets]
        if types == ["15"]:
            # Reference prices for projects that also got a D0 are already shown under D0.
            rows = [r for r in rows if "D0" not in (r.get("stages") or [])]
        if types == ["D0"]:
            # Bids closing soonest first; unknown or past deadlines after them.
            def urgency(r):
                left = days_left(r, today)
                return (left is None or left < 0, left if left is not None else 999, -r["score"])
            rows.sort(key=urgency)
        parts.append(section_html(heading, hint, rows, today, results=types == ["W0"]))
        all_rows += [{**r, "section": heading, "days_left": days_left(r, today)} for r in rows]

    total = len(all_rows)
    head = (f'<div style="font-family:Tahoma,sans-serif;max-width:980px">'
            f'<h2 style="margin:0">e-GP Alert — {now:%d/%m/%Y}</h2>'
            f'<div style="color:#666">ประกาศใหม่ที่เกี่ยวกับ OfficeMate ตั้งแต่ {since.astimezone(BKK):%d/%m %H:%M} น. '
            f'รวม {total} รายการ (คะแนน ≥ {min_score})<br>เฉพาะจังหวัด: {html.escape(", ".join(sorted(targets)))} '
            f'และประกาศที่ไม่ระบุจังหวัด (ส่วนใหญ่เป็นส่วนกลาง)'
            + (f' · จังหวัดอื่น {len(elsewhere)} รายการอยู่ในแท็บ "จังหวัดอื่น" ของไฟล์ Excel' if elsewhere else '')
            + '</div>')
    bands = " · ".join(f"{b} {d}" for b, d in SCORE_BANDS[:4])
    foot = (f'<p style="color:#999;font-size:12px;margin-top:24px">คะแนน = ความตรงกับสินค้า OfficeMate: '
            f'{html.escape(bands)}<br>งบ = ราคากลางจากเอกสารประกาศ · ไฟล์ Excel แนบมีรายการทั้งหมดและแท็บคำอธิบาย '
            '· ระบบ e-GP Alert v3</p></div>')
    return head + "\n".join(parts) + foot, all_rows, elsewhere, outcome_rows


OUTCOME_COLS = {"outcome": "ผลลัพธ์", "title": "ชื่อโครงการ", "dept_name": "หน่วยงาน", "province": "จังหวัด",
                "winners": "ผู้ชนะ", "winner_price": "ราคาที่ชนะ (บาท)", "budget_thb": "งบประมาณ (บาท)",
                "lead_from": "เคยส่งเป็น Lead (ประเภท)", "pub_date": "วันที่ประกาศ", "project_no": "เลขโครงการ",
                "link": "ลิงก์"}


def write_xlsx(rows, path, elsewhere=(), outcomes=()):
    cols = {"section": "หมวดอีเมล", "score": "คะแนน", "type_label": "ประเภทประกาศ", "title": "ชื่อโครงการ",
            "dept_name": "หน่วยงาน", "province": "จังหวัด", "category": "หมวดสินค้า", "reason": "เหตุผล",
            "budget_thb": "งบประมาณ (บาท)", "winners": "ผู้ชนะ", "winner_price": "ราคาที่ชนะ (บาท)",
            "bid_date": "วันยื่นซอง", "bid_time": "เวลายื่น", "days_left": "เหลือ (วัน)",
            "expected": "คาดว่าจะประกาศ",
            "pub_date": "วันที่ประกาศ", "method": "วิธีจัดหา", "project_no": "เลขโครงการ", "plan_no": "เลขแผน",
            "cancelled": "ยกเลิกแล้ว", "amended": "มีการแก้ไขประกาศ", "link": "ลิงก์"}
    def frame(rs):
        data = [{**r, "type_label": f"{TYPE_LABEL.get(r['announce_type'], r['announce_type'])} ({r['announce_type']})",
                 "expected": expected_label(r)} for r in rs]
        return pd.DataFrame(data, columns=list(cols)).rename(columns=cols)

    columns_help = [
        ("จังหวัด", "อ่านจากชื่อโครงการและเอกสารประกาศ (ว่าง = เอกสารไม่ระบุจังหวัด ส่วนใหญ่เป็นหน่วยงานส่วนกลาง)"),
        ("งบประมาณ (บาท)", "ราคากลางจากเอกสารประกาศ หรืองบประมาณโครงการจากหน้าแผนจัดซื้อ (ว่าง = เอกสารต้องล็อกอิน e-GP หรือไม่ระบุ "
                           "ประกาศผู้ชนะแบบเฉพาะเจาะจงไม่มีประกาศราคากลางก่อนหน้า จึงมักว่าง ให้ดูราคาที่ชนะแทน)"),
        ("ผู้ชนะ / ราคาที่ชนะ (บาท)", "ชื่อผู้ชนะและราคาที่เสนอจากประกาศผู้ชนะ (W0) ถ้ามีหลายรายการ ราคาเป็นยอดรวม"),
        ("วันยื่นซอง / เวลายื่น", "วันและช่วงเวลาเสนอราคาในระบบ e-GP (มีเฉพาะประกาศเชิญชวน)"),
        ("คาดว่าจะประกาศ", "เดือนที่หน่วยงานคาดว่าจะประกาศจัดซื้อ (มีเฉพาะแผนจัดซื้อ P0)"),
        ("เหลือ (วัน)", "จำนวนวันจากวันที่ส่งอีเมลถึงวันยื่นซอง"),
        ("ยกเลิกแล้ว", "โครงการเดียวกันมีประกาศยกเลิกประกาศเชิญชวน (D1) ตามมา — ไม่ต้องตามต่อ"),
        ("มีการแก้ไขประกาศ", "โครงการเดียวกันมีประกาศแก้ไขประกาศเชิญชวน (D2) — เปิดดูรายละเอียดใหม่"),
        ("เลขโครงการ", "เลข 11 หลักของ e-GP ใช้ค้นหาโครงการในเว็บ e-GP"),
        ("แท็บ ผลลัพธ์ (วันจันทร์)", "ผลของ 7 วันที่ผ่านมาที่ระบบตรวจเองจากประกาศผู้ชนะ (W0) และประกาศยกเลิก (D1): "
                                    "OfficeMate ชนะ / บริษัทอื่นชนะ (เคยเป็น Lead) / บริษัทอื่นชนะ / Lead ถูกยกเลิก "
                                    "\"เคยส่งเป็น Lead\" = โครงการเดียวกันเคยอยู่ในอีเมลเป็นประกาศเชิญชวน ร่าง TOR หรือราคากลาง"),
    ]
    legend = ([{"หัวข้อ": "ประเภทประกาศ", "ค่า": f"{TYPE_LABEL[k]} ({k})", "ความหมาย": v}
               for k, v in TYPE_MEANING.items()]
              + [{"หัวข้อ": "คะแนน", "ค่า": b, "ความหมาย": d} for b, d in SCORE_BANDS]
              + [{"หัวข้อ": "คอลัมน์", "ค่า": k, "ความหมาย": v} for k, v in columns_help])
    sheets = [("รายการ", rows)] + ([("จังหวัดอื่น", elsewhere)] if elsewhere else [])
    with pd.ExcelWriter(path) as xw:
        if outcomes:  # Mondays: results first, it is the headline of the week
            pd.DataFrame(list(outcomes), columns=list(OUTCOME_COLS)).rename(columns=OUTCOME_COLS).to_excel(
                xw, sheet_name="ผลลัพธ์", index=False)
            style_sheet(xw.sheets["ผลลัพธ์"], number_cols={"งบประมาณ (บาท)", "ราคาที่ชนะ (บาท)"},
                        wrap_cols={"ชื่อโครงการ": 60, "หน่วยงาน": 28, "ผู้ชนะ": 30})
        for name, rs in sheets:
            frame(rs).to_excel(xw, sheet_name=name, index=False)
        pd.DataFrame(legend).to_excel(xw, sheet_name="คำอธิบาย", index=False)
        for name, _ in sheets:
            style_sheet(xw.sheets[name], number_cols={"งบประมาณ (บาท)", "ราคาที่ชนะ (บาท)"},
                        wrap_cols={"ชื่อโครงการ": 60, "เหตุผล": 35, "หน่วยงาน": 28, "ผู้ชนะ": 30,
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

    targets = provinces.parse_targets(os.environ.get("TARGET_PROVINCES") or DEFAULT_PROVINCES)
    out = os.path.join(ROOT, "out")
    os.makedirs(out, exist_ok=True)

    def make(loop: bool, suffix: str = ""):
        """loop=True adds the KG Lead Loop parts (Monday outcomes). While those are on trial they go only
        to LOOP_RECIPIENTS; the team's digest stays as it was."""
        body, rows, elsewhere, outcomes = build(db, since, now, weekly, args.min_score, targets, with_outcomes=loop)
        xlsx = os.path.join(out, f"eGP_Alert_{now:%Y%m%d}{suffix}.xlsx")
        write_xlsx(rows, xlsx, elsewhere, outcomes)
        with open(os.path.join(out, f"digest_preview{suffix}.html"), "w", encoding="utf-8") as f:
            f.write(body)
        print(f"digest{suffix} since {since:%Y-%m-%d %H:%M} weekly={weekly}: {len(rows)} items "
              f"(+{len(elsewhere)} in other provinces, {len(outcomes)} outcomes) -> {out}")
        return body, rows, outcomes, xlsx

    def subject(rows, outcomes, prefix=""):
        n_new = len(rows)
        weekly_headings = {h for _, h, _, when, _ in SECTIONS if when == "weekly"}
        n_daily = sum(r["section"] not in weekly_headings for r in rows)
        n_bid = sum(r["announce_type"] == "D0" for r in rows)
        n_prep = sum(r["announce_type"] == "B0" for r in rows)
        n_plan = sum(r["announce_type"] == "P0" and r["section"] not in weekly_headings for r in rows)
        weekly_note = f" + สรุปรายสัปดาห์ {n_new - n_daily} รายการ" if n_new > n_daily else ""
        n_wins = sum(r["outcome"] == "OfficeMate ชนะ" for r in outcomes)
        if n_wins:
            weekly_note += f" · 🏆 OfficeMate ชนะ {n_wins}"
        return prefix + (f"🚨 e-GP Alert {now:%d/%m/%Y}: ยื่นราคาได้ {n_bid} · เตรียมของ {n_prep} · "
                         f"{f'แผนใหม่ {n_plan} · ' if n_plan else ''}"
                         f"ใหม่รวม {n_daily} โครงการ{weekly_note}" if n_daily
                         else f"ℹ️ e-GP Alert {now:%d/%m/%Y}: ไม่มีโครงการใหม่{weekly_note}")

    def emails(value):
        return [e.strip() for e in (value or "").split(",") if e.strip()]

    loop_to = emails(os.environ.get("LOOP_RECIPIENTS"))
    if not args.send:
        make(loop=True)  # previews show everything, trial parts included
        return

    if args.to:  # a test send: the full version, and the "since" window of the real digest stays put
        body, rows, outcomes, xlsx = make(loop=True)
        send(subject(rows, outcomes, "[ทดสอบ] "), body, xlsx, emails(args.to))
        print(f"test sent to {len(emails(args.to))} recipient(s)")
        return

    # DIGEST_RECIPIENTS (a repository variable) overrides the team list, e.g. for a trial period.
    recipients = emails(os.environ.get("DIGEST_RECIPIENTS") or os.environ["RECEIVER_EMAIL"])
    body, rows, outcomes, xlsx = make(loop=not loop_to)
    send(subject(rows, outcomes), body, xlsx, recipients)
    db.insert("digests", {"kind": "daily", "since": since.isoformat(), "n_items": len(rows),
                          "recipients": ",".join(recipients)}, returning=False)
    print(f"sent to {len(recipients)} recipient(s)")
    if loop_to:
        body, rows, outcomes, xlsx = make(loop=True, suffix="_trial")
        send(subject(rows, outcomes, "[ทดลอง Lead Loop] "), body, xlsx, loop_to)
        print(f"trial version sent to {len(loop_to)} recipient(s)")


if __name__ == "__main__":
    main()
