"""Send a few single requests one at a time and print exactly what comes back."""
import requests

URLS = [
    "https://process5.gprocurement.go.th/egp-template-service/dwnt/view-pdf-file?templateId=fdfd4581-1679-47df-a9bc-6b8f30e46700",
    "https://process5.gprocurement.go.th/egp-upload-service/v1/downloadFileTest?fileId=8850cf5fc54f4fe3b26d8f943647ce9f",
]
for u in URLS:
    for ua in ("Mozilla/5.0", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"):
        r = requests.get(u, headers={"User-Agent": ua}, timeout=60, allow_redirects=True)
        print(r.status_code, r.headers.get("Content-Type"), len(r.content), "| server:", r.headers.get("Server"),
              "| history:", [h.status_code for h in r.history], "| final:", r.url[:90])
        if len(r.content) < 2000:
            print("   body:", r.content[:600])
try:
    print("my ip:", requests.get("https://ipinfo.io/json", timeout=20).text[:300])
except Exception as e:
    print("ip lookup failed", e)
