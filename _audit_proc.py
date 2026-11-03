import sys
from _bh_specs import SPECS
from server import layout as L
from server.themes import get_builtin
from server.raster import Raster

th = get_builtin("bauhaus")
print("dna:", th.get("dna"))

def audit(label, spec, deck_title="Audit"):
    out = L.layout_slide(spec, th, 0, [spec], deck_title)
    print("="*70)
    print(label, "| bg:", out.get("bg"))
    for i, el in enumerate(out["elements"]):
        g = {k: el.get(k) for k in ("t","geom","x","y","w","h","rot","radius","alpha","bleed") if k in el}
        line = el.get("line")
        extra = f" line={line}" if line else ""
        print(f"[{i:2d}] {g}{extra} fill={el.get('fill')}")
        if el["t"] == "text":
            for p in el["paras"]:
                print(f"       para size={p['size']} font={p['font']} bold={p.get('bold')} caps={p.get('caps')} sp={p.get('spacing')} color={p['color']} text={p['text'][:60]!r}")
            w = el["w"]; h = el["h"]
            need = 0.0
            for p in el["paras"]:
                need += L.text_h(p["text"], p["size"], w, p["font"], el["line"]) + p["size"]/72*p.get("space",0.0)
            print(f"       measured={need:.3f} box_h={h:.3f} {'OVERFLOW +%.3f'%(need-h) if need>h else 'ok (slack %.3f)'%(h-need)}")
    return out

sp = next(s for s in SPECS if s["type"]=="process")
audit("SAMPLE process (4 steps)", sp)
