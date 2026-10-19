"""Which province an announcement is for.

The RSS feed only names the top-level department (e.g. กรมส่งเสริมการปกครองท้องถิ่น covers every local
government in the country), so the province is read from the title and the announcement document:
office names, addresses and the signer's position ("ผู้อำนวยการ...จังหวัดชลบุรี") name it.
"""
import re

PROVINCES = [
    "กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น", "จันทบุรี", "ฉะเชิงเทรา",
    "ชลบุรี", "ชัยนาท", "ชัยภูมิ", "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง", "ตราด", "ตาก", "นครนายก",
    "นครปฐม", "นครพนม", "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส", "น่าน",
    "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา",
    "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี", "เพชรบูรณ์", "แพร่", "ภูเก็ต",
    "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน", "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง", "ระยอง", "ราชบุรี",
    "ลพบุรี", "ลำปาง", "ลำพูน", "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ",
    "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว", "สระบุรี", "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี",
    "สุราษฎร์ธานี", "สุรินทร์", "หนองคาย", "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี",
    "อุตรดิตถ์", "อุทัยธานี", "อุบลราชธานี",
]
ALIASES = {"กรุงเทพฯ": "กรุงเทพมหานคร", "กรุงเทพ": "กรุงเทพมหานคร", "กทม": "กรุงเทพมหานคร",
           "อยุธยา": "พระนครศรีอยุธยา", "โคราช": "นครราชสีมา"}
# Names that are also ordinary words or parts of words (เลย, เผยแพร่, ตากแดด, น่านน้ำ, ตรังค์) count only
# after "จังหวัด" / "จ." / "จว.".
NEEDS_PREFIX = {"เลย", "แพร่", "ตาก", "น่าน", "ตรัง"}
PREFIX = r"(?:จังหวัด|จ\.|จว\.)\s*"

_plain = sorted([p for p in PROVINCES if p not in NEEDS_PREFIX] + list(ALIASES), key=len, reverse=True)
_PATTERN = re.compile(
    "(?:" + PREFIX + "(" + "|".join(sorted(PROVINCES + list(ALIASES), key=len, reverse=True)) + "))"
    "|(" + "|".join(map(re.escape, _plain)) + ")")


def mentions(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in _PATTERN.finditer(text or ""):
        name = m.group(1) or m.group(2)
        name = ALIASES.get(name, name)
        counts[name] = counts.get(name, 0) + 1
    return counts


def detect(title: str, document: str = "") -> str | None:
    """The province named in the title, else the one the document names most often."""
    for text in (title, document):
        counts = mentions(text)
        if counts:
            return max(counts, key=lambda p: (counts[p], -text.find(p)))
    return None


def parse_targets(value: str) -> set[str]:
    """'กรุงเทพมหานคร, นนทบุรี' -> {'กรุงเทพมหานคร', 'นนทบุรี'}; unknown names raise."""
    names = {ALIASES.get(n.strip(), n.strip()) for n in re.split(r"[,\n]", value or "") if n.strip()}
    unknown = names - set(PROVINCES)
    if unknown:
        raise ValueError(f"unknown province name(s): {', '.join(sorted(unknown))}")
    return names
