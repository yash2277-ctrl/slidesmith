"""Real-font wrapped-height check (same method as _bh_check.check_text_fit) plus
geometry checks, for _bh_process at several scales."""
from server import layout as L
from server import themes, design
from server.raster import _font, render_png
from _bh_specs import SPECS
import io
from PIL import Image

TH = themes.get_builtin("bauhaus")
TH["dna"] = design.dna(20261006)   # same as _bh_check.py so decor/dna path is exercised

def real_text_h(el):
    ppi = 96; total = 0.0; info=[]
    for p in el["paras"]:
        px = max(4, int(p["size"] * ppi / 72))
        face = "outfit" if p.get("font") == "heading" else "body"
        font = _font(face, bool(p.get("bold")), bool(p.get("italic")), px)
        text = p["text"].upper() if p.get("caps") else p["text"]
        max_w = el["w"] * ppi
        lines, cur = [], ""
        for word in (text or " ").split():
            t = (cur+" "+word) if cur else word
            if font.getlength(t) <= max_w or not cur: cur = t
            else: lines.append(cur); cur = word
        lines.append(cur)
        total += len(lines)*px/ppi*el.get("line",1.15)
        info.append((p["text"][:34], p["size"], len(lines), round(max_w/font.getlength("M"*20),1)))
    return total, info

def audit(label, spec, idx=0):
    lay = L.layout_slide(spec, TH, idx, [spec], "Audit")
    W,H = TH["slide_w"], TH["slide_h"]
    fr = L.Frame(TH, "visual"); cx,cy,cw,ch = fr.content_rect()
    print("="*76); print(label)
    print(f"  content_rect x={cx:.3f} y={cy:.3f} w={cw:.3f} h={ch:.3f}  bottom={cy+ch:.3f}")
    shapes=[e for e in lay["elements"] if e["t"] in ("shape","rect","ellipse","triangle","text")]
    for i,el in enumerate(lay["elements"]):
        r,b = el["x"]+el["w"], el["y"]+el["h"]
        flags=[]
        if el["x"]<-0.01 or el["y"]<-0.01 or r>W+0.01 or b>H+0.01: flags.append("OFF-SLIDE")
        if el["t"]=="text" and b>cy+ch+0.01: flags.append(f"BELOW-CONTENT-RECT(+{b-(cy+ch):.3f})")
        if el["t"]=="text":
            need,info = real_text_h(el)
            if need > el["h"]*1.10: flags.append(f"TEXT-OVERFLOW {need:.3f}>{el['h']:.3f} (+{need-el['h']:.3f})")
            print(f"  [{i:2d}] text x={el['x']:.3f} y={el['y']:.3f} w={el['w']:.3f} h={el['h']:.3f} bottom={b:.3f} realH={need:.3f} {info} {' '.join(flags)}")
        else:
            print(f"  [{i:2d}] {el['t']:7s} geom={el.get('geom')} x={el['x']:.3f} y={el['y']:.3f} w={el['w']:.3f} h={el['h']:.3f} right={r:.3f} bottom={b:.3f} fill={el.get('fill')} line={el.get('line')} {' '.join(flags)}")
    # text vs text overlap, and content vs footer overlap
    ft=[e for e in lay["elements"] if e["t"]=="text" and e["y"]>6.5]
    for e in shapes:
        for f in ft:
            ox=min(e["x"]+e["w"],f["x"]+f["w"])-max(e["x"],f["x"]); oy=min(e["y"]+e["h"],f["y"]+f["h"])-max(e["y"],f["y"])
            if ox>0.01 and oy>0.01: print(f"   !! HIT footer el ({e['t']},y={e['y']:.3f}) x footer text y={f['y']:.3f} overlap {ox:.3f}x{oy:.3f}")
    png = render_png(lay, TH, ppi=96)
    return lay

sample = next(s for s in SPECS if s["type"]=="process")
audit("SPECS process (4 steps)", sample, [s["type"] for s in SPECS].index("process"))
audit("6 steps, medium text", {"type":"process","title":"A six step workflow for the whole team","steps":[
 {"heading":"Discovery","text":"Interview every stakeholder and log the raw material in one shared place so nothing gets lost."},
 {"heading":"Framing","text":"Write the problem in a single sentence that a designer and an engineer will both agree with."},
 {"heading":"Composition","text":"Block out the grid with pure geometry before a single word is chosen for the page."},
 {"heading":"Colour","text":"Fill the panels with the three primaries and keep black and white carrying the hierarchy."},
 {"heading":"Type","text":"Set the headline heavy and tight, then open the tracking on every small label on the slide."},
 {"heading":"Release","text":"Export the deck, check it against the preview and ship it to the people who asked for it."}]})
audit("6 steps, very long text", {"type":"process","title":"A six step workflow","steps":[
 {"heading":"Discovery and stakeholder interviews","text":"Interview every single stakeholder across design, engineering, support and sales, then log all of the raw material in one shared place so that nothing whatsoever gets lost between the notes and the eventual deliverable."},
 {"heading":"Framing","text":"Write the problem down in a single sentence that a designer and an engineer will both agree with, and keep that sentence visible on the wall for the entire length of the engagement."},
 {"heading":"Composition","text":"Block out the grid with pure geometry before a single word is chosen, checking the balance from across the room."},
 {"heading":"Colour","text":"Fill the panels with the three primaries and let black and white carry the rest of the hierarchy without gradients."},
 {"heading":"Typography","text":"Set the headline heavy and tightly tracked, then open the tracking right out on every small label."},
 {"heading":"Release","text":"Export the deck, check the exported file against the live preview, fix anything that moved, then ship it."}]})
audit("6 steps, very long headings", {"type":"process","title":"Long headings","steps":[
 {"heading":"Discovery and stakeholder interviews","text":"Short."},
 {"heading":"Framing the problem statement","text":"Short."},
 {"heading":"Composition of the grid","text":"Short."},
 {"heading":"Colour application rules","text":"Short."},
 {"heading":"Typography decisions","text":"Short."},
 {"heading":"Release and review","text":"Short."}]})
