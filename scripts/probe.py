"""Send a few single RSS requests one at a time and print exactly what happens (timing, status, size, error)."""
import time

import requests

BASE = "http://process3.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml"
CASES = [
    "methodId=16&anounceType=D0&deptId=0307",  # exactly what v2 sends
    "anounceType=D0&deptId=0307",
    "deptId=0307",
    "methodId=15&anounceType=D0&deptId=0307",
    "methodId=16&anounceType=P0&deptId=0307",
    "methodId=16&anounceType=15&deptId=0307",
    "methodId=16&anounceType=B0&deptId=0307",
    "methodId=16&anounceType=W0&deptId=0307",
    "methodId=16&anounceType=D0&deptId=2101",
    "anounceType=P0&deptId=2101",
    "methodId=16&anounceType=D0",
    "methodId=16&anounceType=D0&deptsubId=0300700101",
]

for q in CASES:
    url = f"{BASE}?{q}"
    t0 = time.monotonic()
    try:
        # stream + wall-clock cap, because a slow server can trickle bytes past a normal read timeout
        with requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=(10, 30), stream=True) as r:
            body = b""
            for chunk in r.iter_content(8192):
                body += chunk
                if time.monotonic() - t0 > 90:
                    raise TimeoutError("wall clock > 90s")
            txt = body.decode("cp874", errors="replace")
            print(f"[{time.monotonic()-t0:5.1f}s] HTTP {r.status_code} {len(body):>7}B items={txt.count('<item>')} | {q}", flush=True)
            if "<item>" in txt:
                i = txt.index("<item>")
                print("        ", txt[i:i+600].replace("\n", " "), flush=True)
            elif body:
                print("        ", txt[:300].replace("\n", " "), flush=True)
    except Exception as e:
        print(f"[{time.monotonic()-t0:5.1f}s] FAIL {type(e).__name__}: {str(e)[:200]} | {q}", flush=True)
    time.sleep(2)
