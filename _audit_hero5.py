import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide
from server.template_analyzer import contrast
from server.raster import _font
from _bh_specs import SPECS
T=themes.get_builtin("bauhaus"); T["dna"]=design.dna(20261006)
W,H=T["slide_w"],T["slide_h"]

def real_h(el):
    tot=0
    for p in el["paras"]:
        px=max(4,int(p["size"]*96/72))
        f=_font("outfit" if p.get("font")=="heading" else "body", bool(p.get("bold")), bool(p.get("italic")), px)
        txt=p["text"].upper() if p.get("caps") else p["text"]
        mx=el["w"]*96; lines,cur=[],""
        for w_ in txt.split():
            tr=(cur+" "+w_) if cur else w_
            if f.getlength(tr)<=mx or not cur: cur=tr
            else: lines.append(cur); cur=w_
        lines.append(cur)
        tot+=len(lines)*px/96*el.get("line",1.15)
    return tot

CASES={
 "sample": SPECS[0],
 "long-title": {"type":"title","kicker":"Form follows function and honest construction","title":"Bauhaus Design System And The Complete Constructivist Visual Language Handbook Volume Two","subtitle":"Geometry, primary colour and honest construction for modern presentation decks of considerable length and description"},
 "verylong": {"type":"title","kicker":"K","title":"The Comprehensive And Exhaustive Guide To Constructivist Modernism And Every Aspect Of Geometric Abstraction For Decks","subtitle":"x"},
}
for label,spec in CASES.items():
    lay=layout_slide(spec,T,0,SPECS,"Audit")
    texts=[e for e in lay["elements"] if e["t"]=="text"]
    print(f"\n--- {label} ---")
    for i in range(len(texts)-1):
        a,b=texts[i],texts[i+1]
        ab=a["y"]+real_h(a); print(f"  {a['paras'][0]['text'][:25]!r} real_bottom={ab:.3f} vs next '{b['paras'][0]['text'][:20]!r}' y={b['y']:.3f} -> {'OVERLAP %.3f in'%(b['y']-ab) if ab>b['y'] else 'ok gap %.3f'%(b['y']-ab)}")
    t=texts[-1]; print(f"  last bottom real={t['y']+real_h(t):.3f}")

print("\n--- contrast of hero text on off-white #F0F0F0 ---")
lay=layout_slide(SPECS[0],T,0,SPECS,"Audit")
for e in lay["elements"]:
    if e["t"]=="text":
        p=e["paras"][0]
        print(f"  {p['size']}pt {p['color']} on #F0F0F0 -> contrast {contrast(p['color'],'#F0F0F0'):.2f}")
print("\npalette is strictly: ", T["colors"])
