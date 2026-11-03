from server import layout as L
from server.themes import get_builtin
th = get_builtin("bauhaus")

def dump(label, spec):
    out = L.layout_slide(spec, th, 0, [spec], "Audit")
    print("="*72); print(label)
    print("  slide 13.333 x 7.5; content_rect =", [round(v,3) for v in L.Frame(th, "visual").content_rect()])
    worst = None
    for i, el in enumerate(out["elements"]):
        r = el["x"]+el["w"]; b = el["y"]+el["h"]
        tag = ""
        if el["x"] < -1e-9 or el["y"] < -1e-9 or r > 13.333+1e-9 or b > 7.5+1e-9: tag += " OFF-SLIDE"
        if el["t"]=="text":
            need = sum(L.text_h(p["text"], p["size"], el["w"], p["font"], el["line"]) for p in el["paras"])
            if need > el["h"]+1e-9: tag += f" TEXT-OVERFLOW +{need-el['h']:.3f}"
            if b > 7.0 and not el.get("static"): tag += " BELOW-FOOTER"
        if el["t"] in ("shape","rect","ellipse","triangle"):
            if b > 6.98: tag += " SHAPE-IN-FOOTER"
        print(f"  [{i:2d}] {el['t']:8s} geom={el.get('geom')} x={el['x']:.3f} y={el['y']:.3f} w={el['w']:.3f} h={el['h']:.3f} right={r:.3f} bottom={b:.3f}{tag}")
    # text/text overlaps
    ts = [e for e in out["elements"] if e["t"]=="text"]
    for a in range(len(ts)):
        for bb in range(a+1, len(ts)):
            A,B = ts[a], ts[bb]
            ox = min(A["x"]+A["w"],B["x"]+B["w"]) - max(A["x"],B["x"])
            oy = min(A["y"]+A["h"],B["y"]+B["h"]) - max(A["y"],B["y"])
            if ox > 0.01 and oy > 0.01:
                print(f"   OVERLAP text[{A['paras'][0]['text'][:18]}] x text[{B['paras'][0]['text'][:18]}] = {ox:.3f}x{oy:.3f}")
    return out

# 6 steps, long text
dump("6 steps, long body", {"type":"process","title":"A six step workflow for the whole team","steps":[
 {"heading":"Discovery","text":"Interview every stakeholder and log the raw material in one shared place so nothing gets lost."},
 {"heading":"Framing","text":"Write the problem in a single sentence that a designer and an engineer will both agree with."},
 {"heading":"Composition","text":"Block out the grid with pure geometry before a single word is chosen for the page."},
 {"heading":"Colour","text":"Fill the panels with the three primaries and keep black and white carrying the hierarchy."},
 {"heading":"Type","text":"Set the headline heavy and tight, then open the tracking on every small label on the slide."},
 {"heading":"Release","text":"Export the deck, check it against the preview and ship it to the people who asked for it."},
]})

dump("6 steps, very long text", {"type":"process","title":"A six step workflow for the whole team","steps":[
 {"heading":"Discovery and stakeholder interviews","text":"Interview every single stakeholder across design, engineering, support and sales, then log all of the raw material in one shared place so that nothing whatsoever gets lost between the notes and the eventual deliverable."},
 {"heading":"Framing","text":"Write the problem down in a single sentence that a designer and an engineer will both agree with, and keep that sentence visible on the wall for the entire length of the engagement."},
 {"heading":"Composition","text":"Block out the grid with pure geometry before a single word is chosen for the page, checking the balance of the composition from across the room rather than from inches away."},
 {"heading":"Colour","text":"Fill the panels with the three primaries and let black and white carry the rest of the hierarchy on the page without any gradients, tints or shadows that blur the edges."},
 {"heading":"Typography","text":"Set the headline heavy and tightly tracked, then open the tracking right out on every small label so the eye can find the navigation before it reads the argument."},
 {"heading":"Release","text":"Export the deck, check the exported file against the live preview, fix anything that moved, then ship it to the people who asked for it in the first place."},
]})

dump("6 steps, long headings short text", {"type":"process","title":"Long headings","steps":[
 {"heading":"Discovery and stakeholder interviews","text":"Short."},
 {"heading":"Framing the problem statement","text":"Short."},
 {"heading":"Composition of the grid","text":"Short."},
 {"heading":"Colour application","text":"Short."},
 {"heading":"Typography decisions","text":"Short."},
 {"heading":"Release and review","text":"Short."},
]})

dump("2 steps", {"type":"process","title":"Two","steps":[{"heading":"One","text":"A"},{"heading":"Two","text":"B"}]})
dump("empty heading", {"type":"process","title":"Empty heading case","steps":[{"heading":"","text":"x"},{"heading":"","text":"y"}]})
