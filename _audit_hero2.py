import sys, math, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image
from server import themes, design
from server.layout import layout_slide
from server.raster import render_png, _font
from _bh_specs import SPECS

T = themes.get_builtin("bauhaus"); T["dna"] = design.dna(20261006)
W, H = T["slide_w"], T["slide_h"]

def measure(lay):
    out=[]
    for el in lay["elements"]:
        if el["t"]!="text": continue
        ppi=96; total=0.0; nl=0
        for p in el["paras"]:
            px=max(4,int(p["size"]*ppi/72))
            face = "outfit" if p.get("font")=="heading" else "body"
            f=_font(face, bool(p.get("bold")), bool(p.get("italic")), px)
            text=p["text"].upper() if p.get("caps") else p["text"]
            maxw=(el["w"]-0.35*p.get("level",0))*ppi
            lines,cur=[],""
            for word in (text or " ").split():
                trial=(cur+" "+word) if cur else word
                if f.getlength(trial)<=maxw or not cur: cur=trial
                else: lines.append(cur); cur=word
            lines.append(cur); nl+=len(lines)
            total+=len(lines)*px/ppi*el.get("line",1.15)
        out.append((el,total,nl))
    return out

CASES = {
 "sample": SPECS[0],
 "long-title": {"type":"title","kicker":"Form follows function and honest construction","title":"Bauhaus Design System And The Complete Constructivist Visual Language Handbook Volume Two","subtitle":"Geometry, primary colour and honest construction for modern presentation decks of considerable length and description"},
 "verylong-title": {"type":"title","kicker":"K","title":"The Comprehensive And Exhaustive Guide To Constructivist Modernism And Every Aspect Of Geometric Abstraction For Decks","subtitle":"x"},
 "no-sub": {"type":"title","title":"Short Title","kicker":"K","contact":"hello@x.com"},
 "no-kicker-long": {"type":"title","title":"A Moderately Long Presentation Title That Runs Across Two Or Three Lines Here","subtitle":"A subtitle of medium length that will likely occupy two lines of body copy."},
 "contact": {"type":"title","kicker":"Launch","title":"Spring Programme","subtitle":"Twelve sessions on typography and poster craft across the spring term","contact":"programme@bauhaus.example"},
}
for label, spec in CASES.items():
    lay = layout_slide(spec, T, 0, SPECS, "Audit")
    print(f"\n=== {label} ===")
    for el,total,nl in measure(lay):
        p0=el["paras"][0]
        flag = "  <== OVERFLOW %.0f%%" % ((total/el["h"]-1)*100) if total > el["h"]*1.10 else ""
        print(f"  TEXT y={el['y']:.3f} h={el['h']:.3f} w={el['w']:.3f} measured={total:.3f} lines={nl} size={p0['size']} bottom={el['y']+el['h']:.3f} {p0['text'][:40]!r}{flag}")
    for el in lay["elements"]:
        if el["t"]=="text" and el["y"]+max(el["h"],0)<0: print("   negative y")
    ys=[(el["y"],el["y"]+el["h"]) for el in lay["elements"]]
    print("   max bottom:", round(max(b for a,b in ys),3), "slide H:", H)
    # off-slide check for text
    for el in lay["elements"]:
        if el["t"]=="text" and (el["y"]<0 or el["y"]+el["h"]>H or el["x"]+el["w"]>W):
            print(f"   OFFSLIDE text x={el['x']:.2f} y={el['y']:.2f} r={el['x']+el['w']:.2f} b={el['y']+el['h']:.2f} :: {el['paras'][0]['text'][:40]!r}")
