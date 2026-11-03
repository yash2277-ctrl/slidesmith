import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide, est_lines
from _bh_specs import SPECS

T = themes.get_builtin("bauhaus")
T["dna"] = design.dna(20261006)
W, H = T["slide_w"], T["slide_h"]

def rotbox(el):
    x,y,w,h = el["x"],el["y"],el["w"],el["h"]
    rot = el.get("rot",0)
    if rot:
        a=math.radians(rot); cx,cy=x+w/2,y+h/2
        pts=[(x,y),(x+w,y),(x+w,y+h),(x,y+h)]
        pts=[(cx+(px-cx)*math.cos(a)-(py-cy)*math.sin(a), cy+(px-cx)*math.sin(a)+(py-cy)*math.cos(a)) for px,py in pts]
        x=min(p[0] for p in pts); y=min(p[1] for p in pts)
        w=max(p[0] for p in pts)-x; h=max(p[1] for p in pts)-y
    return x,y,w,h

def dump(spec, i=0, label=""):
    lay = layout_slide(spec, T, i, SPECS, "Audit")
    print(f"=== {label or spec.get('type')} ===  slide {W}x{H}  bg={lay['bg']}")
    for k, el in enumerate(lay["elements"]):
        x,y,w,h = rotbox(el)
        rot = el.get("rot",0)
        ln = el.get("line") if isinstance(el.get("line"), dict) else None
        lw = ln.get("width") if ln else None
        if el["t"]=="text":
            p0 = el["paras"][0]
            print(f"  [{k:2d}] TEXT  box=({el['x']:.3f},{el['y']:.3f},{el['w']:.3f},{el['h']:.3f}) rot={rot} "
                  f"size={p0['size']} cap={p0.get('caps')} fill={p0['color']} bottom={el['y']+el['h']:.3f} :: {p0['text'][:45]!r}")
        else:
            print(f"  [{k:2d}] {el['t']:8s} box=({x:.3f},{y:.3f},{w:.3f},{h:.3f}) raw=({el['x']:.3f},{el['y']:.3f},{el['w']:.3f},{el['h']:.3f}) "
                  f"rot={rot} fill={el.get('fill')} a={el.get('alpha',1)} line={lw} r={el.get("radius",0)} bleed={el.get('bleed')}")
    return lay

dump(SPECS[0], 0, "title sample")
dump(SPECS[-1], len(SPECS)-1, "closing sample")
