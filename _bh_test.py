"""Offline check for the Bauhaus theme: lays out one slide of every type,
renders PNGs (the same raster the AI reviewer sees) and exports a real .pptx.
Run:  python _bh_test.py   ->  data/_bh_preview/
"""
import shutil
from pathlib import Path

from server import themes, design
from server.layout import layout_slide
from server.renderer import build_pptx
from server.raster import render_png
from server.slide_schema import normalize

OUT = Path("data/_bh_preview")
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)

theme = themes.get_builtin("bauhaus")
theme["dna"] = design.dna(20261006)

DECK_TITLE = "Bauhaus Design System"

from _bh_specs import SPECS



for i, spec in enumerate(SPECS):
    layout = layout_slide(spec, theme, i, SPECS, DECK_TITLE)
    png = render_png(layout, theme, ppi=96)
    (OUT / f"slide_{i + 1:02d}_{spec['type']}.png").write_bytes(png)
    print(f"slide {i + 1:02d} {spec['type']}: {len(png) // 1024} KB")

out_pptx = OUT / "bauhaus_test.pptx"
build_pptx([{"spec": s} for s in SPECS], theme, DECK_TITLE, out_pptx)
print(f"\npptx: {out_pptx} ({out_pptx.stat().st_size // 1024} KB)")
