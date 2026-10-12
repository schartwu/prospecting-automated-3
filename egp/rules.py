"""Keyword rules that decide clear-cut titles without calling Gemini.

Measured against 1,460 Gemini-labelled titles (2026-10-12): the rules decided 69% of titles and agreed
with Gemini on 99%. Titles that hit both lists (e.g. "ซื้อครุภัณฑ์สำนักงาน และครุภัณฑ์ก่อสร้าง") or
neither are left for Gemini.
"""
import re

MODEL = "rules-v1"

NOT_OURS = re.compile(
    "จ้างก่อสร้าง|ก่อสร้าง|จ้างเหมา|บำรุงรักษา|ซ่อม|ที่ปรึกษา|การแพทย์|วิทยาศาสตร์|ยานพาหนะ|รถยนต์|รถบรรทุก|"
    "รถตู้|น้ำมัน|อาหาร|ข้าวสาร|เวชภัณฑ์|ทำความสะอาดอาคาร|รักษาความปลอดภัย|จัดสถานที่|พวงมาลา|ประชาสัมพันธ์|"
    "พัฒนาระบบ|ฝึกอบรม|สัมมนา|ศึกษา|วิจัย|ปรับปรุง|ติดตั้งระบบ|วัสดุการเกษตร|เครื่องแบบ|ประปา|ไฟฟ้าถนน")

OURS = re.compile(
    "วัสดุสำนักงาน|กระดาษ|หมึก|โทนเนอร์|เครื่องเขียน|ครุภัณฑ์คอมพิวเตอร์|วัสดุคอมพิวเตอร์|โน้ตบุ๊ก|"
    "เครื่องพิมพ์|ครุภัณฑ์สำนักงาน|เครื่องถ่ายเอกสาร|เครื่องทำลายเอกสาร|เก้าอี้|โต๊ะทำงาน|ตู้เอกสาร|วัสดุงานบ้าน")


# First match wins; used to fill the category for titles the rules accept.
CATEGORY_BY_WORD = [
    ("หมึก|โทนเนอร์", "หมึกพิมพ์และวัสดุสิ้นเปลืองงานพิมพ์"),
    ("คอมพิวเตอร์|โน้ตบุ๊ก|เครื่องพิมพ์", "คอมพิวเตอร์และอุปกรณ์ไอที"),
    ("กระดาษ|เครื่องเขียน", "กระดาษและเครื่องเขียน"),
    ("เก้าอี้|โต๊ะทำงาน|ตู้เอกสาร", "เฟอร์นิเจอร์สำนักงาน"),
    ("เครื่องถ่ายเอกสาร|เครื่องทำลายเอกสาร|ครุภัณฑ์สำนักงาน", "เครื่องใช้สำนักงาน"),
    ("วัสดุงานบ้าน", "วัสดุงานบ้านงานครัวและทำความสะอาด"),
    ("วัสดุสำนักงาน", "วัสดุสำนักงานรวมหลายหมวด"),
]


def decide(title: str) -> dict | None:
    """Return a verdict like the Gemini classifier's, or None when the title needs Gemini."""
    ours, not_ours = OURS.search(title), NOT_OURS.search(title)
    if ours and not not_ours:
        category = next((c for words, c in CATEGORY_BY_WORD if re.search(words, title)), None)
        return {"relevant": True, "score": 90, "category": category,
                "reason": f"คำว่า '{ours.group(0)}' ตรงสินค้า OfficeMate", "model": MODEL}
    if not_ours and not ours:
        return {"relevant": False, "score": 0, "category": "ไม่เกี่ยวข้อง",
                "reason": f"คำว่า '{not_ours.group(0)}' ไม่ใช่สินค้าที่ขาย", "model": MODEL}
    return None
