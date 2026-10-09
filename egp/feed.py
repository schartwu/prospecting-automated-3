"""Client for the e-GP announcement RSS feed (กรมบัญชีกลาง, หนังสือ ว37/2561).

Feed limits (manual section 4): XML only, at most the 20 latest items, current day only.
"""
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests

BASE_URL = "http://process3.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml"
FEED_ITEM_CAP = 20

ANNOUNCE_TYPES = {
    "P0": "แผนการจัดซื้อจัดจ้าง",
    "15": "ประกาศราคากลาง",
    "B0": "ร่างเอกสารประกวดราคา / ร่างเอกสารซื้อหรือจ้างด้วยวิธีสอบราคา",
    "D0": "ประกาศเชิญชวน",
    "W0": "ประกาศรายชื่อผู้ชนะการเสนอราคา / ผู้ได้รับการคัดเลือก",
    "D1": "ยกเลิกประกาศเชิญชวน",
    "W1": "ยกเลิกประกาศรายชื่อผู้ชนะ",
    "D2": "เปลี่ยนแปลงประกาศเชิญชวน",
    "W2": "เปลี่ยนแปลงประกาศรายชื่อผู้ชนะ",
}

METHODS = {
    "02": "สอบราคา",
    "15": "e-market",
    "16": "e-bidding",
    "18": "คัดเลือก",
    "19": "เฉพาะเจาะจง",
    "20": "จ้างที่ปรึกษา ประกาศเชิญชวนทั่วไป",
    "21": "จ้างที่ปรึกษา คัดเลือก",
    "22": "จ้างที่ปรึกษา เฉพาะเจาะจง",
    "23": "จ้างออกแบบ/ควบคุมงาน ประกาศเชิญชวนทั่วไป",
    "24": "จ้างออกแบบ/ควบคุมงาน คัดเลือก",
    "25": "จ้างออกแบบ/ควบคุมงาน เฉพาะเจาะจง",
    "26": "จ้างออกแบบ/ควบคุมงาน ประกวดแบบ",
}

_session = requests.Session()
_session.headers["User-Agent"] = "Mozilla/5.0 (prospecting-automated-3)"


@dataclass
class FeedResult:
    params: dict
    ok: bool
    http_status: int | None = None
    channel: dict = field(default_factory=dict)
    items: list = field(default_factory=list)
    error: str | None = None
    elapsed: float = 0.0

    @property
    def capped(self) -> bool:
        """True when the feed hit its 20-item limit, so items were probably dropped."""
        return len(self.items) >= FEED_ITEM_CAP


def _parse(raw: bytes) -> tuple[dict, list]:
    text = raw.decode("cp874", errors="replace")
    # The XML declaration says windows-874 but we already decoded; ElementTree rejects the mismatch.
    text = text.replace('encoding="Windows-874"', "").replace('encoding="windows-874"', "")
    root = ET.fromstring(text)
    channel = root.find("channel")
    if channel is None:
        return {}, []
    meta = {c.tag: (c.text or "").strip() for c in channel if c.tag != "item"}
    items = [{c.tag: (c.text or "").strip() for c in item} for item in channel.findall("item")]
    return meta, items


def fetch(params: dict, timeout: float = 40, retries: int = 2) -> FeedResult:
    started = time.monotonic()
    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = _session.get(BASE_URL, params=params, timeout=timeout)
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
            else:
                meta, items = _parse(resp.content)
                return FeedResult(params, True, resp.status_code, meta, items,
                                  elapsed=time.monotonic() - started)
        except Exception as e:  # network errors and malformed XML are both recorded, never swallowed
            last_error = f"{type(e).__name__}: {e}"
        time.sleep(2 * (attempt + 1))
    return FeedResult(params, False, error=last_error, elapsed=time.monotonic() - started)
