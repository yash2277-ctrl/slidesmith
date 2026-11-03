"""Instrument the real raster.table() to capture exactly what the PNG gets per cell,
and compare with what the HTML canvas and the PPTX write."""
from PIL import ImageDraw
from server.layout import layout_slide, est_lines
from server.themes import get_builtin
from server import raster, renderer
import zipfile, re

THEME = get_builtin("bauhaus")
spec = {"type": "table", "title": "Token sheet", "columns": ["Token", "Value", "Use"],
        "rows": [["surface / elevated background", "#FFFFFF",
                  "Card fills and any raised panel that sits on the off-white canvas"],
                 ["primary-red", "#D02020", "Action"]]}
lay = layout_slide(spec, THEME, 0, [spec], "Audit")
te = [e for e in lay["elements"] if e["t"] == "table"][0]

captured = []
orig = ImageDraw.ImageDraw.text
def spy(self, xy, txt, *a, **k):
    captured.append((round(xy[1]), txt))
    return orig(self, xy, txt, *a, **k)
ImageDraw.ImageDraw.text = spy
raster.render_png(lay, THEME, 72)
ImageDraw.ImageDraw.text = orig

te_top_px = None
print("raster row box:", te["y"], "h", te["h"], "row_h", te["h"]/(len(te["rows"])+1))
print("text actually painted into the PNG (y, string):")
for y, t in captured:
    print(f"   y={y:4d}  {t!r}")

print()
print("full cell value in the display list:", repr(te["rows"][0][2]))
print("lines HTML/PPTX will lay out at size", te["size"], ":",
      est_lines(te["rows"][0][2], te["size"], te["w"]/3, "body"))

w = renderer.Writer(THEME, None)
import pathlib
w.add(lay, "")
w.save(pathlib.Path("_t_probe.pptx"))
xml = zipfile.ZipFile("_t_probe.pptx").read("ppt/slides/slide1.xml").decode()
print()
print("text stored in the PPTX cells:", re.findall(r'<a:t>([^<]*)</a:t>', xml))
print("PPTX word_wrap:", set(re.findall(r'<a:bodyPr[^>]*wrap="(\w+)"', xml)))
print("PPTX reserved row heights (in):", [round(int(h)/914400, 3) for h in re.findall(r'<a:tr h="(\d+)"', xml)])