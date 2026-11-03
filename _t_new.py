"""Quick check that the new document + diagram slide types render everywhere."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from server import themes, store
from server.layout import layout_slide
from server.raster import inspect, render_png
from server.renderer import build_pptx
from server.slide_schema import normalize, validate

theme = {**themes.get_builtin("midnight"), "dna": {}}


def check(name, raw, theme):
    spec = normalize(raw)
    err = validate(spec)
    lay = layout_slide(spec, theme, 0, [spec], "Test deck")
    png, issues = inspect(lay, spec, theme)
    Path(f"_t_{name}.png").write_bytes(png)
    types = {}
    for el in lay["elements"]:
        types[el["t"]] = types.get(el["t"], 0) + 1
    print(f"{name}: err={err} issues={issues} els={types}")
    return spec, lay


doc = {"type": "document", "title": "Offer letter", "doc": "#D1", "pages": [1], "caption": "CodeAlpha offer letter"}
dia = {"type": "diagram", "title": "How the app is built", "caption": "Three tiers, requests flow down and data flows back",
       "nodes": [{"label": "Browser", "text": "React SPA", "icon": "mdi:monitor"},
                 {"label": "API", "text": "Express routes", "icon": "mdi:server"},
                 {"label": "Auth", "text": "JWT check", "icon": "mdi:shield-lock"},
                 {"label": "Database", "text": "MongoDB", "icon": "mdi:database"}],
       "edges": [{"from": 0, "to": 1, "label": "HTTPS"}, {"from": 1, "to": 2, "label": "verify"},
                 {"from": 2, "to": 3, "label": "query"}]}

for theme_id in ("midnight", "bauhaus", "clean"):
    th = {**themes.get_builtin(theme_id), "dna": {}}
    s1, l1 = check(f"doc_{theme_id}", doc, th)
    s2, l2 = check(f"dia_{theme_id}", dia, th)
    out = Path(f"_t_{theme_id}.pptx")
    build_pptx([{"spec": s1, "status": "done"}, {"spec": s2, "status": "done"}], th, "Test deck", out)
    print(f"  -> pptx {out} {out.stat().st_size} bytes")
print("OK")