"""End-to-end test against the running server: create a project with the Bauhaus
theme, let the real AI build a deck, then export the .pptx and fetch a slide PNG.

Usage:  python _e2e_test.py [base_url] [prompt]
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8021").rstrip("/")
PROMPT = sys.argv[2] if len(sys.argv) > 2 else (
    "Create a 6-slide deck on the history of the Bauhaus school, in the Bauhaus style. "
    "Use section, bullets, cards, stats, timeline and a closing slide.")
OUT = Path("data/_e2e")
OUT.mkdir(parents=True, exist_ok=True)


def api(path, data=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=body, method=method or ("POST" if body else "GET"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw and raw[:1] in b"[{" else raw


t0 = time.time()
status = api("/api/status")
print(f"1. server      : demo={status['demo']} model={status['model']} key={status['has_key']}")

themes = api("/api/themes")["themes"]
bh = next((t for t in themes if t["theme_id"] == "bauhaus"), None)
print(f"2. theme api   : bauhaus present={bool(bh)} previews={len(bh['previews']) if bh else 0}")

proj = api("/api/projects", {"name": "E2E Bauhaus", "theme_id": "bauhaus"})
pid = proj["id"]
print(f"3. project     : {pid} theme={proj['theme_id']}")

boundary = "----slidemith"
payload = urllib.parse.urlencode({"text": PROMPT, "selected": "[]"}).encode()
req = urllib.request.Request(f"{BASE}/api/projects/{pid}/chat", data=payload,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
slides_done = 0
print("4. generating  : ", end="", flush=True)
with urllib.request.urlopen(req, timeout=1800) as resp:
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        try:
            ev = json.loads(line[5:])
        except ValueError:
            continue
        if ev.get("type") == "slide" and ev.get("slide", {}).get("status") == "done":
            slides_done += 1
            print(f"[slide {slides_done}]", end=" ", flush=True)
        if ev.get("type") == "error":
            print(f"\n   ! {ev.get('message')}")
        if ev.get("type") == "done":
            break
print()

view = api(f"/api/projects/{pid}")
specs = [s["spec"]["type"] for s in view["slides"]]
print(f"5. deck built  : {len(view['slides'])} slides in {time.time() - t0:.0f}s -> {', '.join(specs)}")

png_url = f"{BASE}/api/projects/{pid}/slides/{view['slides'][0]['id']}.png"
with urllib.request.urlopen(png_url, timeout=120) as r:
    png = r.read()
    checks = r.headers.get("X-Slide-Checks", "")
(OUT / "slide1.png").write_bytes(png)
print(f"6. slide png   : {len(png) // 1024} KB  reviewer checks: {checks or 'none'}")

pptx_url = f"{BASE}/api/projects/{pid}/export"
with urllib.request.urlopen(pptx_url, timeout=300) as r:
    pptx = r.read()
(OUT / "deck.pptx").write_bytes(pptx)
print(f"7. export      : {len(pptx) // 1024} KB -> data/_e2e/deck.pptx")

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
prs = Presentation(str(OUT / "deck.pptx"))
shapes = sum(len(s.shapes) for s in prs.slides)
tri = sum(1 for s in prs.slides for sh in s.shapes
          if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and "TRIANGLE" in str(getattr(sh, "auto_shape_type", "")))
rot = sum(1 for s in prs.slides for sh in s.shapes if getattr(sh, "rotation", 0))
outl = sum(1 for s in prs.slides for sh in s.shapes
           if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and sh.line.width and sh.line.width.pt >= 1.5)
print(f"8. pptx verify : {len(prs.slides)} slides · {shapes} shapes · {tri} triangles · {rot} rotated · {outl} outlined")
print(f"\nRESULT: {'PASS' if slides_done and len(prs.slides) == slides_done else 'CHECK ABOVE'}  ({time.time() - t0:.0f}s total)")
