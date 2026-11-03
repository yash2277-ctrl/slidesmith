"""Render the bauhaus table slide three ways and compare the artefacts."""
import io, re, zipfile
from pathlib import Path
from PIL import Image
from _bh_specs import SPECS
from server.layout import layout_slide
from server.themes import get_builtin
from server import raster, renderer

THEME = get_builtin("bauhaus")
SAMPLE = next(s for s in SPECS if s["type"] == "table")

LONG = {"type": "table", "title": "Token sheet",
        "columns": ["Design token name", "Resolved value", "Where it is applied"],
        "rows": [["surface / elevated background", "#FFFFFF",
                  "Card fills and any raised panel that sits on the off-white canvas"],
                 ["border / heavy structural stroke", "#121212 at 2.75pt",
                  "Every card edge in the deck, drawn as a solid rule"],
                 ["shadow / hard offset", "#121212 offset 0.08in",
                  "Depth cue behind every card, never blurred"],
                 ["radius / corner treatment", "0 or full circle",
                  "Constructivist geometry only, no rounded rectangles anywhere"],
                 ["type / heading", "Outfit ExtraBold uppercase",
                  "Headlines, tracked tight at -0.5 points"]]}

for name, spec in (("SAMPLE", SAMPLE), ("LONG", LONG)):
    lay = layout_slide(spec, THEME, 0, [spec], "Audit")
    png = raster.render_png(lay, THEME, 72)
    Path(f"_t_{name}.png").write_bytes(png)
    im = Image.open(io.BytesIO(png)).convert("RGB")
    s = im.width / lay["w"]
    te = [e for e in lay["elements"] if e["t"] == "table"][0]
    px, py, pw, ph = int(te["x"]*s), int(te["y"]*s), int(te["w"]*s), int(te["h"]*s)
    rh = ph/(len(te["rows"])+1)
    print(f"--- {name}  png {im.size}  table box px x[{px},{px+pw}] y[{py},{py+ph}] row_h={rh:.1f}px")
    for label, yy in (("header/row1 boundary", int(te["y"]*s + rh)),
                      ("row1/row2 boundary", int(te["y"]*s + 2*rh)),
                      ("mid row 1", int(te["y"]*s + 1.5*rh)),
                      ("mid header", int(te["y"]*s + 0.5*rh))):
        dark = [x for x in range(px, px+pw) if sum(im.getpixel((x, yy))) < 260]
        print(f"   {label:22s} y={yy} dark px={len(dark):4d} first few={dark[:6]}")
    # vertical scan inside the header to find the header band
    ycol = int(te["y"]*s + 0.5*rh)
    print("   header pixel:", im.getpixel((px + 5, ycol)))
    y1 = int(te["y"]*s + 1.5*rh)
    print("   row1 pixel :", im.getpixel((px + 5, y1)), " row2 pixel:", im.getpixel((px + 5, int(te["y"]*s + 2.5*rh))))

    w = renderer.Writer(THEME, None)
    w.add(lay, "")
    w.save(Path(f"_t_{name}.pptx"))
    xml = zipfile.ZipFile(f"_t_{name}.pptx").read("ppt/slides/slide1.xml").decode()
    print("   pptx tableStyleId:", re.findall(r'<a:tableStyleId>([^<]*)', xml))
    print("   pptx tblPr:", re.findall(r'<a:tblPr[^>]*/?>', xml))
    print("   pptx cell border tags (lnL/lnR/lnT/lnB):", sorted(set(re.findall(r'<a:(lnL|lnR|lnT|lnB)[ />]', xml))))
    print("   pptx row heights (in):", [round(int(h)/914400, 3) for h in re.findall(r'<a:tr h="(\d+)"', xml)])
    print("   pptx col widths (in):", [round(int(h)/914400, 3) for h in re.findall(r'<a:gridCol w="(\d+)"', xml)])
    print("   pptx graphicFrame off/ext:", re.findall(r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(\d+)" cy="(\d+)"', xml))