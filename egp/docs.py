"""Read budget (ราคากลาง) and bid date (วันเสนอราคา) from the document an announcement links to.

D0 links are a PDF announcement. B0 and some 15 links are a ZIP holding the draft announcement
(annoudoc_*.pdf / pB0.pdf), the draft bid document (doc_*.pdf) and the TOR (Attach_TOR_*.pdf).
The PDF text layer comes out with words in jumbled order, so the patterns look for the pieces
separately instead of expecting a clean sentence.
"""
import io
import re
import zipfile
from datetime import date, timedelta

import pymupdf as fitz
import requests

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
          "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
MONEY = r"(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+\.\d{2})\s*บาท"
MAX_DOWNLOAD = 15 * 1024 * 1024
# Inside a ZIP, the short announcement documents carry the numbers; the TOR is long and comes last.
ZIP_ORDER = [r"^annoudoc", r"^pB0", r"^doc_", r"\.pdf$"]


def fetch_text(url: str) -> tuple[str, dict]:
    """Download the linked document and return (plain text, info about what was read)."""
    resp = requests.get(url, timeout=90, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
    resp.raise_for_status()
    data = resp.raw.read(MAX_DOWNLOAD + 1, decode_content=True)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("document larger than 15 MB")
    info = {"content_type": resp.headers.get("Content-Type", ""), "bytes": len(data)}
    if data[:4] == b"%PDF":
        return _pdf_text(data), {**info, "kind": "pdf"}
    if data[:2] == b"PK":
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
        info.update(kind="zip", files=names, tor=[n for n in names if "tor" in n.lower()])
        ordered = sorted(names, key=lambda n: next(i for i, p in enumerate(ZIP_ORDER) if re.search(p, n, re.I)))
        texts = [_pdf_text(zf.read(n)) for n in ordered if "tor" not in n.lower()][:3]
        return "\n".join(texts), info
    return "", {**info, "kind": "other"}  # e.g. an HTML login page


def _pdf_text(data: bytes) -> str:
    with fitz.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(THAI_DIGITS))


def parse_budget(text: str) -> float | None:
    """ราคากลาง ... เป็นเงินทั้งสิ้น 1,600,000.00 บาท (words in between are often shuffled in)."""
    for anchor in ("เป็นเงินทั้งสิ้น", "ราคากลาง", "วงเงิน"):
        for m in re.finditer(anchor, text):
            hit = re.search(MONEY, text[m.end():m.end() + 160])
            if hit:
                return float(hit.group(1).replace(",", ""))
    return None


def parse_bid_date(text: str) -> tuple[date | None, str | None]:
    """'เสนอราคา...อิเล็กทรอนิกส์ในวันที่ 21 ระหว่างเวลา น. ถึง น. ... ตุลาคม 2569 09.00 12.00'.
    Day comes first, then month + Buddhist-era year and the time window further on."""
    m = re.search(r"อิเล็กทรอนิกส์\s*ในวันที่\s*(\d{1,2})", text)
    if not m:
        return None, None
    tail = text[m.end():m.end() + 400]
    my = re.search(r"(" + "|".join(MONTHS) + r")\s*(?:พ\.ศ\.\s*)?(\d{4})", tail)
    if not my:
        return None, None
    try:
        d = date(int(my.group(2)) - 543, MONTHS.index(my.group(1)) + 1, int(m.group(1)))
    except ValueError:
        return None, None
    times = re.findall(r"\b(\d{2}\.\d{2})\b", tail[my.end():my.end() + 60])
    return d, (f"{times[0]}-{times[1]}" if len(times) >= 2 else None)


def plausible(bid: date | None, pub: date | None) -> bool:
    """A bid date before the announcement or months later means the pattern grabbed the wrong date."""
    return bid is not None and (pub is None or pub <= bid <= pub + timedelta(days=90))


EXTRACT_PROMPT = """ข้อความด้านล่างมาจากเอกสารประกาศจัดซื้อจัดจ้างภาครัฐ (ข้อความอาจเรียงสลับตำแหน่ง)
ให้ดึงข้อมูลต่อไปนี้ ถ้าไม่มีในเอกสารให้ใส่ null:
- budget_thb: ราคากลาง/วงเงินงบประมาณรวม เป็นตัวเลขบาท
- bid_date: วันที่ยื่นข้อเสนอ/เสนอราคา รูปแบบ YYYY-MM-DD เป็นปี ค.ศ. (แปลง พ.ศ. ลบ 543)
- bid_time: ช่วงเวลายื่นข้อเสนอ เช่น "09.00-12.00"
- item_count: จำนวนรายการสินค้า (ตัวเลข)

เอกสาร:
{text}
"""

EXTRACT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "budget_thb": {"type": "NUMBER", "nullable": True},
        "bid_date": {"type": "STRING", "nullable": True},
        "bid_time": {"type": "STRING", "nullable": True},
        "item_count": {"type": "INTEGER", "nullable": True},
    },
    "required": ["budget_thb", "bid_date", "bid_time", "item_count"],
}
