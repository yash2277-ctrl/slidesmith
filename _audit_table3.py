"""Stress: row-count sweep + raster truncation parity check."""
from _bh_specs import SPECS
from server.layout import layout_slide, text_h
from server.themes import get_builtin
from server import raster

THEME = get_builtin("bauhaus")
SAMPLE = next(s for s in SPECS if s["type"] == "table")
CONTENT_TOP, CONTENT_BOT = 1.95, 1.95 + 4.70
FOOTER_TOP = 7.00

print("=== row-count sweep (3 cols, short cells) ===")
for n in range(5, 15):
    rows = [[f"token-{i:02d}", "#D02020", "Action"] for i in range(n)]
    spec = {"type": "table", "title": "Token sheet", "columns": ["Token", "Value", "Use"], "rows": rows}
    lay = layout_slide(spec, THEME, 0, [spec], "Audit")
    te = [e for e in lay["elements"] if e["t"] == "table"][0]
    bot = te["y"] + te["h"]
    flag = ""
    if te["y"] < CONTENT_TOP - 1e-6:
        flag += " TOP-ABOVE-CONTENT-RECT"
    if bot > CONTENT_BOT + 1e-6:
        flag += " PAST-CONTENT-RECT"
    if bot > FOOTER_TOP:
        flag += f" OVERLAPS-FOOTER (footer top {FOOTER_TOP}, need +{bot-FOOTER_TOP:.2f}in)"
    if bot > 7.5:
        flag += " OFF-SLIDE"
    print(f" rows={n:2d} size={te['size']:2d} top={te['y']:.3f} h={te['h']:.3f} bottom={bot:.3f}"
          f"  cell_text_h={text_h('token-01', te['size'], te['w']/3):.3f}{flag}")

print()
print("=== single-cell-too-wide: what each renderer does ===")
VALS = ["A very long descriptive value that is wider than one table column at the shipped size"]
spec = {"type": "table", "title": "Token sheet", "columns": ["Token", "Value", "Use"],
        "rows": [[VALS[0], "#D02020", "Action"]]}
lay = layout_slide(spec, THEME, 0, [spec], "Audit")
te = [e for e in lay["elements"] if e["t"] == "table"][0]
r = raster.Raster(lay, THEME, 72)
cw_px = r.px(te["w"]) / 3
font = raster._font(r._face({"face": te.get("face")}), False, False, int(te["size"] * 72 / 72))
print(f" cell_w_px={cw_px:.1f}  font px size={int(te['size']*72/72)}")
for row in [te["columns"]] + te["rows"]:
    for v in row:
        w = font.getlength(v)
        trunc = not (w < cw_px - 10)
        cut = v[: max(3, int(len(v) * (cw_px - 10) / max(w, 1)) - 1)] + "…" if trunc else v
        from server.layout import est_lines
        print(f"  {v[:46]!r:50s} w={w:7.1f}px  raster={'TRUNC-> ' + cut[-24:] if trunc else 'full'}"
              f"  html/pptx lines={est_lines(v, te['size'], te['w']/3, 'body')}")

print()
print("=== does the HTML preview uppercase the header? (source) ===")
import re, pathlib
js = pathlib.Path("web/slides.js").read_text(encoding="utf8")
line = js.splitlines()[233]
print(" slides.js:234 ->", line.strip())
css = pathlib.Path("web/styles.css").read_text(encoding="utf8")
print(" styles.css has 'text-transform':", "text-transform" in css,
      "| th rules:", re.findall(r'[^\n{]*\bth\b[^\n{]*\{[^}]*\}', css)[:3])