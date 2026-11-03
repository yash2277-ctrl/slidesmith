"""Audit: shared chrome + decorations for the Bauhaus theme."""
import math, sys, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image
from server import themes, design
from server.layout import layout_slide, est_lines, text_h
from server.raster import render_png, _font
from _bh_specs import SPECS

THEME = themes.get_builtin("bauhaus")
THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]
print("theme style:", THEME.get("style"), "dna:", "yes")

def rbox(el):
    x,y,w,h = el["x"],el["y"],el["w"],el["h"]
    rot = el.get("rot",0)
    if rot and el["t"] in ("rect","triangle"):
        a=math.radians(rot); cx,cy=x+w/2,y+h/2
        pts=[(cx+(px-cx)*math.cos(a)-(py-cy)*math.sin(a), cy+(px-cx)*math.sin(a)+(py-cy)*math.cos(a))
             for px,py in ((x,y),(x+w,y),(x+w,y+h),(x,y+h))]
        X0=min(p[0] for p in pts); Y0=min(p[1] for p in pts)
        return X0,Y0,max(p[0] for p in pts)-X0,max(p[1] for p in pts)-Y0
    return x,y,w,h

def overlap(a,b):
    ax,ay,aw,ah=a; bx,by,bw,bh=b
    ix=min(ax+aw,bx+bw)-max(ax,bx); iy=min(ay+ah,by+bh)-max(ay,by)
    return (ix,iy) if ix>1e-6 and iy>1e-6 else None

def txt_h(el):
    """measured wrapped height, inches, real Outfit font @96dpi"""
    tot=0.0
    for p in el["paras"]:
        px=max(4,int(p["size"]*96/72))
        face="outfit" if p.get("font")=="heading" else "outfit"
        f=_font(face,bool(p.get("bold")),bool(p.get("italic")),px)
        t=p["text"].upper() if p.get("caps") else p["text"]
        ind=0.35*p.get("level",0)+(px*1.1/96 if p.get("bullet") else 0)
        mx=(el["w"]-ind)*96
        ls,cur=[],""
        sp=p.get("spacing",0)*96/72
        for w in (t or " ").split():
            tr=(cur+" "+w) if cur else w
            if f.getlength(tr)+sp*len(tr)<=mx or not cur: cur=tr
            else: ls.append(cur); cur=w
        ls.append(cur)
        tot+=len(ls)*px/96*el.get("line",1.15)+p.get("space",0)/72
    return tot

for i,spec in enumerate(SPECS):
    lay=layout_slide(spec,THEME,i,SPECS,"Audit")
    els=lay["elements"]
    print(f"\n=== slide {i+1} [{spec['type']}] bg={lay['bg']} els={len(els)}")
    # decorations first (they are pushed first)
    for e in els[:8]:
        bx=rbox(e)
        print(f"   {e['t']:8s} ({e['x']:.3f},{e['y']:.3f}) {e['w']:.3f}x{e['h']:.3f} rot={e.get('rot',0)} fill={e.get('fill')} line={e.get('line')}")
    chrome=[e for e in els if e["t"]=="text"]
    # report chrome text boxes (kicker/title/footer) plus overflow
    for e in els:
        if e["t"]!="text": continue
        m=txt_h(e)
        if m>e["h"]*1.10 and any(p["text"].strip() for p in e["paras"]):
            print(f"   OVERFLOW {int((m/e['h']-1)*100)}%: box h={e['h']:.2f} measured={m:.2f} y={e['y']:.2f} w={e['w']:.2f} :: {e['paras'][0]['text'][:50]!r}")
    # overlap among text boxes
    tb=[(e,rbox(e)) for e in els if e["t"]=="text"]
    for a in range(len(tb)):
        for b in range(a+1,len(tb)):
            ov=overlap(tb[a][1],tb[b][1])
            if ov:
                print(f"   TEXTBOX-OVERLAP {ov[0]:.2f}x{ov[1]:.2f}in : {tb[a][0]['paras'][0]['text'][:26]!r} @({tb[a][0]['x']:.2f},{tb[a][0]['y']:.2f},{tb[a][0]['w']:.2f}x{tb[a][0]['h']:.2f}) vs {tb[b][0]['paras'][0]['text'][:26]!r} @({tb[b][0]['x']:.2f},{tb[b][0]['y']:.2f},{tb[b][0]['w']:.2f}x{tb[b][0]['h']:.2f})")
    # trio vs kicker/title/foot
    trio=[e for e in els if e["x"]>11.0 and e["y"]<1.2 and e["t"] in ("ellipse","rect","triangle")]
    for t in trio:
        for e in els:
            if e is t or e["t"]!="text": continue
            ov=overlap(rbox(t),rbox(e))
            if ov: print(f"   TRIO-OVERLAP {t['t']}@({t['x']:.2f},{t['y']:.2f},{t['w']:.2f}x{t['h']:.2f}) x {e['paras'][0]['text'][:24]!r} by {ov[0]:.2f}x{ov[1]:.2f}in")
    # bounds
    for e in els:
        x,y,w,h=rbox(e)
        if e.get("bleed"): continue
        if x<-0.01 or y<-0.01 or x+w>W+0.01 or y+h>H+0.01:
            print(f"   BOUNDS {e['t']} ({x:.2f},{y:.2f}) {w:.2f}x{h:.2f} -> right={x+w:.2f} bottom={y+h:.2f}")
