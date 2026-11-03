from server import layout as L
from server import themes, design
from server.raster import _font
TH = themes.get_builtin("bauhaus"); TH["dna"] = design.dna(20261006)

def real_h(el):
    ppi=96; tot=0
    for p in el["paras"]:
        px=max(4,int(p["size"]*ppi/72)); f=_font("outfit" if p.get("font")=="heading" else "body", bool(p.get("bold")), False, px)
        t=p["text"].upper() if p.get("caps") else p["text"]; mw=el["w"]*ppi
        lines,cur=[],""
        for w in (t or " ").split():
            tr=(cur+" "+w) if cur else w
            if f.getlength(tr)<=mw or not cur: cur=tr
            else: lines.append(cur); cur=w
        lines.append(cur); tot+=len(lines)*px/ppi*el.get("line",1.15)
    return tot

def audit(label,spec):
    lay=L.layout_slide(spec,TH,0,[spec],"Audit")
    fr=L.Frame(TH,"visual"); cy,ch=fr.content_rect()[1],fr.content_rect()[3]
    print("="*70); print(label)
    for i,e in enumerate(lay["elements"]):
        if e["t"]!="text" or e["y"]<4: continue
        b=e["y"]+e["h"]
        print(f"  [{i:2d}] x={e['x']:.3f} y={e['y']:.3f} w={e['w']:.3f} h={e['h']:.3f} right={e['x']+e['w']:.3f} bottom={b:.3f} est_need={L.text_h(e['paras'][0]['text'],e['paras'][0]['size'],e['w'],'body',e['line']):.3f} realH={real_h(e):.3f}")
    print(f"  content bottom={cy+ch:.3f}  footer text top=7.000  footer square top=6.980  last-col right={max(e['x']+e['w'] for e in lay['elements'] if e['t']=='text' and e['y']>4):.3f}")
    # does any body text box collide with the footer page-number square (x>=12.283, y>=6.98)?
    for e in lay["elements"]:
        if e["t"]=="text" and e["y"]>4:
            ox=min(e["x"]+e["w"],12.583)-max(e["x"],12.283); oy=min(e["y"]+e["h"],7.280)-max(e["y"],6.980)
            if ox>0.01 and oy>0.01: print(f"  !! COLLIDE with footer page square: box right={e['x']+e['w']:.3f} bottom={e['y']+e['h']:.3f} overlap {ox:.3f}x{oy:.3f}")
    return lay

# realistic long LLM step text, 6 steps
long_txt=("Interview every stakeholder across design, engineering and support and log the raw material in one shared "
 "place so that nothing whatsoever gets lost between the notes and the eventual deliverable, then circulate the "
 "summary for comment before the kickoff meeting so that everyone starts from the same set of facts.")
audit("6 steps, 300-char bodies", {"type":"process","title":"End to end","steps":[{"heading":f"Step {i}","text":long_txt} for i in range(1,7)]})
audit("6 steps, 380-char bodies", {"type":"process","title":"End to end","steps":[{"heading":f"Step {i}","text":long_txt*2} for i in range(1,7)]})
audit("7 steps", {"type":"process","title":"Seven steps here","steps":[{"heading":f"Step {i}","text":"Some body copy for this step."} for i in range(1,8)]})
