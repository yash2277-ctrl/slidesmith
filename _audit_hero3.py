import sys, math, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design, raster as R
from server.layout import layout_slide, est_lines, fit_size
from _bh_specs import SPECS
T=themes.get_builtin("bauhaus"); T["dna"]=design.dna(20261006)

CASES = {
 "sample": SPECS[0],
 "long-title": {"type":"title","kicker":"Form follows function and honest construction","title":"Bauhaus Design System And The Complete Constructivist Visual Language Handbook Volume Two","subtitle":"Geometry, primary colour and honest construction for modern presentation decks of considerable length and description"},
 "verylong": {"type":"title","kicker":"K","title":"The Comprehensive And Exhaustive Guide To Constructivist Modernism And Every Aspect Of Geometric Abstraction For Decks","subtitle":"x"},
}
for label, spec in CASES.items():
    lay = layout_slide(spec, T, 0, SPECS, "Audit")
    png = R.render_png(lay, T, ppi=96)
    print(label, "-> raster issues:", getattr(R, "_LAST", None))
# re-implement: capture issues
import inspect
src = inspect.getsource(R.render_png)
print(src[:1200])
