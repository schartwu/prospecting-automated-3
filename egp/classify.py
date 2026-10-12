"""Judge whether a procurement title is something OfficeMate can supply, using Gemini."""
import json
import os
import time

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
# Tried in order when a model's quota is used up or it is overloaded. On the free tier each model has
# its own small daily request quota (20/day), so batches are large and the models share the load.
FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-2.5-flash"]


class QuotaExhausted(RuntimeError):
    """Every model's daily quota is used up; the rest waits for tomorrow."""

CATEGORIES = [
    "กระดาษและเครื่องเขียน",
    "หมึกพิมพ์และวัสดุสิ้นเปลืองงานพิมพ์",
    "คอมพิวเตอร์และอุปกรณ์ไอที",
    "เครื่องใช้สำนักงาน",
    "เฟอร์นิเจอร์สำนักงาน",
    "วัสดุงานบ้านงานครัวและทำความสะอาด",
    "เครื่องใช้ไฟฟ้า",
    "อุปกรณ์ความปลอดภัยและเครื่องมือช่าง",
    "วัสดุสำนักงานรวมหลายหมวด",
    "ไม่เกี่ยวข้อง",
]

PROMPT = """คุณคือผู้คัดกรองโครงการจัดซื้อจัดจ้างภาครัฐ (e-GP) ให้ทีมขายของ OfficeMate
OfficeMate เป็นผู้ค้าปลีก/ค้าส่ง "สินค้าสำเร็จรูป" สำหรับสำนักงาน: กระดาษ เครื่องเขียน หมึกพิมพ์ คอมพิวเตอร์ โน้ตบุ๊ก
เครื่องพิมพ์ อุปกรณ์ไอทีทั่วไป เครื่องใช้สำนักงาน เฟอร์นิเจอร์สำนักงาน วัสดุงานบ้าน/ทำความสะอาด เครื่องใช้ไฟฟ้า
อุปกรณ์ความปลอดภัยและเครื่องมือช่างทั่วไป

ตัดสินแต่ละชื่อโครงการว่า OfficeMate "ขายของในโครงการนี้ได้" หรือไม่:
- เกี่ยวข้อง: การ "ซื้อ" หรือ "เช่า" สินค้าในหมวดข้างต้น เช่น ซื้อวัสดุสำนักงาน, ซื้อครุภัณฑ์คอมพิวเตอร์, ซื้อโต๊ะเก้าอี้,
  ซื้อหมึกพิมพ์, เช่าเครื่องคอมพิวเตอร์ หรือแผนจัดซื้อ (P0) ของสินค้าเหล่านี้
- ไม่เกี่ยวข้อง: งาน "จ้าง" บริการ (จ้างบำรุงรักษา, จ้างซ่อม, จ้างทำความสะอาด, จ้างพัฒนาระบบ, จ้างที่ปรึกษา, จ้างก่อสร้าง),
  ครุภัณฑ์การแพทย์/วิทยาศาสตร์, ยานพาหนะ, วัสดุก่อสร้าง, ระบบเฉพาะทาง (ระบบสูบน้ำ, ระบบไฟฟ้าอาคาร, เครือข่ายขนาดใหญ่
  ที่ต้องติดตั้งเชิงวิศวกรรม), ยา อาหาร น้ำมัน เครื่องแบบ
- ถ้าโครงการผสม (เช่น ซื้อครุภัณฑ์สำนักงานหลายรายการ) และมีของที่ OfficeMate ขายได้เป็นส่วนสำคัญ ให้ถือว่าเกี่ยวข้อง

score 0-100 = ความมั่นใจว่า OfficeMate ขายได้และน่าตาม (100 = ตรงสินค้าหลักชัดเจน เช่น ซื้อวัสดุสำนักงาน/กระดาษ/หมึก)
category ต้องเป็นหนึ่งใน: {categories}
reason เป็นภาษาไทยสั้นๆ ไม่เกิน 15 คำ

ตอบเป็น JSON array เรียงตาม id ที่ให้ ครบทุก id

รายการ:
{items}
"""

SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "INTEGER"},
            "relevant": {"type": "BOOLEAN"},
            "score": {"type": "INTEGER"},
            "category": {"type": "STRING", "enum": CATEGORIES},
            "reason": {"type": "STRING"},
        },
        "required": ["id", "relevant", "score", "category", "reason"],
    },
}


def classify_titles(rows: list[dict], api_key: str, model: str = DEFAULT_MODEL) -> list[dict]:
    """rows: [{'title', 'announce_types', 'methods'}]. Returns one verdict dict per row, same order.
    Falls back to other models when one is overloaded."""
    errors, exhausted = [], []
    for m in [model, *[f for f in FALLBACK_MODELS if f != model]]:
        if m in _exhausted_models:
            continue
        try:
            return _classify_with(rows, api_key, m)
        except _DailyQuota as e:
            _exhausted_models.add(m)
            exhausted.append(m)
            errors.append(str(e))
        except RuntimeError as e:
            errors.append(str(e))
    if all(m in _exhausted_models for m in [model, *FALLBACK_MODELS]):
        raise QuotaExhausted(" | ".join(errors))
    raise RuntimeError(" | ".join(errors))


class _DailyQuota(RuntimeError):
    pass


_exhausted_models: set[str] = set()


def _classify_with(rows: list[dict], api_key: str, model: str, retries: int = 2) -> list[dict]:
    lines = []
    for i, r in enumerate(rows):
        hint = ", ".join(filter(None, [*(r.get("announce_types") or []), *(r.get("methods") or [])]))
        lines.append(f"{i}. [{hint}] {r['title'][:400]}")
    body = {
        "contents": [{"parts": [{"text": PROMPT.format(categories=", ".join(CATEGORIES), items="\n".join(lines))}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA,
                             "maxOutputTokens": 32768},
    }
    last = None
    for attempt in range(retries):
        try:
            resp = requests.post(GEMINI_URL.format(model=model), json=body, timeout=180,
                                 headers={"x-goog-api-key": api_key})
            if resp.status_code == 429 and "PerDay" in resp.text:
                # Daily quota gone: retrying only burns time, move on to the next model.
                raise _DailyQuota(f"{model}: daily quota used up")
            if resp.status_code in (429, 500, 503):
                # Per-minute limit (5 RPM on the free tier) or a temporary overload.
                last = f"HTTP {resp.status_code}: {resp.text[:200]}"
                time.sleep(65)
                continue
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            by_id = {v["id"]: v for v in json.loads(text)}
            missing = [i for i in range(len(rows)) if i not in by_id]
            if missing:
                raise ValueError(f"model skipped ids {missing[:10]}")
            return [{
                "title": rows[i]["title"],
                "relevant": bool(by_id[i]["relevant"]),
                "score": max(0, min(100, int(by_id[i]["score"]))),
                "category": by_id[i]["category"],
                "reason": by_id[i]["reason"][:300],
                "model": model,
            } for i in range(len(rows))]
        except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{model} failed after {retries} attempts: {last[:300]}")


def list_models(api_key: str) -> list[str]:
    resp = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                        headers={"x-goog-api-key": api_key}, params={"pageSize": 200}, timeout=60)
    resp.raise_for_status()
    return [m["name"] for m in resp.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]
