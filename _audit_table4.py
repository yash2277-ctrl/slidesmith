"""Row-height cap check: layout.py:1627 min(0.8, ...) vs the tallest-cell fit it just computed."""
from server.layout import layout_slide, text_h, est_lines
from server.themes import get_builtin

THEME = get_builtin("bauhaus")

def probe(tag, cols, rows):
    spec = {"type": "table", "title": "Token sheet", "columns": cols, "rows": rows}
    lay = layout_slide(spec, THEME, 0, [spec], "Audit")
    te = [e for e in lay["elements"] if e["t"] == "table"][0]
    rh = te["h"] / (len(te["rows"]) + 1)
    cw = te["w"] / len(cols)
    worst_v, worst = "", 0.0
    for row in [te["columns"]] + te["rows"]:
        for v in row:
            hh = text_h(v, te["size"], cw, "body", 1.2)
            if hh > worst:
                worst, worst_v = hh, v
    lines = est_lines(worst_v, te["size"], cw, "body")
    need_row = worst + 0.25          # what render_table measured for itself
    print(f"{tag}: size={te['size']} n_rows={len(te['rows'])+1} row_h={rh:.3f} "
          f"cell_w={cw:.3f} tallest_needs={worst:.3f} ({lines} lines, {worst_v[:40]!r}) "
          f"needed_with_pad={need_row:.3f}")
    print(f"   -> row_h {rh:.3f} vs text {worst:.3f}: "
          f"{'CELL TEXT OVERFLOWS ITS ROW by %.3f in' % (worst-rh) if worst > rh else 'fits'}")

probe("1 row, one very long cell",
      ["Token", "Value", "Use"],
      [["A very long descriptive value that is wider than one table column at the shipped size",
        "#D02020", "Action"]])

probe("3 rows, long cells",
      ["Design token name", "Resolved value", "Where it is applied"],
      [["surface / elevated background", "#FFFFFF", "Card fills and any raised panel that sits on the off-white canvas"],
       ["border / heavy structural stroke", "#121212 at 2.75pt", "Every card edge in the deck, drawn as a solid rule"],
       ["shadow / hard offset", "#121212 offset 0.08in", "Depth cue behind every card, never blurred"]])

probe("2 cols, long cells",
      ["Name", "Notes"],
      [["Radius treatment", "Zero radius or a full circle, never a rounded rectangle anywhere in the system"],
       ["Hard shadow", "A solid black rectangle offset a few hundredths of an inch, never blurred"]])

# what the bauhaus decoration gate does
print()
print("=== _bh_decorate gate (layout.py:1917) ===")
for tid in ("bauhaus", "midnight"):
    t = THEME if tid == "bauhaus" else __import__("server.themes", fromlist=["x"]).get_builtin(tid)
    spec = {"type": "table", "title": "Token sheet", "columns": ["A"], "rows": [["b"]]}
    lay = layout_slide(spec, t, 0, [spec], "Audit")
    shapes = [f"{e['t']}@{e['x']:.2f},{e['y']:.2f}" for e in lay["elements"] if e["t"] != "text"]
    print(f" {tid:9s} dna={t.get('dna')!r:>6}  non-text elements: {shapes}")