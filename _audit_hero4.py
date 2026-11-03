import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design, raster as R
from server.layout import layout_slide
from _bh_specs import SPECS
T=themes.get_builtin("bauhaus"); T["dna"]=design.dna(20261006)
CASES = {
 "sample": SPECS[0],
 "long-title": {"type":"title","kicker":"Form follows function and honest construction","title":"Bauhaus Design System And The Complete Constructivist Visual Language Handbook Volume Two","subtitle":"Geometry, primary colour and honest construction for modern presentation decks of considerable length and description"},
 "verylong": {"type":"title","kicker":"K","title":"The Comprehensive And Exhaustive Guide To Constructivist Modernism And Every Aspect Of Geometric Abstraction For Decks","subtitle":"x"},
}
for label, spec in CASES.items():
    lay = layout_slide(spec, T, 0, SPECS, "Audit")
    r = R.Raster(lay, T, ppi=96)
    r.render()
    print(f"{label}: {r.issues}")
