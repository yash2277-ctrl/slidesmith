"""Layout engine: slide spec + theme/template profile -> display list.

The display list (inches / points) is rendered twice: as HTML on the live canvas
(web/slides.js) and as native PowerPoint shapes (renderer.py). Keeping a single
source of geometry is what makes the preview match the exported file.
"""
from __future__ import annotations

import json
import math
import re

from . import design
from .media import icon_url
from .template_analyzer import contrast, luminance, mix

CHAR_W = {"heading": 0.6, "body": 0.5}
# wide faces the 0.5/0.6 em averages under-measure (the raster wraps with real metrics; keep layout honest too)
FACE_WIDTH = {"segoe print": 1.22, "ink free": 1.2, "century gothic": 1.08, "arial black": 1.12}


def _wfac(kind: str, face: str | None) -> float:
    return CHAR_W[kind] * FACE_WIDTH.get((face or "").lower().strip(), 1.0)


# ---------------------------------------------------------------- text fitting

def est_lines(text: str, size: float, width: float, kind: str = "body", face: str | None = None) -> int:
    if width <= 0.05:
        return 99
    per_line = max(1, int(width / (size / 72 * _wfac(kind, face))))
    return sum(max(1, math.ceil(len(part) * 1.06 / per_line)) for part in (text or " ").split("\n"))


def fit_size(text: str, w: float, h: float, max_pt: float, min_pt: float, kind="body", line=1.15, face=None) -> float:
    pt = max_pt
    while pt > min_pt:
        if est_lines(text, pt, w, kind, face) * pt / 72 * line <= h:
            return pt
        pt -= 1
    return min_pt


def fit_paras(paras: list[tuple[str, float, float]], w: float, h: float, max_pt: float, min_pt: float,
              kind="body", line=1.15, gap=0.45, face=None) -> float:
    """paras: (text, scale, indent_in). Returns a base size where all paragraphs fit."""
    pt = max_pt
    while pt > min_pt:
        total = 0.0
        for text, scale, indent in paras:
            s = pt * scale
            total += est_lines(text, s, w - indent - s / 72 * 1.1, kind, face) * s / 72 * line + s / 72 * gap
        if total <= h:
            return pt
        pt -= 1
    return min_pt


def P(text, size, color, font="body", bold=False, italic=False, bullet=None, level=0, space=0.0, caps=False, spacing=None):
    p = {"text": text, "size": round(size, 1), "color": color, "font": font, "bold": bold}
    if italic:
        p["italic"] = True
    if bullet:
        p["bullet"] = bullet
    if level:
        p["level"] = level
    if space:
        p["space"] = space
    if caps:
        p["caps"] = True
    if spacing:
        p["spacing"] = spacing
    return p


def T(x, y, w, h, paras, align="l", valign="t", line=1.15, ph=None):
    el = {"t": "text", "x": x, "y": y, "w": w, "h": h, "paras": paras, "align": align, "valign": valign, "line": line}
    if ph:
        el["ph"] = ph
    return el


def R(x, y, w, h, fill, alpha=1.0, radius=0.0, line=None, shape="rect", rot=0.0):
    el = {"t": shape, "x": x, "y": y, "w": w, "h": h, "fill": fill}
    if alpha < 1:
        el["alpha"] = alpha
    if radius:
        el["radius"] = radius
    if line:
        el["line"] = line
    if rot:
        el["rot"] = rot
    return el


def IMG(x, y, w, h, image: dict, fit="cover", radius=0.0):
    """Photo element (cover-cropped like a background image)."""
    el = {"t": "image", "x": x, "y": y, "w": w, "h": h, "src": image.get("src", ""), "fit": fit}
    if radius:
        el["radius"] = radius
    if image.get("w") and image.get("h"):
        el["iw"], el["ih"] = image["w"], image["h"]
    return el


def ICON(x, y, size, icon: str, color: str) -> dict:
    return {"t": "image", "x": x, "y": y, "w": size, "h": size, "src": icon_url(icon, color), "fit": "contain", "icon": True}


def CONN(p_from, p_to, color: str, width: float = 1.6, dash: bool = False) -> dict:
    """An arrow from one point to another, in the diagram's node coordinates."""
    (x1, y1), (x2, y2) = p_from, p_to
    el = {"t": "connector", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
          "color": color, "width": width, "arrow": True}
    if dash:
        el["dash"] = True
    return el


def has_icon(item: dict) -> bool:
    return isinstance(item.get("icon"), str) and ":" in item["icon"]


def photo(spec: dict) -> dict | None:
    img = spec.get("image")
    return img if isinstance(img, dict) and img.get("src") else None


def photo_slot(els, x, y, w, h, spec, frame, radius=0.0):
    """A photo, or a tidy placeholder while it is still being found."""
    img = photo(spec)
    if img:
        els.append(IMG(x, y, w, h, img, radius=radius))
        if img.get("credit"):
            els.append(R(x, y + h - 0.32, w, 0.32, "#000000", 0.45))
            els.append(T(x + 0.12, y + h - 0.3, w - 0.24, 0.28, [P("Photo: " + img["credit"], 7.5, "#FFFFFF")], valign="m", line=1.0))
    else:
        els.append(R(x, y, w, h, frame.c["surface"], radius=radius, line={"color": frame.c["border"], "width": 0.75}))
        label = spec.get("image", {}).get("query") if isinstance(spec.get("image"), dict) else spec.get("image")
        els.append(T(x, y, w, h, [P("Image" + (f": {label}" if label else ""), 12, frame.c["muted"])], "c", "m"))


def readable(on: str, light="#FFFFFF", dark="#111111") -> str:
    return light if contrast(light, on) >= contrast(dark, on) else dark


# ---------------------------------------------------------------- frames

class Frame:
    """Everything a slide-type renderer needs: geometry, palette, fonts, placeholders."""

    def __init__(self, theme: dict, role: str, alt: bool = False):
        self.theme = theme
        self.W, self.H = theme["slide_w"], theme["slide_h"]
        self.custom = theme["kind"] == "custom"
        c = dict(theme["colors"])
        self.layout = None
        self.bg = None
        if self.custom:
            key = theme["mapping"].get(role) or theme["mapping"]["visual"]
            self.layout = next((l for l in theme["layouts"] if l["key"] == key), theme["layouts"][0])
            bg = self.layout["bg_color"]
            text = theme["scheme"]["lt1"] if self.layout["dark"] else theme["scheme"]["dk1"]
            if contrast(text, bg) < 3:
                text = readable(bg, "#FFFFFF", "#111111")
            c.update(bg=bg, text=text, muted=mix(text, bg, 0.38), surface=mix(bg, text, 0.07), border=mix(bg, text, 0.16))
            brand = [b for b in theme.get("brand", []) if contrast(b, bg) >= 1.6]
            accents = brand + [c[k] for k in ("accent", "accent2", "accent3", "accent4") if c[k] not in brand]
            c.update(accent=accents[0], accent2=accents[1], accent3=accents[2], accent4=accents[3],
                     on_accent=readable(accents[0]))
        elif alt:
            bg = c["bg_alt"]
            text = c["text"] if contrast(c["text"], bg) >= 4.5 else readable(bg, "#FFFFFF", "#111111")
            c.update(text=text, muted=mix(text, bg, 0.35), surface=mix(bg, text, 0.08), border=mix(bg, text, 0.18))
            self.bg = {"type": "solid", "color": bg}
        else:
            self.bg = {"type": "solid", "color": c["bg"]}
        self.dna = theme.get("dna") or {}
        shift = 0 if theme.get("style") == "bauhaus" else self.dna.get("palette", 0)
        if shift:  # each deck leads with a different accent of the same palette
            acc = [c["accent"], c["accent2"], c["accent3"], c["accent4"]]
            acc = acc[shift:] + acc[:shift]
            c.update(accent=acc[0], accent2=acc[1], accent3=acc[2], accent4=acc[3], on_accent=readable(acc[0]))
        self.c = c
        self.style = theme.get("style", "")
        self.mx = 0.75 * self.W / 13.333
        self.heading_bold = theme["fonts"].get("heading_bold", True)
        self.f_head = theme["fonts"]["heading"]
        self.f_body = theme["fonts"]["body"]
        self.base = None
        self.faces = None
        self.index = 0
        self.occ = 0

    def rad(self, default=0.12):
        if self.style == "bauhaus":  # constructivist: everything is either square or a circle
            return 0.0
        return self.dna.get("radius", default) if self.dna else default

    def variant(self, kind, options):
        return design.pick(self.dna, kind, options, self.occ) if self.dna else options[0]

    def use_base(self, base: dict):
        """Draw this slide inside a sample page of the user's template (its frame, logos, title box)."""
        self.base = base
        self.layout = next((l for l in self.theme["layouts"] if l["key"] == base["layout_key"]), self.layout)
        bg = base["bg_color"]
        title = self.base_el(base["title_key"])
        text = next((p["color"] for p in (title or {}).get("paras", []) if p.get("color")), None)
        if not text or contrast(text, bg) < 3:
            text = readable(bg, "#FFFFFF", "#111111")
        body = self.base_el(base["body_key"])
        body_text = next((p["color"] for p in (body or {}).get("paras", []) if p.get("color") and p["text"].strip()), text)
        if contrast(body_text, bg) < 3:
            body_text = text
        self.c.update(bg=bg, text=body_text, muted=mix(body_text, bg, 0.38), surface=mix(bg, body_text, 0.06), border=mix(bg, body_text, 0.16))
        face = lambda el: next((p.get("face") for p in (el or {}).get("paras", []) if p.get("face") and p["text"].strip()), None)
        self.faces = {"heading": face(title) or face(body) or self.theme["fonts"]["heading"],
                      "body": face(body) or self.theme["fonts"]["body"]}

    @property
    def base_has_levels(self):
        body = self.base_el(self.base["body_key"]) if self.base else None
        return bool(body and any(p.get("level", 0) >= 1 and p["text"].strip() for p in body["paras"]))

    def base_el(self, key):
        if not self.base or not key:
            return None
        return next((e for e in self.base["elements"] if e.get("key") == key), None)

    # placeholders of the chosen template layout
    def ph(self, kind: str, n: int = 0):
        if not self.layout:
            return None
        phs = sorted((p for p in self.layout["placeholders"] if p["kind"] == kind), key=lambda p: (round(p["y"], 1), p["x"]))
        return phs[n] if len(phs) > n else None

    def bodies(self):
        if not self.layout:
            return []
        return sorted((p for p in self.layout["placeholders"] if p["kind"] == "body"), key=lambda p: p["x"])

    def content_rect(self):
        W, H, mx = self.W, self.H, self.mx
        if self.base:
            body = self.base_el(self.base["body_key"])
            title = self.base_el(self.base["title_key"])
            if body:
                top = max(body["y"], (title["y"] + title["h"] + 0.1) if title else 0)
                return (body["x"], top, body["w"], max(1.0, body["y"] + body["h"] - top))
        if not self.custom:
            return (mx, 1.95 * H / 7.5, W - 2 * mx, H - 1.95 * H / 7.5 - 0.85 * H / 7.5)
        title = self.ph("title")
        top = (title["y"] + title["h"] + 0.15) if title else 0.12 * H
        big = [b for b in self.bodies() if b["w"] * b["h"] > 0.15 * W * H]
        if big:
            x0 = min(b["x"] for b in big)
            x1 = max(b["x"] + b["w"] for b in big)
            y0 = max(top, min(b["y"] for b in big))
            y1 = max(b["y"] + b["h"] for b in big)
            return (x0, y0, x1 - x0, max(1.0, y1 - y0))
        ref = self._ref_body()
        if ref:
            y0 = max(top, ref["y"])
            return (ref["x"], y0, ref["w"], max(1.0, ref["y"] + ref["h"] - y0))
        x = title["x"] if title else mx
        w = title["w"] if title else W - 2 * mx
        return (x, top, w, max(1.0, H * 0.9 - top))

    def _ref_body(self):
        key = self.theme["mapping"].get("bullets")
        lay = next((l for l in self.theme["layouts"] if l["key"] == key), None)
        if not lay:
            return None
        bodies = [p for p in lay["placeholders"] if p["kind"] == "body"]
        return max(bodies, key=lambda p: p["w"] * p["h"]) if bodies else None


def ph_text(ph: dict, paras_text: list[tuple[str, int]], role: str, frame: Frame, bold=None) -> dict:
    """Text element bound to a template placeholder, sized to fit inside it."""
    st = ph["style"]
    kind = "heading" if role == "title" else "body"
    joined = "\n".join(t for t, _ in paras_text) or " "
    size = fit_size(joined, ph["w"] - 0.2, ph["h"] - 0.1, st["size"], max(10, st["size"] * 0.45), kind)
    paras = [P(t, size * (0.85 if lvl else 1), st["color"], kind, bold=st.get("bold") if bold is None else bold,
               bullet="tpl" if role == "body" else None, level=lvl) for t, lvl in paras_text]
    valign = {"ctr": "m", "b": "b"}.get(st.get("anchor"), "t")
    return T(ph["x"] + 0.1, ph["y"] + 0.05, ph["w"] - 0.2, ph["h"] - 0.1, paras, st.get("align", "l")[0] if st.get("align") in ("l", "r") else ("c" if st.get("align") == "ctr" else "l"),
             valign, ph={"idx": ph["idx"], "role": role, "fit": size < st["size"] - 0.5})


# ---------------------------------------------------------------- template sample pages

def _text_height(paras: list[dict], w: float, line: float, factor: float = 1.0) -> float:
    total = 0.0
    for p in paras:
        size = p["size"] * factor
        indent = 0.35 * p.get("level", 0) + (size / 72 * 1.1 if p.get("bullet") else 0)
        text = (p["text"] or " ").replace("\t", "    ")
        total += est_lines(text, size, max(0.3, w - indent), p.get("font", "body")) * size / 72 * line + p.get("space", 0) / 72
    return total


def _shrink(el: dict, original: list[dict]) -> dict:
    """Scale text down (never below 55%) when new text no longer fits the sample box."""
    allowed = max(el["h"], _text_height(original, el["w"], el.get("line", 1.2)))
    if _text_height(el["paras"], el["w"], el.get("line", 1.2)) <= allowed * 1.02:
        return el
    f = 1.0
    while f > 0.55 and _text_height(el["paras"], el["w"], el.get("line", 1.2), f) > allowed:
        f -= 0.05
    el["paras"] = [{**p, "size": round(p["size"] * f, 1)} for p in el["paras"]]
    el["shrink"] = round(f, 2)
    return el


BULLET_PREFIX = re.compile(r"^\s*[-\u2013\u2022*\u00b7\u25aa]\s+")


def _style_index(paras: list[dict], level: int) -> int | None:
    """Index of the sample paragraph whose formatting a new line of this level should reuse."""
    filled = [i for i, p in enumerate(paras) if p["text"].strip()]
    for lv in (level, level - 1, level - 2):
        same = [i for i in filled if paras[i].get("level", 0) == lv]
        if same:
            return same[0]
    return filled[0] if filled else (0 if paras else None)


def _new_para(paras: list[dict], idx: int | None, text: str, level: int) -> dict:
    base = dict(paras[idx]) if idx is not None else {"size": 18, "color": "#000000", "bold": False, "font": "body", "align": "l"}
    text = BULLET_PREFIX.sub("", text)
    if base.get("bullet"):
        text = re.sub(r"^\s*\d{1,2}[.)]\s+", "", text)
    base.update(text=text, level=level, src=idx)
    return base


def _auto_styles(paras: list[dict], lines: list[dict]) -> list[int | None]:
    """Lines given without levels mirror the sample: an optional heading line, then list items."""
    filled = [i for i, p in enumerate(paras) if p["text"].strip()]
    if not filled:
        return [0 if paras else None] * len(lines)
    key = lambda i: (paras[i]["size"], bool(paras[i]["bold"]), paras[i].get("level", 0))
    rest = filled[1:] or filled
    item = max(rest, key=lambda i: sum(1 for j in rest if key(j) == key(i)))
    head = filled[0]
    heading_like = len(filled) > 1 and head != item and (paras[head]["size"] > paras[item]["size"] + 1 or paras[head].get("level", 0) < paras[item].get("level", 0))
    first = BULLET_PREFIX.sub("", lines[0]["text"]).strip() if lines else ""
    sample_head = paras[head]["text"].strip().lower()
    looks_heading = first and (first.lower()[:12] in sample_head or sample_head[:12] in first.lower()
                               or (len(first.split()) <= 7 and not first[0].isdigit() and not first.endswith(".") and len(lines) > 2))
    if heading_like and looks_heading:
        return [head] + [item] * (len(lines) - 1)
    return [item] * len(lines)


def fill_text(el: dict, lines: list[dict]) -> dict:
    """Replace every paragraph of a sample text box, reusing the formatting of matching sample lines."""
    paras = []
    auto = _auto_styles(el["paras"], lines) if lines and all(ln.get("level") is None for ln in lines) else None
    for k, ln in enumerate(lines):
        if auto is not None:
            idx = auto[k]
            level = el["paras"][idx].get("level", 0) if idx is not None else 0
        else:
            level = ln["level"] if ln.get("level") is not None else 0
            idx = _style_index(el["paras"], level)
        paras.append(_new_para(el["paras"], idx, ln["text"], level))
    if not paras:
        paras = [_new_para(el["paras"], _style_index(el["paras"], 0), "", 0)]
    return _shrink({**el, "paras": paras}, el["paras"])


def fill_paras(el: dict, changes: dict) -> dict:
    """Replace individual paragraphs (a change may expand into several lines); all others stay as they are."""
    paras = []
    for i, p in enumerate(el["paras"]):
        if i not in changes:
            paras.append({**p, "src": i})
            continue
        for ln in changes[i] or [{"text": "", "level": None}]:
            level = ln["level"] if ln.get("level") is not None else p.get("level", 0)
            idx = i if level == p.get("level", 0) else _style_index(el["paras"], level)
            paras.append(_new_para(el["paras"], idx, ln["text"], level))
    return _shrink({**el, "paras": paras}, el["paras"])


def _lines(value) -> list[dict]:
    """Fill value -> lines; level None means "same level as the line being replaced"."""
    if isinstance(value, str):
        return [{"text": t, "level": None} for t in value.split("\n")]
    out = []
    for item in value or []:
        if isinstance(item, str):
            out.extend({"text": t, "level": None} for t in item.split("\n"))
        elif isinstance(item, dict):
            try:
                level = max(0, min(4, int(item["level"]))) if item.get("level") is not None else None
            except (TypeError, ValueError):
                level = None
            out.append({"text": str(item.get("text", "")), "level": level})
    return out


def template_slide(theme: dict, sid) -> dict | None:
    return next((s for s in theme.get("slides", []) if s["id"] == sid), None)


def split_fill(fill: dict):
    whole, per_para, cells = {}, {}, {}
    for key, value in (fill or {}).items():
        base, _, sub = key.partition(".")
        flat = value if isinstance(value, str) else " ".join(l["text"] for l in _lines(value))
        if not sub:
            whole[base] = value
        elif sub.startswith("p") and sub[1:].isdigit():
            per_para.setdefault(base, {})[int(sub[1:])] = _lines(value)
        elif sub.startswith("r") and "c" in sub:
            try:
                r, c = sub[1:].split("c")
                cells.setdefault(base, {})[(int(r), int(c))] = flat
            except ValueError:
                pass
    return whole, per_para, cells


def apply_fill(ts: dict, fill: dict) -> list[dict]:
    """Sample page elements with the AI's replacements applied."""
    whole, per_para, cells = split_fill(fill)
    out = []
    for e in ts["elements"]:
        key = e.get("key")
        if e["t"] == "text" and key in whole:
            e = fill_text(e, _lines(whole[key]))
        elif e["t"] == "text" and key in per_para:
            e = fill_paras(e, per_para[key])
        elif e["t"] == "tpltable" and key in cells:
            e = json.loads(json.dumps(e))
            for (r, c), text in cells[key].items():
                if r < len(e["rows"]) and c < len(e["rows"][r]["cells"]):
                    cell = e["rows"][r]["cells"][c]
                    cell["text"] = text
                    if cell["paras"]:
                        cell["paras"] = [{**cell["paras"][0], "text": text}]
                    cell["changed"] = True
        else:
            e = dict(e)
            if key:
                e["static"] = True
        out.append(e)
    return out


def _with_title(spec: dict, ts: dict) -> dict:
    """Fill an empty sample title bar with the slide title (older saved slides didn't)."""
    fill = dict(spec.get("fill") or {})
    title = spec.get("title", "")
    tkey, body = ts.get("title_key"), ts.get("body_key")
    if not (title and tkey and ts["role"] not in ("cover", "closing")) or any(k.split(".")[0] == tkey for k in fill):
        return fill
    fill[tkey] = title
    same = lambda v: isinstance(v, str) and v.strip().strip("	").casefold() == title.strip().casefold()
    if body and isinstance(fill.get(body), list) and fill[body]:
        first = fill[body][0]
        if same(first if isinstance(first, str) else first.get("text")):
            fill[body] = fill[body][1:]
    for key in (body + ".p0",) if body else ():
        v = fill.get(key)
        if same(v) or (isinstance(v, list) and len(v) == 1 and same(v[0] if isinstance(v[0], str) else v[0].get("text"))):
            fill[key] = ""
    return fill


def render_template(spec: dict, theme: dict):
    ts = template_slide(theme, spec.get("source"))
    if not ts:
        return None
    spec = {**spec, "fill": _with_title(spec, ts)}
    return {"w": theme["slide_w"], "h": theme["slide_h"], "bg": ts["bg"], "layout_key": ts["layout_key"],
            "hide_master": ts["hide_master"], "elements": apply_fill(ts, spec.get("fill")),
            "clone": {"source": ts["id"], "remove": []}}


def template_title(spec: dict, theme: dict) -> str:
    """A readable label for a template-page slide (used on canvas cards)."""
    if spec.get("title"):
        return spec["title"]
    ts = template_slide(theme, spec.get("source"))
    if not ts:
        return spec.get("source", "")
    els = {e.get("key"): e for e in apply_fill(ts, spec.get("fill")) if e["t"] == "text"}
    for key in (ts["title_key"], ts["body_key"]):
        e = els.get(key)
        line = next((p["text"].strip() for p in e["paras"] if p["text"].strip()), "") if e else ""
        if line:
            return line[:80]
    return ts["role"].title()


# ---------------------------------------------------------------- shared chrome

def content_title(frame: Frame, spec: dict, els: list):
    """Title (+ accent rule) for content slides."""
    if frame.style == "bauhaus" and not frame.custom:
        return _bh_content_title(frame, spec, els)
    title = spec.get("title", "")
    if frame.base and frame.base_el(frame.base["title_key"]):
        els.append(fill_text(frame.base_el(frame.base["title_key"]), [{"text": title, "level": 0}]))
        return
    if frame.custom:
        ph = frame.ph("title")
        if ph:
            els.append(ph_text(ph, [(title, 0)], "title", frame))
        else:
            x, y, w, _ = frame.content_rect()
            els.append(T(x, 0.4, w, 1.0, [P(title, 32, frame.c["text"], "heading", True)], valign="b"))
        return
    W, H, mx = frame.W, frame.H, frame.mx
    style = frame.dna.get("title", "bar") if frame.dna else "bar"
    size = fit_size(title, W - 2 * mx, 1.05, 34, 22, "heading", face=frame.f_head)
    kicker = spec.get("kicker") or (f"{frame.index + 1:02d}" if style == "kicker" else "")
    if kicker:
        els.append(T(mx, 0.38, W - 2 * mx, 0.3, [P(kicker.upper(), 11, frame.c["accent"], "body", True, spacing=2)]))
    tx = mx + (0.32 if style == "side" else 0)
    els.append(T(tx, 0.62, W - 2 * mx, 1.05, [P(title, size, frame.c["text"], "heading", frame.heading_bold)], valign="b", line=1.05))
    if style == "bar":
        els.append(R(mx, 1.78 * H / 7.5, 0.7, 0.06, frame.c["accent"]))
    elif style == "side":
        els.append(R(mx, 0.95, 0.08, 0.78, frame.c["accent"]))
    elif style == "plain":
        els.append(R(mx, 1.8 * H / 7.5, W - 2 * mx, 0.015, frame.c["border"]))


def footer(frame: Frame, deck_title: str, index: int, els: list):
    if frame.custom:
        return
    if frame.style == "bauhaus":
        W, H, mx = frame.W, frame.H, frame.mx
        els.append(T(mx, H - 0.5, W * 0.6, 0.26, [P(deck_title, 8.5, frame.c["muted"], "body", True, caps=True, spacing=1.5)], valign="m"))
        d = 0.3
        els.append(R(W - mx - d, H - 0.52, d, d, "#121212"))
        els.append(T(W - mx - d, H - 0.52, d, d, [P(str(index + 1), 10.5, "#FFFFFF", "heading", True)], "c", "m", line=1.0))
        return
    W, H, mx = frame.W, frame.H, frame.mx
    els.append(T(mx, H - 0.5, W * 0.6, 0.28, [P(deck_title, 9.5, frame.c["muted"])], valign="m"))
    els.append(T(W - mx - 1.2, H - 0.5, 1.2, 0.28, [P(str(index + 1), 9.5, frame.c["muted"])], align="r", valign="m"))


# ---------------------------------------------------------------- bauhaus style
# Constructivist modernism: pure primaries (red/blue/yellow), stark black, hard
# offset shadows instead of soft ones, thick black borders, sharp corners, and
# decorations built only from circles, squares and triangles.

BH_INK = "#121212"
BH_HAIRLINE = "#ADADAD"


def _bh_primaries(frame: Frame) -> list[str]:
    return [frame.c["accent"], frame.c["accent2"], frame.c["accent3"]]


def _bh_shadow(els: list, x: float, y: float, w: float, h: float, off: float = 0.08, rot: float = 0.0, shape: str = "rect"):
    els.append(R(x + off, y + off, w, h, BH_INK, shape=shape, rot=rot))


def _bh_corner(frame: Frame, els: list, x: float, y: float, i: int, s: float = 0.15):
    """Small geometric mark in a card corner: circle / square / triangle, rotating."""
    els.append(R(x, y, s, s, _bh_primaries(frame)[i % 3], shape=("ellipse", "rect", "triangle")[i % 3]))


def _bh_card(frame: Frame, els: list, x: float, y: float, w: float, h: float, off: float = 0.08,
             border: float = 2.75, fill: str = "#FFFFFF", deco: int | None = None):
    _bh_shadow(els, x, y, w, h, off)
    els.append(R(x, y, w, h, fill, line={"color": BH_INK, "width": border}))
    if deco is not None:
        _bh_corner(frame, els, x + w - 0.38, y + 0.14, deco)


def _bh_bleed(R_el: dict) -> dict:
    """Tag a full-bleed decoration so bounds checks don't read it as an overflow."""
    R_el["bleed"] = True
    return R_el


def _bh_badge(frame: Frame, els: list, x: float, y: float, i: int, d: float = 0.5, with_number=True):
    """A number in a geometric shape: red circle, blue square, yellow rotated square."""
    acc = _bh_primaries(frame)[i % 3]
    kind = ("ellipse", "rect", "rect")[i % 3]
    s = d * 0.78 if i % 3 == 2 else d  # rotated square: same visual diagonal
    rot = 45 if i % 3 == 2 else 0
    _bh_shadow(els, x, y + (d - s) / 2, s, s, 0.05, rot=rot, shape=kind)
    els.append(R(x, y + (d - s) / 2, s, s, acc, line={"color": BH_INK, "width": 1.75}, shape=kind, rot=rot))
    if with_number:
        els.append(T(x, y, d, d, [P(str(i + 1), d * 26, readable(acc), "heading", True)], "c", "m", line=1.0))


def _bh_icon_tile(frame: Frame, els: list, x: float, y: float, s: float, item: dict, i: int):
    acc = _bh_primaries(frame)[i % 3]
    els.append(R(x, y, s, s, acc, line={"color": BH_INK, "width": 1.5}))
    if has_icon(item):
        els.append(ICON(x + s * 0.18, y + s * 0.18, s * 0.64, item["icon"], readable(acc)))
    else:
        els.append(T(x, y, s, s, [P(str(i + 1), 15, readable(acc), "heading", True)], "c", "m", line=1.0))


def _bh_trio(frame: Frame, els: list, x: float, y: float, i: int, s: float = 0.16):
    """The geometric logo: circle, square and triangle cascading diagonally."""
    acc = _bh_primaries(frame)
    els.append(R(x, y, s, s, acc[i % 3], shape="ellipse"))
    els.append(R(x + s * 0.95, y + s * 0.8, s * 0.85, s * 0.85, acc[(i + 1) % 3]))
    els.append(R(x + s * 1.85, y + s * 1.6, s * 0.95, s * 0.95, acc[(i + 2) % 3], shape="triangle"))


def _bh_content_title(frame: Frame, spec: dict, els: list):
    W, H, mx, c = frame.W, frame.H, frame.mx, frame.c
    title = spec.get("title", "")
    if frame.base and frame.base_el(frame.base["title_key"]):
        els.append(fill_text(frame.base_el(frame.base["title_key"]), [{"text": title, "level": 0}]))
        return
    els.append(R(mx, 0.44, 0.15, 0.15, c["accent"]))
    if spec.get("kicker"):
        els.append(T(mx + 0.26, 0.37, W - 2 * mx - 1.6, 0.3, [P(spec["kicker"], 11, c["accent2"], "body", True, caps=True, spacing=2)], valign="m"))
    size = fit_size(title, (W - 2 * mx) * 0.92, 1.05, 33, 22, "heading")
    els.append(T(mx, 0.62, W - 2 * mx, 1.05, [P(title, size, c["text"], "heading", True, caps=True, spacing=-0.5)], valign="b", line=1.04))
    els.append(R(mx, 1.76, W - 2 * mx, 0.045, BH_INK))


def _bh_hero(frame: Frame, spec: dict, els: list, closing: bool = False):
    W, H, mx, c = frame.W, frame.H, frame.mx, frame.c
    if photo(spec):
        return _photo_hero(frame, spec, els, photo(spec), closing)
    title, sub = spec.get("title", ""), spec.get("subtitle", "")
    kicker, contact = spec.get("kicker", ""), spec.get("contact", "")
    if closing:  # the yellow call-to-action block
        frame.bg = {"type": "solid", "color": c["accent3"]}
        els.append(_bh_bleed(R(W - 3.0, -1.5, 3.4, 3.4, c["accent"], 0.5, shape="ellipse")))
        els.append(_bh_bleed(R(-1.3, H - 3.4, 2.9, 2.9, c["accent2"], 0.5, rot=45)))
        tx, tw, align = mx * 2, W - 4 * mx, "c"
    else:  # off-white poster with a blue color-blocked panel and a geometric composition
        frame.bg = {"type": "solid", "color": c["bg"]}
        px = W * 0.63
        els.append(R(px, 0, W - px, H, c["accent2"]))
        els.append(R(px - 0.055, 0, 0.055, H, BH_INK))
        d, cx, cy = 3.1, px + (W - px) / 2, H * 0.44
        els.append(R(cx - d / 2, cy - d / 2, d, d, c["accent3"], line={"color": BH_INK, "width": 2.5}, shape="ellipse"))
        q = 1.7
        els.append(R(cx - d / 2 - 0.5, cy - d / 2 + 0.3, q, q, "#FFFFFF", line={"color": BH_INK, "width": 2.5}, rot=45))
        s = 1.1
        els.append(R(cx + d / 2 - s - 0.3, cy + d / 2 - s - 0.45, s, s, c["accent"], line={"color": BH_INK, "width": 2.25}, shape="ellipse"))
        t = 0.85
        els.append(R(cx - d / 2 - 0.05, cy + d / 2 + 0.32, t, t, "#FFFFFF", line={"color": BH_INK, "width": 2.25}, shape="triangle"))
        tx, tw, align = mx, px - mx - 0.6, "l"
    size = fit_size(title, tw * 0.94, 2.4, 56 if not closing else 50, 30, "heading", 1.05)
    th = est_lines(title, size, tw * 0.94, "heading") * size / 72 * 1.08 + 0.1
    sub_size = fit_size(sub, tw, 1.2, 21, 14) if sub else 20
    sh = (est_lines(sub, sub_size, tw) * sub_size / 72 * 1.3 + 0.1) if sub else 0
    block = (0.45 if kicker else 0) + th + (0.28 + sh if sub else 0) + (0.6 if contact else 0)
    y = max(0.6, (H - block) / 2 - 0.1)
    if kicker:
        els.append(T(tx, y, tw, 0.35, [P(kicker, 13, c["accent"], "body", True, caps=True, spacing=3)], align))
        y += 0.45
    els.append(T(tx, y, tw, th, [P(title, size, c["text"], "heading", True, caps=True, spacing=-0.5)], align, line=1.05))
    y += th + 0.28
    if sub:
        els.append(T(tx, y, tw, sh, [P(sub, sub_size, c["muted"] if not closing else BH_INK)], align, line=1.25))
        y += sh + 0.15
    if contact:
        els.append(T(tx, y + 0.1, tw, 0.4, [P(contact, 15, c["accent2"] if not closing else BH_INK, "body", True)], align))


def _bh_section(frame: Frame, spec: dict, els: list, number: int):
    W, H, mx, c = frame.W, frame.H, frame.mx, frame.c
    frame.bg = {"type": "solid", "color": c["accent"]}  # red color block
    els.append(_bh_bleed(R(W - 2.6, H - 2.6, 3.8, 3.8, c["accent3"], shape="ellipse")))
    els.append(R(W - 1.95, 0.7, 1.1, 1.1, c["accent2"], line={"color": BH_INK, "width": 2.25}))
    els.append(R(W - 3.6, 0.62, 0.95, 0.95, "#FFFFFF", line={"color": BH_INK, "width": 2}, shape="triangle"))
    b = 1.1
    _bh_shadow(els, mx, 1.0, b, b, 0.09, rot=45)
    els.append(R(mx, 1.0, b, b, c["accent3"], line={"color": BH_INK, "width": 2.5}, rot=45))
    els.append(T(mx, 1.0, b, b, [P(f"{number:02d}", 24, BH_INK, "heading", True)], "c", "m", line=1.0))
    title = spec.get("title", "")
    size = fit_size(title, (W - 2 * mx - 1) * 0.94, 2.1, 52, 30, "heading")
    els.append(T(mx, 3.0, W - 2 * mx - 1, 2.1, [P(title, size, "#FFFFFF", "heading", True, caps=True, spacing=-0.5)], line=1.03))
    if spec.get("subtitle"):
        els.append(T(mx, 5.25, W - 2 * mx - 4.0, 0.9, [P(spec["subtitle"], 19, "#FFD9D9")], line=1.25))
    els.append(R(mx, H - 0.8, 2.2, 0.09, BH_INK))


def _bh_bullets(frame: Frame, spec: dict, els: list):
    c = frame.c
    items = spec.get("bullets", [])
    if not items:
        return
    x, y, w, h = frame.content_rect()
    ink, soft = c["text"], mix(c["text"], c["bg"], 0.25)
    lead = 0.82
    tw = w - lead - 0.1

    def row_h(b, size):
        return max(0.52, text_h(b["text"], size, tw, "body", 1.22) + sum(text_h(s, size * 0.85, tw, "body", 1.25) for s in b["sub"]) + 0.22)
    size = 21
    while size > 11 and sum(row_h(b, size) for b in items) + 0.16 * (len(items) - 1) > h:
        size -= 1
    gap = 0.16
    heights = [row_h(b, size) for b in items]
    total = sum(heights) + gap * max(0, len(items) - 1)
    if total > h:  # extreme copy: squeeze the rows rather than run off the slide
        k = max(0.4, h / total)
        heights = [hh * k for hh in heights]
        total = sum(heights) + gap * max(0, len(items) - 1)
    yy = _top(y, h, total)
    for i, b in enumerate(items):
        rh = heights[i]
        _bh_badge(frame, els, x, yy + (rh - 0.5) / 2, i, 0.5)
        paras = [P(b["text"], size, ink)] + [P(s, size * 0.85, soft) for s in b["sub"]]
        els.append(T(x + lead, yy, tw, rh, paras, valign="m", line=1.24))
        yy += rh
        if i < len(items) - 1 and gap:
            els.append(R(x + lead, yy + gap / 2 - 0.01, tw, 0.02, BH_HAIRLINE))
            yy += gap


def _bh_cards(frame: Frame, spec: dict, els: list):
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    cards = spec.get("cards", [])
    x, y, w, h = frame.content_rect()
    n = len(cards)
    cols = n if n <= 3 else (4 if n == 4 and w > 10 else (2 if n == 4 else 3))
    rows = math.ceil(n / cols)
    gap = 0.34
    cw = (w - gap * (cols - 1)) / cols
    iw = cw - 0.56
    row_avail = (h - gap * (rows - 1)) / rows
    badge = 0.5

    def need(cd, hs, ts):
        return 0.3 + max(badge, text_h(cd["heading"], hs, iw - badge - 0.34, "heading", 1.12)) + 0.18 + text_h(cd["text"], ts, iw, "body", 1.32) + 0.34
    hs, ts = 19, 15.5
    while max(need(cd, hs, ts) for cd in cards) > row_avail and (ts > 11 or hs > 13):
        ts, hs = max(11, ts - 0.5), max(13, hs - 0.5)
    over = max(need(cd, hs, ts) for cd in cards) / max(row_avail, 0.01)
    if over > 1:  # a wall of text: scale the type down instead of spilling out of the card
        k = max(0.6, 1 / over)
        hs, ts = round(hs * k, 1), round(ts * k, 1)
    card_h = min(row_avail, max(need(cd, hs, ts) for cd in cards))
    top = _top(y, h, rows * card_h + gap * (rows - 1))
    for i, cd in enumerate(cards):
        r, col = divmod(i, cols)
        in_row = cols if r < rows - 1 else n - cols * (rows - 1)
        cx = x + (cols - in_row) * (cw + gap) / 2 + col * (cw + gap)
        cy = top + r * (card_h + gap)
        _bh_card(frame, els, cx, cy, cw, card_h, deco=i)
        _bh_icon_tile(frame, els, cx + 0.28, cy + 0.3, badge, cd, i)
        hh = text_h(cd["heading"], hs, iw - badge - 0.34, "heading", 1.12)
        els.append(T(cx + 0.28 + badge + 0.16, cy + 0.3, iw - badge - 0.34, max(hh, badge),
                     [P(cd["heading"], hs, ink, "heading", True, caps=True)], valign="m", line=1.12))
        ty = cy + 0.3 + max(badge, hh) + 0.18
        els.append(T(cx + 0.28, ty, iw, max(0.3, cy + card_h - ty - 0.26), [P(cd["text"], ts, soft)], line=1.32))


def _bh_stats(frame: Frame, spec: dict, els: list):
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    stats = spec.get("stats", [])
    x, y, w, h = frame.content_rect()
    n = len(stats)
    gap = 0.4
    cw = (w - gap * (n - 1)) / n
    iw = cw - 0.3
    d = min(1.9, cw - 0.5, h * 0.4)
    ls, ds = 18, 14

    def need(st):
        return d + 0.32 + text_h(st["label"], ls, iw, "heading", 1.12) + (0.12 + text_h(st.get("detail", ""), ds, iw, "body", 1.3) if st.get("detail") else 0) + 0.2
    while max(need(st) for st in stats) > h and ds > 11:
        ds -= 1
        ls = max(13, ls - 1)
    card_h = min(h, max(need(st) for st in stats))
    top = _top(y, h, card_h)
    for i, st in enumerate(stats):
        cx = x + i * (cw + gap)
        bx = cx + cw / 2 - d / 2
        acc = _bh_primaries(frame)[i % 3]
        if i % 3 == 2:  # rotated square, drawn so its diagonal matches the other shapes
            s = d * 0.72
            _bh_shadow(els, bx + (d - s) / 2, top + (d - s) / 2, s, s, 0.07, rot=45)
            els.append(R(bx + (d - s) / 2, top + (d - s) / 2, s, s, acc, line={"color": BH_INK, "width": 2.25}, rot=45))
        else:
            _bh_shadow(els, bx, top, d, d, 0.07, shape="ellipse" if i % 3 == 0 else "rect")
            els.append(R(bx, top, d, d, acc, line={"color": BH_INK, "width": 2.25}, shape="ellipse" if i % 3 == 0 else "rect"))
        vs = fit_size(st["value"], d * 0.74, d * 0.44, 40, 16, "heading")
        els.append(T(bx, top, d, d, [P(st["value"], vs, readable(acc), "heading", True)], "c", "m", line=1.0))
        yy = top + d + 0.32
        lh = text_h(st["label"], ls, iw, "heading", 1.12)
        els.append(T(cx + 0.15, yy, iw, lh, [P(st["label"], ls, ink, "heading", True, caps=True)], "c", line=1.12))
        yy += lh + 0.12
        if st.get("detail"):
            els.append(T(cx + 0.15, yy, iw, max(0.3, top + card_h - yy), [P(st["detail"], ds, soft)], "c", line=1.3))


def _bh_timeline(frame: Frame, spec: dict, els: list):
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    steps = spec.get("steps", [])
    x, y, w, h = frame.content_rect()
    n = len(steps)
    avg = sum(len(st["text"]) for st in steps) / max(n, 1)
    if n > 5 or avg > 110:
        return _bh_timeline_grid(frame, steps, x, y, w, h, els)
    seg = w / n
    iw = seg - 0.55
    head = 1.45

    def card_need(st, hs, ts):
        return 0.24 + text_h(st["heading"], hs, iw - 0.3, "heading", 1.1) + 0.1 + text_h(st["text"], ts, iw - 0.3, "body", 1.28) + 0.3
    hs, ts = 17, 14
    while head + max(card_need(st, hs, ts) for st in steps) > h and (ts > 11 or hs > 13):
        ts, hs = max(11, ts - 1), max(13, hs - 0.5)
    card_h = min(h - head - 0.1, max(card_need(st, hs, ts) for st in steps))
    top = _top(y, h, head + card_h)
    line_y = top + 0.92
    els.append(R(x + seg / 2, line_y - 0.025, w - seg, 0.05, BH_INK))
    for i, st in enumerate(steps):
        cx = x + i * seg
        mid = cx + seg / 2
        acc = _bh_primaries(frame)[i % 3]
        els.append(T(cx + 0.05, top, seg - 0.1, 0.32, [P((st["label"] or "").upper(), 12.5, ink, "body", True, spacing=1.5)], "c", "b"))
        if i % 3 == 2:
            s_ = 0.42 * 0.74
            els.append(R(mid - s_ / 2, line_y - s_ / 2, s_, s_, acc, line={"color": BH_INK, "width": 1.75}, rot=45))
        else:
            els.append(R(mid - 0.21, line_y - 0.21, 0.42, 0.42, acc, line={"color": BH_INK, "width": 1.75}, shape="ellipse" if i % 3 == 0 else "rect"))
        _bh_card(frame, els, cx + 0.1, line_y + 0.45, seg - 0.2, card_h, off=0.06, border=2.0)
        hh = text_h(st["heading"], hs, iw - 0.3, "heading", 1.1)
        els.append(T(cx + 0.28, line_y + 0.65, iw - 0.3, hh, [P(st["heading"], hs, ink, "heading", True)], "c", line=1.1))
        els.append(T(cx + 0.28, line_y + 0.65 + hh + 0.08, iw - 0.3, max(0.3, card_h - hh - 0.6), [P(st["text"], ts, soft)], "c", line=1.28))


def _bh_timeline_grid(frame: Frame, steps: list, x: float, y: float, w: float, h: float, els: list):
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    n = len(steps)
    cols = math.ceil(n / 2)
    gap = 0.32
    cw = (w - gap * (cols - 1)) / cols
    iw = cw - 0.5
    row_avail = (h - 0.4) / 2

    def need(st, hs, ts):
        return 0.26 + 0.3 + 0.08 + text_h(st["heading"], hs, iw, "heading", 1.1) + 0.08 + text_h(st["text"], ts, iw, "body", 1.28) + 0.28
    hs, ts = 17, 14
    while max(need(st, hs, ts) for st in steps) > row_avail and (ts > 11 or hs > 13):
        ts, hs = max(11, ts - 1), max(13, hs - 0.5)
    card_h = min(row_avail, max(need(st, hs, ts) for st in steps))
    top = _top(y, h, 2 * card_h + 0.4)
    for i, st in enumerate(steps):
        r, col = divmod(i, cols)
        cx, cy = x + col * (cw + gap), top + r * (card_h + 0.4)
        _bh_card(frame, els, cx, cy, cw, card_h, off=0.06, border=2.0, deco=i)
        els.append(T(cx + 0.25, cy + 0.18, iw, 0.3, [P((st["label"] or f"Step {i + 1}"), 11.5, acc_text[i % 4], "body", True, caps=True, spacing=1.5)], valign="m"))
        hh = text_h(st["heading"], hs, iw, "heading", 1.1)
        els.append(T(cx + 0.25, cy + 0.52, iw, hh, [P(st["heading"], hs, ink, "heading", True)], line=1.1))
        els.append(T(cx + 0.25, cy + 0.52 + hh + 0.08, iw, max(0.3, card_h - hh - 0.85), [P(st["text"], ts, soft)], line=1.28))


def _bh_two_col(frame: Frame, spec: dict, els: list):
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    cols = (spec.get("left", {}), spec.get("right", {}))
    x, y, w, h = frame.content_rect()
    gap = 0.5
    cw = (w - gap) / 2
    pad = 0.32
    iw = cw - 2 * pad

    def need(col, size):
        return 0.4 + text_h(col.get("heading", ""), size + 2, iw - 0.3, "heading", 1.1) + 0.24 \
            + sum(text_h(b, size, iw - size / 72 * 1.1, "body", 1.25) + size / 72 * 0.5 for b in col.get("bullets", [])) + 0.3
    size = 19
    while size > 11 and max(need(col, size) for col in cols) > h:
        size -= 1
    over = max(need(col, size) for col in cols) / max(h, 0.01)
    if over > 1:  # overstuffed columns: shrink further so the copy stays inside the panel
        size = max(9, round(size / over, 1))
    panel_h = min(h, max(need(col, size) for col in cols))
    top = _top(y, h, panel_h)
    for i, col in enumerate(cols):
        cx = x + i * (cw + gap)
        _bh_card(frame, els, cx, top, cw, panel_h, off=0.09, border=3.0, deco=i)
        acc = accents[i % 4]
        hh = text_h(col.get("heading", ""), size + 2, iw - 0.3, "heading", 1.1)
        els.append(R(cx + pad, top + 0.36, 0.16, 0.16, acc))
        els.append(T(cx + pad + 0.28, top + 0.3, iw - 0.3, hh + 0.12, [P(col.get("heading", ""), size + 2, ink, "heading", True, caps=True)], valign="m", line=1.1))
        paras = [P(t, size, ink, bullet=acc, space=size * 0.5) for t in col.get("bullets", [])]
        els.append(T(cx + pad, top + 0.42 + max(hh, 0.3) + 0.24, iw, panel_h - max(hh, 0.3) - 0.95, paras, line=1.25))


def _bh_matrix(frame: Frame, spec: dict, els: list):
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    quads = (spec.get("quadrants", []) + [{"heading": "", "text": "", "icon": ""}] * 4)[:4]
    x, y, w, h = frame.content_rect()
    ty_ = 0.34 if spec.get("y_axis") else 0
    by = 0.4 if spec.get("x_axis") else 0
    if ty_:
        els.append(T(x, y, w, ty_, [P("↑  " + spec["y_axis"], 12, soft, "body", True)], valign="m"))
        y, h = y + ty_, h - ty_
    gap = 0.26
    cw, ch = (w - gap) / 2, (h - by - gap) / 2
    iw = cw - 0.6

    def need(q, hs, ts):
        return 0.32 + text_h(q["heading"], hs, iw - 0.25, "heading", 1.1) + 0.12 + text_h(q["text"], ts, iw, "body", 1.3) + 0.26
    hs, ts = 18, 15
    while max(need(q, hs, ts) for q in quads) > ch and ts > 11:
        ts, hs = ts - 1, max(14, hs - 1)
    for i, q in enumerate(quads):
        r, col = divmod(i, 2)
        qx, qy = x + col * (cw + gap), y + r * (ch + gap)
        _bh_card(frame, els, qx, qy, cw, ch, off=0.07, border=2.5, deco=i)
        acc = accents[i % 4]
        hh = max(0.36, text_h(q["heading"], hs, iw - 0.25, "heading", 1.1))
        els.append(R(qx + 0.3, qy + 0.3, 0.09, hh + 0.04, acc))
        els.append(T(qx + 0.52, qy + 0.28, iw - 0.25, hh + 0.06, [P(q["heading"], hs, ink, "heading", True, caps=True)], valign="m", line=1.1))
        els.append(T(qx + 0.3, qy + 0.32 + hh + 0.14, iw, max(0.3, ch - hh - 0.62), [P(q["text"], ts, soft)], line=1.3))
    if spec.get("x_axis"):
        els.append(T(x, y + h - by + 0.05, w, by - 0.05, [P(spec["x_axis"] + "  →", 12, soft, "body", True)], "c", "m"))


def _bh_quote(frame: Frame, spec: dict, els: list):
    W, H, c = frame.W, frame.H, frame.c
    quote, who = spec.get("quote", ""), spec.get("attribution", "")
    x, y, w, h = frame.mx * 1.9, 0.95, W - frame.mx * 3.9, H - 2.2
    els.append(_bh_bleed(R(W - 3.0, H - 3.0, 3.9, 3.9, c["accent2"], shape="ellipse")))
    els.append(R(W - 4.3, H - 1.2, 1.0, 1.0, c["accent3"], line={"color": BH_INK, "width": 2}, rot=45))
    els.append(R(W - 2.35, 0.55, 0.9, 0.9, c["accent"], line={"color": BH_INK, "width": 2}, shape="triangle"))
    els.append(T(x, y, 2.2, 1.9, [P("“", 120, c["accent"], "heading", True)], line=1.0))
    size = fit_size(quote, (w - 0.5) * 0.95, h - 2.6, 34, 18, "heading", 1.25)
    qh = est_lines(quote, size, (w - 0.5) * 0.95, "heading") * size / 72 * 1.3 + 0.2
    els.append(T(x + 0.15, y + 1.42, w - 0.5, qh, [P(quote, size, BH_INK, "heading", True)], line=1.25))
    if who:
        ry = y + 1.6 + qh
        els.append(R(x + 0.15, ry, 0.75, 0.07, c["accent3"]))
        els.append(T(x + 0.15, ry + 0.22, w - 0.5, 0.45, [P(who, 15, BH_INK, "body", True, caps=True, spacing=1)], line=1.1))


def _bh_process(frame: Frame, spec, els):
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    steps = spec.get("steps", [])
    if not steps:
        return
    x, y, w, h = frame.content_rect()
    n = len(steps)
    seg = w / n
    arrow_h = 1.0
    iw = seg - 0.35
    hs = min(fit_size((st["heading"] or " ").upper(), seg - 0.95, arrow_h - 0.24, 15, 10, "heading", 1.05) for st in steps)
    ts = 15
    while ts > 11 and max(text_h(st["text"], ts, iw, "body", 1.3) for st in steps) + arrow_h + 0.4 > h:
        ts -= 1
    text_block = max(text_h(st["text"], ts, iw, "body", 1.3) for st in steps)
    top = _top(y, h, arrow_h + 0.4 + text_block)
    for i, st in enumerate(steps):
        sx = x + i * seg
        acc = _bh_primaries(frame)[i % 3]
        els.append({"t": "shape", "geom": "homePlate" if i == 0 else "chevron", "x": sx, "y": top, "w": seg + 0.12, "h": arrow_h,
                    "fill": acc, "line": {"color": BH_INK, "width": 2.0}})
        pad_l = 0.22 if i == 0 else arrow_h * 0.45
        els.append(T(sx + pad_l, top, seg - pad_l - arrow_h * 0.3, arrow_h,
                     [P((st["heading"] or "").upper(), hs, readable(acc), "heading", True)], "c", "m", line=1.05))
        els.append(T(sx + 0.15, top + arrow_h + 0.4, iw, text_block + 0.2, [P(st["text"], ts, ink)], "c", line=1.3))


def _bh_decorate(frame: Frame, els: list):
    """Faint construction circle + the solid primary trio in the top-right corner."""
    W, mx = frame.W, frame.mx
    els.append(_bh_bleed(R(W - 1.2, -1.1, 2.2, 2.2, None, line={"color": "#D7D7D7", "width": 1.25}, shape="ellipse")))
    _bh_trio(frame, els, W - mx - 1.15, 0.36, frame.occ)



# ---------------------------------------------------------------- slide types

def _photo_hero(frame: Frame, spec: dict, els: list, img: dict, closing=False):
    """Title/closing/section with a full-bleed photo and a readable overlay."""
    W, H, mx, c = frame.W, frame.H, frame.mx, frame.c
    frame.bg = {"type": "solid", "color": "#000000"}
    els.append(IMG(0, 0, W, H, img))
    shade = c["bg"] if frame.theme.get("dark") else "#0B0F1A"
    els.append(R(0, 0, W * 0.62, H, shade, 0.82))
    els.append(R(W * 0.62, 0, W * 0.05, H, shade, 0.58))  # mid band: softens the hard photo/text seam
    els.append(R(W * 0.62, 0, W * 0.38, H, shade, 0.35))
    tw = W * 0.62 - 2 * mx
    title, sub, kicker = spec.get("title", ""), spec.get("subtitle", ""), spec.get("kicker", "")
    size = fit_size(title, tw, 2.4, 58 if len(title) <= 24 else 54, 28, "heading", 1.05, face=frame.f_head)
    th = est_lines(title, size, tw, "heading", frame.f_head) * size / 72 * 1.08 + 0.1
    y = max(0.8, (H - th - (1.2 if sub else 0) - (0.45 if kicker else 0)) / 2)
    if kicker:
        els.append(T(mx, y, tw, 0.35, [P(kicker.upper(), 13, c["accent"], "body", True, spacing=3)]))
        y += 0.45
    els.append(T(mx, y, tw, th, [P(title, size, "#FFFFFF", "heading", frame.heading_bold)], line=1.05))
    y += th + 0.25
    if sub:
        els.append(T(mx, y, tw, 1.2, [P(sub, fit_size(sub, tw, 1.2, 22, 14, face=frame.f_body), "#E6E9F2")], line=1.25))
        y += 1.3
    if spec.get("contact"):
        els.append(T(mx, y, tw, 0.4, [P(spec["contact"], 15, c["accent"], "body", True)]))
    if img.get("credit"):
        els.append(T(W - 4.6, H - 0.38, 4.4, 0.3, [P("Photo: " + img["credit"], 7.5, "#FFFFFF")], "r", "m", line=1.0))


def _hero(frame: Frame, spec: dict, els: list, closing=False):
    """Title & closing slides for built-in themes."""
    if frame.style == "bauhaus":
        return _bh_hero(frame, spec, els, closing)
    W, H, mx, c = frame.W, frame.H, frame.mx, frame.c
    if photo(spec):
        return _photo_hero(frame, spec, els, photo(spec), closing)
    style = (frame.dna.get("hero") if frame.dna else None) or frame.theme.get("title_style", "orb")
    title, sub = spec.get("title", ""), spec.get("subtitle", "")
    kicker = spec.get("kicker", "")
    contact = spec.get("contact", "")
    centered = style == "frame" or closing
    tx, tw = mx, W * 0.66
    if style == "orb":
        frame.bg = {"type": "gradient", "stops": [{"pos": 0, "color": c["bg"]}, {"pos": 100, "color": c["bg_alt"]}], "angle": 45}
        els.append(R(W - 5.4, -1.9, 7.2, 7.2, c["accent"], 0.20, shape="ellipse"))
        els.append(R(W - 2.9, 4.2, 4.4, 4.4, c["accent2"], 0.16, shape="ellipse"))
        els.append(R(W - 6.6, 4.9, 1.3, 1.3, c["accent3"], 0.22, shape="ellipse"))
    elif style == "split":
        frame.bg = {"type": "solid", "color": c["bg"]}
        panel = c["bg_alt"] if c["bg_alt"] != c["bg"] else c["accent"]
        els.append(R(W * 0.64, 0, W * 0.36, H, panel))
        els.append(R(W * 0.64 + 0.9, H * 0.5 - 1.6, 3.2, 3.2, c["accent"], 0.9, shape="ellipse"))
        els.append(R(W * 0.64 + 2.3, H * 0.5 - 0.2, 2.2, 2.2, c["accent2"], 0.85, shape="ellipse"))
        tw = W * 0.64 - mx - 0.5
    elif style == "bar":
        frame.bg = {"type": "solid", "color": c["bg"]}
        els.append(R(0, 0, 0.32, H, c["accent"]))
        els.append(R(mx + 0.2, H - 1.1, 2.2, 0.06, c["text"]))
        tx = mx + 0.2
        tw = W * 0.72
    else:  # frame
        frame.bg = {"type": "solid", "color": c["bg"]}
        els.append(R(0.4, 0.4, W - 0.8, H - 0.8, None, line={"color": c["accent"], "width": 1.5}))
        els.append(R(W / 2 - 0.5, H - 1.25, 1.0, 0.06, c["accent"]))
    if centered:
        tx, tw = mx * 2, W - 4 * mx
    align = "c" if centered else "l"
    size = fit_size(title, tw, 2.4, 60 if not closing else 54, 30, "heading", 1.05, face=frame.f_head)
    lines = est_lines(title, size, tw, "heading", frame.f_head)
    th = lines * size / 72 * 1.08 + 0.1
    sub_size = fit_size(sub, tw, 1.2, 22, 14, face=frame.f_body) if sub else 20
    sh = (est_lines(sub, sub_size, tw, "body", frame.f_body) * sub_size / 72 * 1.3 + 0.1) if sub else 0
    block = (0.45 if kicker else 0) + th + (0.25 + sh if sub else 0) + (0.6 if contact else 0)
    y = max(0.6, (H - block) / 2 - (0.1 if not centered else 0))
    if kicker:
        els.append(T(tx, y, tw, 0.35, [P(kicker.upper(), 13, c["accent"], "body", True, spacing=3)], align))
        y += 0.45
    els.append(T(tx, y, tw, th, [P(title, size, c["text"], "heading", frame.heading_bold)], align, line=1.05))
    y += th + 0.25
    if sub:
        els.append(T(tx, y, tw, sh, [P(sub, sub_size, c["muted"])], align, line=1.25))
        y += sh + 0.15
    if contact:
        els.append(T(tx, y + 0.1, tw, 0.4, [P(contact, 15, c["accent"], "body", True)], align))


def render_title(frame, spec, els, closing=False):
    if not frame.custom:
        return _hero(frame, spec, els, closing)
    if frame.base:
        content_title(frame, {"title": spec.get("title", "")}, els)
        x, y, w, h = frame.content_rect()
        lines = [P(spec.get("kicker", "").upper(), 14, frame.c["accent"], "body", True, spacing=2)] if spec.get("kicker") else []
        if spec.get("subtitle"):
            lines.append(P(spec["subtitle"], fit_size(spec["subtitle"], w, h * 0.5, 30, 16, "heading"), frame.c["text"], "heading", True, space=10))
        if spec.get("contact"):
            lines.append(P(spec["contact"], 18, frame.c["accent"], "body", True))
        if lines:
            els.append(T(x, y, w, h, lines, "c", "m", line=1.25))
        return
    title_ph = frame.ph("title")
    sub_ph = frame.ph("subtitle") or (frame.bodies()[0] if frame.bodies() else None)
    if title_ph:
        els.append(ph_text(title_ph, [(spec.get("title", ""), 0)], "title", frame))
    sub = spec.get("subtitle", "")
    extra = spec.get("contact", "") if closing else ""
    if sub_ph and (sub or extra):
        lines = [(sub, 0)] if sub else []
        if extra:
            lines.append((extra, 0))
        els.append(ph_text(sub_ph, lines, "subtitle", frame))
    if spec.get("kicker") and title_ph and title_ph["y"] > 0.8:
        els.append(T(title_ph["x"] + 0.1, title_ph["y"] - 0.5, title_ph["w"], 0.4,
                     [P(spec["kicker"].upper(), 12, frame.c["accent"], "body", True, spacing=2)], title_ph["style"].get("align", "l")[0] if title_ph["style"].get("align") in ("l", "r") else "l"))


def render_section(frame, spec, els, number: int):
    if frame.custom:
        return render_title(frame, spec, els)
    if photo(spec):
        return _photo_hero(frame, {**spec, "kicker": f"{number:02d}"}, els, photo(spec))
    if frame.style == "bauhaus":
        return _bh_section(frame, spec, els, number)
    W, H, mx, c = frame.W, frame.H, frame.mx, frame.c
    els.append(R(W - 3.4, H - 3.4, 5.0, 5.0, c["accent"], 0.18, shape="ellipse"))
    els.append(T(mx, 1.7, 3, 1.2, [P(f"{number:02d}", 64, c["accent"], "heading", True)], valign="b", line=1))
    els.append(R(mx, 3.05, 1.0, 0.07, c["accent"]))
    size = fit_size(spec.get("title", ""), W - 2 * mx - 2, 1.7, 48, 28, "heading")
    els.append(T(mx, 3.3, W - 2 * mx - 2, 1.7, [P(spec.get("title", ""), size, c["text"], "heading", frame.heading_bold)], line=1.05))
    if spec.get("subtitle"):
        els.append(T(mx, 5.05, W - 2 * mx - 3, 1.0, [P(spec["subtitle"], 20, c["muted"])], line=1.25))


def render_bullets(frame, spec, els):
    content_title(frame, spec, els)
    items = spec.get("bullets", [])
    if frame.base and frame.base_el(frame.base["body_key"]):
        lines = []
        for b in items:
            lines.append({"text": b["text"], "level": 1 if frame.base_has_levels else 0})  # noqa
            lines.extend({"text": x, "level": 2 if frame.base_has_levels else 1} for x in b["sub"])
        if lines:
            els.append(fill_text(frame.base_el(frame.base["body_key"]), lines))
        return
    if frame.custom:
        body = max(frame.bodies(), key=lambda p: p["w"] * p["h"], default=None)
        if body:
            lines = []
            for b in items:
                lines.append((b["text"], 0))
                lines.extend((s, 1) for s in b["sub"])
            if lines:
                els.append(ph_text(body, lines, "body", frame, bold=False))
            return
    x, y, w, h = frame.content_rect()
    c = frame.c
    if frame.style == "bauhaus":
        return _bh_bullets(frame, spec, els)
    style = frame.variant("bullets", design.BULLETS)
    if style != "dot" and items and len(items) <= 6:
        return _bullet_rows(frame, items, x, y, w, h, numbered=style == "numbered", els=els)
    paras_spec = []
    for b in items:
        paras_spec.append((b["text"], 1.0, 0.45))
        paras_spec.extend((s, 0.8, 0.9) for s in b["sub"])
    if not paras_spec:
        return
    size = fit_paras(paras_spec, w * 0.92, h, 26, 13, gap=0.7, face=frame.f_body)
    paras = []
    for b in items:
        paras.append(P(b["text"], size, c["text"], bullet=c["accent"], space=size * 0.55))
        for s in b["sub"]:
            paras.append(P(s, size * 0.8, c["muted"], bullet=c["muted"], level=1, space=size * 0.4))
    els.append(T(x, y + 0.1, w * 0.92, h - 0.1, paras, line=1.18))


def _bullet_rows(frame, items, x, y, w, h, numbered, els):
    """Each point as its own row: soft cards with an accent edge, or numbered badges."""
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    gap = 0.16 if not numbered else 0.22
    lead = 0.62 if numbered else 0.34
    tw = w - lead - 0.35

    def row_h(b, size):
        return max(0.5, text_h(b["text"], size, tw, "body", 1.22) + sum(text_h(x_, size * 0.85, tw, "body", 1.22) for x_ in b["sub"]) + 0.3)
    size = 22
    while size > 13 and sum(row_h(b, size) for b in items) + gap * (len(items) - 1) > h:
        size -= 1
    block = sum(row_h(b, size) for b in items) + gap * (len(items) - 1)
    yy = _top(y, h, block)
    for i, b in enumerate(items):
        rh = row_h(b, size)
        acc = accents[i % 4]
        if numbered:
            d = 0.46
            els.append(R(x, yy + (rh - d) / 2, d, d, acc, shape="ellipse"))
            els.append(T(x, yy + (rh - d) / 2, d, d, [P(str(i + 1), 15, readable(acc), "heading", True)], "c", "m"))
        else:
            els.append(R(x, yy, w, rh, c["surface"], radius=frame.rad(0.1)))
            els.append(R(x, yy, 0.07, rh, acc))
        paras = [P(b["text"], size, ink)] + [P(x_, size * 0.85, soft) for x_ in b["sub"]]
        els.append(T(x + lead, yy, tw, rh, paras, valign="m", line=1.22))
        yy += rh + gap


def _icon_badge(frame, els, x, y, size, item, i, acc, acc_txt):
    """Icon (or number) in the deck's badge style: tile, circle or bare icon."""
    style = frame.dna.get("icon_style", "tile") if frame.dna else "tile"
    if has_icon(item):
        if style == "plain":
            els.append(ICON(x, y, size, item["icon"], acc_txt))
            return
        shape = "ellipse" if style == "circle" else "rect"
        els.append(R(x, y, size, size, acc, 0.16, radius=0 if shape == "ellipse" else min(0.12, frame.rad(0.1)), shape=shape))
        els.append(ICON(x + size * 0.17, y + size * 0.17, size * 0.66, item["icon"], acc_txt))
    else:
        shape = "ellipse" if style == "circle" else "rect"
        els.append(R(x, y, size, size, acc, radius=0 if shape == "ellipse" else min(0.12, frame.rad(0.1)), shape=shape))
        els.append(T(x, y, size, size, [P(str(i + 1), 15, readable(acc), "heading", True)], "c", "m"))


def text_h(text: str, size: float, width: float, kind: str = "body", line: float = 1.2, face: str | None = None) -> float:
    return est_lines(text or " ", size, width, kind, face) * size / 72 * line


def palette(frame: Frame):
    """Readable ink for body text, a softer ink for details, and accent colors that work as text."""
    c = frame.c
    ink = c["text"] if contrast(c["text"], c["bg"]) >= 7 else mix(c["text"], readable(c["bg"], "#FFFFFF", "#000000"), 0.5)
    soft = mix(ink, c["bg"], 0.25)
    accents = [c["accent"], c["accent2"], c["accent3"], c["accent4"]]
    if frame.style == "bauhaus":  # pure primaries; yellow as text turns black instead of muddy gold
        acc_text = [a if contrast(a, c["surface"]) >= 3.2 else c["text"] for a in accents]
    else:
        acc_text = [a if contrast(a, c["surface"]) >= 3.2 else mix(a, ink, 0.55) for a in accents]
    return ink, soft, accents, acc_text


def _top(y: float, h: float, block: float) -> float:
    """Place a content block: centred a little high when it is clearly shorter than the area."""
    return y if block >= h * 0.88 else y + (h - block) * 0.4


def render_two_column(frame, spec, els):
    content_title(frame, spec, els)
    left, right = spec.get("left", {}), spec.get("right", {})
    c = frame.c
    if frame.custom and not frame.base:
        bodies = frame.bodies()
        big = [b for b in bodies if b["w"] * b["h"] > 0.1 * frame.W * frame.H]
        small = [b for b in bodies if b not in big]
        if len(big) >= 2:
            for col, ph in zip((left, right), big[:2]):
                heads = [s for s in small if abs(s["x"] - ph["x"]) < 0.6]
                lines = [(t, 0) for t in col.get("bullets", [])]
                if heads and col.get("heading"):
                    els.append(ph_text(heads[0], [(col["heading"], 0)], "subtitle", frame, bold=True))
                elif col.get("heading"):
                    lines.insert(0, (col["heading"], 0))
                if lines:
                    els.append(ph_text(ph, lines, "body", frame, bold=False))
            return
    x, y, w, h = frame.content_rect()
    ink, soft, accents, acc_text = palette(frame)
    if frame.style == "bauhaus":
        return _bh_two_col(frame, spec, els)
    style = frame.variant("two_col", design.TWO_COL)
    gap = 0.45 if style == "panels" else 0.8
    cw = (w - gap) / 2
    pad = 0.35 if style == "panels" else 0.05
    iw = cw - 2 * pad
    cols = (left, right)

    def need(size):
        return max(0.35 + text_h(col.get("heading", ""), size + 3, iw, "heading", 1.1) + 0.25
                   + sum(text_h(b, size, iw - size / 72 * 1.1, "body", 1.25) + size / 72 * 0.55 for b in col.get("bullets", []))
                   + 0.3 for col in cols)
    size = 20
    while size > 13 and need(size) > h:
        size -= 1
    panel_h = min(h, max(need(size), h * 0.5)) if style == "panels" else min(h, need(size))
    top = _top(y, h, panel_h)
    if style == "divider":
        els.append(R(x + cw + gap / 2 - 0.01, top, 0.02, panel_h, c["border"]))
    for i, col in enumerate(cols):
        cx = x + i * (cw + gap)
        acc = accents[i % 4]
        hh = text_h(col.get("heading", ""), size + 3, iw, "heading", 1.1)
        if style == "panels":
            els.append(R(cx + 0.045, top + 0.06, cw, panel_h, ink, alpha=0.09, radius=frame.rad()))
            els.append(R(cx, top, cw, panel_h, c["surface"], radius=frame.rad()))
            els.append(R(cx + pad, top, 1.2, 0.07, acc))
        els.append(T(cx + pad, top + 0.35, iw, hh, [P(col.get("heading", ""), size + 3, acc_text[i % 4], "heading", True)], line=1.1))
        if style == "divider":
            els.append(R(cx + pad, top + 0.35 + hh + 0.08, 0.6, 0.05, acc))
        paras = [P(t, size, ink, bullet=acc, space=size * 0.55) for t in col.get("bullets", [])]
        els.append(T(cx + pad, top + 0.35 + hh + 0.25, iw, panel_h - hh - 0.6, paras, line=1.25))


def render_cards(frame, spec, els):
    content_title(frame, spec, els)
    cards = spec.get("cards", [])
    if not cards:
        return
    x, y, w, h = frame.content_rect()
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    if frame.style == "bauhaus":
        return _bh_cards(frame, spec, els)
    style = frame.variant("card", design.CARD)
    if style == "list":
        return _cards_list(frame, cards, x, y, w, h, els)
    if style in ("numeral", "centered"):
        return _cards_open(frame, cards, x, y, w, h, els, centered=style == "centered")
    n = len(cards)
    longest = max(len(cd["text"]) for cd in cards)
    cols = n if n <= 3 else (4 if (n == 4 and longest < 70 and w > 10) else (2 if n == 4 else 3))
    rows = math.ceil(n / cols)
    gap = 0.3
    cw = (w - gap * (cols - 1)) / cols
    iw = cw - 0.6
    row_avail = (h - gap * (rows - 1)) / rows
    badge = 0.46

    def head_h(cd, hs):
        return max(badge, text_h(cd["heading"], hs, iw - badge - 0.18, "heading", 1.1))

    def need(cd, hs, ts):  # badge sits beside the heading, so the body text keeps its room
        return 0.28 + head_h(cd, hs) + 0.16 + text_h(cd["text"], ts, iw, "body", 1.3) + 0.3
    hs, ts = 22, 18
    while max(need(cd, hs, ts) for cd in cards) > row_avail and (ts > 13 or hs > 15):
        ts = max(13, ts - 1)
        if hs - ts > 3 or ts == 13:
            hs = max(15, hs - 1)
    card_h = min(row_avail, max(need(cd, hs, ts) for cd in cards))
    block = rows * card_h + gap * (rows - 1)
    top = _top(y, h, block)
    rad = frame.rad()
    for i, cd in enumerate(cards):
        r, col = divmod(i, cols)
        in_row = cols if r < rows - 1 else n - cols * (rows - 1)
        cx = x + (cols - in_row) * (cw + gap) / 2 + col * (cw + gap)
        cy = top + r * (card_h + gap)
        acc = accents[i % 4]
        hh = head_h(cd, hs)
        text_col, head_col = ink, acc_text[i % 4]
        if style != "outline":  # soft offset shadow: the one elevation trick all three renderers draw
            els.append(R(cx + 0.045, cy + 0.06, cw, card_h, ink, alpha=0.09, radius=rad))
        if style == "outline":
            els.append(R(cx, cy, cw, card_h, None, radius=rad, line={"color": acc, "width": 1.5}))
        elif style == "filled":
            els.append(R(cx, cy, cw, card_h, mix(acc, c["bg"], 0.84), radius=rad))
        else:
            els.append(R(cx, cy, cw, card_h, c["surface"], radius=rad, line={"color": c["border"], "width": 0.75} if style == "soft" else None))
            if style == "top_bar":
                els.append(R(cx, cy, cw, 0.08, acc))
            elif style == "left_bar":
                els.append(R(cx, cy, 0.08, card_h, acc))
        _icon_badge(frame, els, cx + 0.3, cy + 0.28 + (hh - badge) / 2, badge, cd, i, acc, acc_text[i % 4])
        els.append(T(cx + 0.3 + badge + 0.18, cy + 0.28, iw - badge - 0.18, hh, [P(cd["heading"], hs, head_col, "heading", True)], valign="m", line=1.1))
        ty = cy + 0.28 + hh + 0.16
        els.append(T(cx + 0.3, ty, iw, max(0.3, cy + card_h - ty - 0.22), [P(cd["text"], ts, text_col)], line=1.3))


def _cards_list(frame, cards, x, y, w, h, els):
    """Cards as full-width rows: icon badge, heading, then text beside it."""
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    n = len(cards)
    cols = 2 if n > 4 else 1
    gap = 0.2
    cw = (w - 0.4 * (cols - 1)) / cols
    per_col = math.ceil(n / cols)
    badge = 0.56
    head_w = min(3.2, cw * 0.3) if cols == 1 else cw - badge - 0.6
    text_w = cw - badge - 0.55 - (head_w + 0.3 if cols == 1 else 0)

    def row_h(cd, hs, ts):
        if cols == 1:
            return max(badge + 0.3, text_h(cd["heading"], hs, head_w, "heading", 1.1) + 0.3, text_h(cd["text"], ts, text_w, "body", 1.3) + 0.3)
        return max(badge + 0.3, text_h(cd["heading"], hs, head_w, "heading", 1.1) + text_h(cd["text"], ts, cw - 0.5, "body", 1.3) + 0.45)
    hs, ts = 20, 16
    while max(sum(row_h(cd, hs, ts) for cd in cards[k * per_col:(k + 1) * per_col]) for k in range(cols)) + gap * (per_col - 1) > h and ts > 11:
        ts, hs = ts - 1, max(14, hs - 1)
    block = max(sum(row_h(cd, hs, ts) for cd in cards[k * per_col:(k + 1) * per_col]) for k in range(cols)) + gap * (per_col - 1)
    top = _top(y, h, block)
    for k in range(cols):
        yy = top
        cx = x + k * (cw + 0.4)
        for j, cd in enumerate(cards[k * per_col:(k + 1) * per_col]):
            i = k * per_col + j
            rh = row_h(cd, hs, ts)
            acc = accents[i % 4]
            els.append(R(cx + 0.045, yy + 0.06, cw, rh, ink, alpha=0.09, radius=frame.rad(0.1)))
            els.append(R(cx, yy, cw, rh, c["surface"], radius=frame.rad(0.1)))
            _icon_badge(frame, els, cx + 0.22, yy + (rh - badge) / 2 if cols == 1 else yy + 0.18, badge, cd, i, acc, acc_text[i % 4])
            hx = cx + 0.22 + badge + 0.25
            if cols == 1:
                els.append(T(hx, yy, head_w, rh, [P(cd["heading"], hs, acc_text[i % 4], "heading", True)], valign="m", line=1.1))
                els.append(T(hx + head_w + 0.3, yy, text_w, rh, [P(cd["text"], ts, ink)], valign="m", line=1.3))
            else:
                hh = text_h(cd["heading"], hs, head_w, "heading", 1.1)
                els.append(T(hx, yy + 0.18, head_w, max(hh, badge), [P(cd["heading"], hs, acc_text[i % 4], "heading", True)], valign="m", line=1.1))
                els.append(T(cx + 0.22, yy + 0.3 + max(hh, badge), cw - 0.44, rh - max(hh, badge) - 0.35, [P(cd["text"], ts, ink)], line=1.3))
            yy += rh + gap


def _cards_open(frame, cards, x, y, w, h, els, centered=False):
    """Boxless cards with big numerals ("01") or centered cards with a round icon on top."""
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    n = len(cards)
    cols = n if n <= 4 else 3
    rows = math.ceil(n / cols)
    gap = 0.35
    cw = (w - gap * (cols - 1)) / cols
    iw = cw - (0.5 if centered else 0.1)
    row_avail = (h - gap * (rows - 1)) / rows
    lead = 0.95 if centered else 0.85

    def need(cd, hs, ts):
        return (0.3 if centered else 0) + lead + 0.15 + text_h(cd["heading"], hs, iw, "heading", 1.1) + 0.12 + text_h(cd["text"], ts, iw, "body", 1.3) + 0.3
    hs, ts = 22, 17
    while max(need(cd, hs, ts) for cd in cards) > row_avail and (ts > 12 or hs > 15):
        ts, hs = max(12, ts - 1), max(15, hs - 1)
    card_h = min(row_avail, max(need(cd, hs, ts) for cd in cards))
    top = _top(y, h, rows * card_h + gap * (rows - 1))
    align = "c" if centered else "l"
    for i, cd in enumerate(cards):
        r, col = divmod(i, cols)
        in_row = cols if r < rows - 1 else n - cols * (rows - 1)
        cx = x + (cols - in_row) * (cw + gap) / 2 + col * (cw + gap)
        cy = top + r * (card_h + gap)
        acc = accents[i % 4]
        tx = cx + (0.25 if centered else 0.05)
        if centered:
            els.append(R(cx, cy, cw, card_h, c["surface"], radius=frame.rad()))
            d = 0.8
            bx = cx + (cw - d) / 2
            els.append(R(bx, cy + 0.3, d, d, acc, shape="ellipse"))
            if has_icon(cd):
                els.append(ICON(bx + d * 0.24, cy + 0.3 + d * 0.24, d * 0.52, cd["icon"], readable(acc)))
            else:
                els.append(T(bx, cy + 0.3, d, d, [P(str(i + 1), 22, readable(acc), "heading", True)], "c", "m"))
            yy = cy + 0.3 + lead + 0.15
        else:
            els.append(T(tx, cy, iw, 0.75, [P(f"{i + 1:02d}", 40, acc_text[i % 4], "heading", True)], valign="b", line=1.0))
            els.append(R(tx, cy + 0.8, 0.5, 0.05, acc))
            yy = cy + lead + 0.15
        hh = text_h(cd["heading"], hs, iw, "heading", 1.1)
        els.append(T(tx, yy, iw, hh, [P(cd["heading"], hs, ink if not centered else acc_text[i % 4], "heading", True)], align, line=1.1))
        els.append(T(tx, yy + hh + 0.12, iw, max(0.3, cy + card_h - yy - hh - 0.25), [P(cd["text"], ts, soft if not centered else ink)], align, line=1.3))


def render_stats(frame, spec, els):
    content_title(frame, spec, els)
    stats = spec.get("stats", [])
    if not stats:
        return
    x, y, w, h = frame.content_rect()
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    if frame.style == "bauhaus":
        return _bh_stats(frame, spec, els)
    style = frame.variant("stats", design.STATS)
    n = len(stats)
    gap = 0.35
    cw = (w - gap * (n - 1)) / n
    iw = cw - 0.7
    centered = style != "cards"
    if style == "rings":
        ring = min(cw - 0.6, 2.2, h * 0.5)
        vs = min(max(20, min(44, (ring - 0.4) / max(len(s["value"] or "0"), 1) / 0.62 * 72)) for s in stats)
    else:
        vs = min(max(26, min(64 if n <= 3 else 52, iw / max(len(s["value"] or "0"), 1) / 0.62 * 72)) for s in stats)
    ls, ds = 20, 15
    icon_h = 0.62 if any(has_icon(st) for st in stats) and style != "rings" else 0
    head = ring + 0.25 if style == "rings" else icon_h + vs / 72 * 1.05

    def need(st):
        return (0.4 + head + 0.15 + text_h(st["label"], ls, iw, "heading", 1.1)
                + (0.15 + text_h(st.get("detail", ""), ds, iw, "body", 1.3) if st.get("detail") else 0) + 0.35)
    while max(need(st) for st in stats) > h and ds > 11:
        ds -= 1
        ls = max(14, ls - 1)
    card_h = min(h, max(need(st) for st in stats))
    top = _top(y, h, card_h)
    align = "c" if centered else "l"
    for i, st in enumerate(stats):
        cx = x + i * (cw + gap)
        acc = accents[i % 4]
        tx = cx + (0.35 if centered else 0.4)
        if style == "cards":
            els.append(R(cx + 0.045, top + 0.06, cw, card_h, ink, alpha=0.09, radius=frame.rad()))
            els.append(R(cx, top, cw, card_h, c["surface"], radius=frame.rad()))
            els.append(R(cx, top + 0.3, 0.08, card_h - 0.6, acc))
        elif style == "dividers" and i:
            els.append(R(cx - gap / 2 - 0.01, top + 0.3, 0.02, card_h - 0.6, c["border"]))
        yy = top + 0.4
        if style == "rings":
            rx = cx + (cw - ring) / 2
            els.append(R(rx, yy, ring, ring, None, shape="ellipse", line={"color": acc, "width": 7}))
            els.append(T(rx, yy, ring, ring, [P(st["value"], vs, acc_text[i % 4], "heading", True)], "c", "m", line=1.0))
            yy += ring + 0.25
        else:
            if has_icon(st):
                els.append(ICON(cx + (cw - 0.46) / 2 if centered else tx, yy, 0.46, st["icon"], acc_text[i % 4]))
            yy += icon_h
            els.append(T(tx, yy, iw, vs / 72 * 1.05, [P(st["value"], vs, acc_text[i % 4], "heading", True)], align, line=1.0))
            yy += vs / 72 * 1.05 + 0.15
        lh = text_h(st["label"], ls, iw, "heading", 1.1)
        els.append(T(tx, yy, iw, lh, [P(st["label"], ls, ink, "heading", True)], align, line=1.1))
        yy += lh + 0.15
        if st.get("detail"):
            els.append(T(tx, yy, iw, max(0.3, top + card_h - yy - 0.2), [P(st["detail"], ds, soft)], align, line=1.3))


def render_timeline(frame, spec, els):
    frame._els = els
    content_title(frame, spec, els)
    steps = spec.get("steps", [])
    if not steps:
        return
    x, y, w, h = frame.content_rect()
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    if frame.style == "bauhaus":
        return _bh_timeline(frame, spec, els)
    n = len(steps)
    style = frame.variant("timeline", design.TIMELINE)
    avg = sum(len(st["text"]) for st in steps) / n
    if style == "vertical" and n <= 6 and avg <= 140:
        return _timeline_vertical(frame, steps, x, y, w, h)
    if n >= 6 and (avg > 90 or style == "grid"):  # grids leave holes on short/odd counts - the line never does
        return _timeline_grid(frame, steps, x, y, w, h)
    seg = w / n
    iw = seg - 0.6
    head = 0.42 + 0.2 + 0.4 + (0.15 if any(has_icon(st) for st in steps) else 0)  # label row, line + dot, gap

    def card_need(st, hs, ts):
        return 0.25 + text_h(st["heading"], hs, iw, "heading", 1.1) + 0.1 + text_h(st["text"], ts, iw, "body", 1.3) + 0.25
    hs, ts = 19, 15
    while head + max(card_need(st, hs, ts) for st in steps) > h and (ts > 11 or hs > 14):
        ts, hs = max(11, ts - 1), max(14, hs - 1)
    card_h = min(h - head, max(card_need(st, hs, ts) for st in steps))
    top = _top(y, h, head + card_h)
    line_y = top + 0.42 + 0.2 + (0.12 if any(has_icon(st) for st in steps) else 0)
    els.append(R(x + seg / 2, line_y - 0.025, w - seg, 0.05, c["border"]))
    for i, st in enumerate(steps):
        cx = x + i * seg
        mid = cx + seg / 2
        acc = accents[i % 4]
        els.append(T(cx + 0.1, top, seg - 0.2, 0.42, [P(st["label"], 14, acc_text[i % 4], "body", True)], "c", "b"))
        if has_icon(st):
            els.append(R(mid - 0.3, line_y - 0.3, 0.6, 0.6, acc, shape="ellipse"))
            els.append(ICON(mid - 0.19, line_y - 0.19, 0.38, st["icon"], readable(acc)))
        else:
            els.append(R(mid - 0.17, line_y - 0.17, 0.34, 0.34, acc, shape="ellipse"))
            els.append(R(mid - 0.07, line_y - 0.07, 0.14, 0.14, c["bg"], shape="ellipse"))
        ty = line_y + 0.4
        els.append(R(cx + 0.12, ty, seg - 0.24, card_h, c["surface"], radius=0.1))
        els.append(R(cx + 0.12, ty, seg - 0.24, 0.06, acc))
        hh = text_h(st["heading"], hs, iw, "heading", 1.1)
        els.append(T(cx + 0.3, ty + 0.25, iw, hh, [P(st["heading"], hs, ink, "heading", True)], "c", line=1.1))
        els.append(T(cx + 0.3, ty + 0.25 + hh + 0.1, iw, max(0.3, card_h - hh - 0.5), [P(st["text"], ts, soft)], "c", line=1.3))


def _timeline_vertical(frame, steps, x, y, w, h):
    """Steps down a vertical spine: label, dot, then heading and text on the right."""
    els = frame._els
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    n = len(steps)
    lab_w = min(2.0, w * 0.18)
    tx = x + lab_w + 0.75
    tw = w - lab_w - 0.75

    def row(st, hs, ts):
        return max(0.6, text_h(st["heading"], hs, tw, "heading", 1.1) + 0.05 + text_h(st["text"], ts, tw, "body", 1.25)) + 0.22
    hs, ts = 19, 15
    while sum(row(st, hs, ts) for st in steps) > h and ts > 11:
        ts, hs = ts - 1, max(14, hs - 1)
    if sum(row(st, hs, ts) for st in steps) > h:  # too much text for one column: use the two-row grid
        return _timeline_grid(frame, steps, x, y, w, h)
    block = sum(row(st, hs, ts) for st in steps)
    yy = _top(y, h, block)
    spine_x = x + lab_w + 0.3
    els.append(R(spine_x - 0.02, yy + 0.2, 0.04, block - 0.4, c["border"]))
    for i, st in enumerate(steps):
        rh = row(st, hs, ts)
        acc = accents[i % 4]
        els.append(T(x, yy, lab_w, 0.4, [P(st["label"], 14, acc_text[i % 4], "body", True)], "r", "m"))
        if has_icon(st):
            els.append(R(spine_x - 0.25, yy - 0.05, 0.5, 0.5, acc, shape="ellipse"))
            els.append(ICON(spine_x - 0.16, yy + 0.04, 0.32, st["icon"], readable(acc)))
        else:
            els.append(R(spine_x - 0.15, yy + 0.05, 0.3, 0.3, acc, shape="ellipse"))
        hh = text_h(st["heading"], hs, tw, "heading", 1.1)
        els.append(T(tx, yy, tw, hh, [P(st["heading"], hs, ink, "heading", True)], line=1.1))
        els.append(T(tx, yy + hh + 0.05, tw, rh - hh - 0.2, [P(st["text"], ts, soft)], line=1.25))
        yy += rh


def _timeline_grid(frame, steps, x, y, w, h):
    """Many steps: two rows of numbered step cards joined by a flow line."""
    els = frame._els
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    n = len(steps)
    cols = math.ceil(n / 2)
    gap = 0.3
    cw = (w - gap * (cols - 1)) / cols
    iw = cw - 0.5
    row_avail = (h - 0.4) / 2

    def need(st, hs, ts):
        return 0.25 + 0.32 + 0.1 + text_h(st["heading"], hs, iw, "heading", 1.1) + 0.08 + text_h(st["text"], ts, iw, "body", 1.3) + 0.25
    hs, ts = 19, 15
    while max(need(st, hs, ts) for st in steps) > row_avail and (ts > 12 or hs > 14):
        ts, hs = max(12, ts - 1), max(14, hs - 1)
    card_h = min(row_avail, max(need(st, hs, ts) for st in steps))
    block = 2 * card_h + 0.4
    top = _top(y, h, block)
    last_row = (n - 1) // cols  # rows are filled left to right
    in_last = n - last_row * cols
    used_w = in_last * cw + (in_last - 1) * gap
    last_off = (w - used_w) / 2  # centre an incomplete last row instead of leaving a hole
    for i, st in enumerate(steps):
        r, col = divmod(i, cols)
        cx = x + col * (cw + gap) + (last_off if r == last_row else 0)
        cy = top + r * (card_h + 0.4)
        acc = accents[i % 4]
        if col < cols - 1 and i < n - 1:  # flow arrow to the next step
            els.append(R(cx + cw, cy + card_h / 2 - 0.02, gap, 0.04, c["border"]))
        els.append(R(cx, cy, cw, card_h, c["surface"], radius=0.1))
        els.append(R(cx, cy, 0.07, card_h, acc))
        els.append(T(cx + 0.25, cy + 0.22, iw, 0.32, [P(st["label"] or f"Step {i + 1}", 12.5, acc_text[i % 4], "body", True, spacing=1)], valign="m"))
        hh = text_h(st["heading"], hs, iw, "heading", 1.1)
        els.append(T(cx + 0.25, cy + 0.6, iw, hh, [P(st["heading"], hs, ink, "heading", True)], line=1.1))
        els.append(T(cx + 0.25, cy + 0.6 + hh + 0.08, iw, max(0.3, card_h - hh - 0.9), [P(st["text"], ts, soft)], line=1.3))


def render_chart(frame, spec, els):
    content_title(frame, spec, els)
    chart = spec.get("chart") or {}
    x, y, w, h = frame.content_rect()
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    take = spec.get("takeaway", "")
    cw = w * 0.64 if take else w
    if chart.get("categories") and chart.get("series"):
        els.append({"t": "chart", "x": x, "y": y + 0.1, "w": cw, "h": h - 0.1, "chart": chart,
                    "colors": accents + [mix(accents[0], ink, 0.4), mix(accents[1], ink, 0.4)],
                    "text": soft, "grid": c["border"], "bg": c["bg"]})
    if take:
        tx, tw = x + cw + 0.4, w - cw - 0.4
        ts = fit_size(take, tw - 0.7, h - 1.6, 20, 13, "heading", 1.3)
        th = text_h(take, ts, tw - 0.7, "heading", 1.3)
        box_h = min(h, 1.2 + th + 0.4)
        top = _top(y, h, box_h)
        els.append(R(tx, top, tw, box_h, c["surface"], radius=0.12))
        els.append(R(tx, top + 0.3, 0.08, box_h - 0.6, accents[0]))
        els.append(T(tx + 0.4, top + 0.4, tw - 0.7, 0.35, [P("KEY TAKEAWAY", 11, acc_text[0], "body", True, spacing=2)]))
        els.append(T(tx + 0.4, top + 0.9, tw - 0.7, th + 0.2, [P(take, ts, ink, "heading", True)], line=1.3))


def render_table(frame, spec, els):
    content_title(frame, spec, els)
    cols, rows = spec.get("columns", []), spec.get("rows", [])
    if not cols:
        return
    x, y, w, h = frame.content_rect()
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    n_rows = len(rows) + 1
    col_w = w / max(len(cols), 1) - 0.3
    size = 18
    while size > 11:
        tallest = max([text_h(v, size, col_w) for r in rows for v in r] + [text_h(v, size, col_w, "heading") for v in cols] + [0.2])
        if n_rows * (tallest + 0.25) <= h:
            break
        size -= 1
    row_h = min(0.8, max(0.5, h / n_rows), tallest + 0.25)
    top = _top(y, h, row_h * n_rows)
    if frame.style == "bauhaus":  # stark black header row, hairline grid
        els.append({"t": "table", "x": x, "y": top, "w": w, "h": row_h * n_rows, "columns": cols,
                    "rows": [r + [""] * (len(cols) - len(r)) for r in rows], "size": size,
                    "header_fill": c["text"], "header_text": readable(c["text"]), "text": ink,
                    "fill_a": "#FFFFFF", "fill_b": c["bg"], "border": c["border"]})
        return
    els.append({"t": "table", "x": x, "y": top, "w": w, "h": row_h * n_rows, "columns": cols,
                "rows": [r + [""] * (len(cols) - len(r)) for r in rows], "size": size,
                "header_fill": c["accent"], "header_text": readable(c["accent"]), "text": ink,
                "fill_a": c["surface"], "fill_b": c["bg"], "border": c["border"]})


def render_quote(frame, spec, els):
    W, H, c = frame.W, frame.H, frame.c
    quote, who = spec.get("quote", ""), spec.get("attribution", "")
    if frame.style == "bauhaus" and not frame.custom:
        return _bh_quote(frame, spec, els)
    if frame.custom:
        x, y, w, h = frame.content_rect()
        if frame.ph("title"):
            y, h = frame.ph("title")["y"], h + (y - frame.ph("title")["y"])
    else:
        x, y, w, h = frame.mx * 1.6, 1.0, W - frame.mx * 3.2, H - 2.0
        els.append(R(W - 2.8, -1.2, 4.2, 4.2, c["accent"], 0.15, shape="ellipse"))
    els.append(T(x, y, 1.5, 1.4, [P("“", 110, c["accent"], "heading", True)], line=1.0))
    size = fit_size(quote, w - 0.6, h - 2.4, 36, 18, "heading", 1.25)
    qh = est_lines(quote, size, w - 0.6, "heading") * size / 72 * 1.3 + 0.2
    els.append(T(x + 0.3, y + 1.35, w - 0.6, qh, [P(quote, size, c["text"], "heading", False, italic=True)], line=1.25))
    if who:
        els.append(R(x + 0.3, y + 1.55 + qh, 0.6, 0.05, c["accent"]))
        els.append(T(x + 0.3, y + 1.7 + qh, w - 0.6, 0.5, [P(who, 16, c["muted"], "body", True)]))


def render_image(frame, spec, els):
    """Photo on one side, title and points on the other."""
    side = spec.get("side", "right")
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    items = spec.get("bullets", [])
    if frame.custom:  # inside the template's frame
        content_title(frame, spec, els)
        x, y, w, h = frame.content_rect()
        iw_ = w * 0.46
        ix = x if side == "left" else x + w - iw_
        photo_slot(els, ix, y, iw_, h, spec, frame, radius=0.1)
        tx, tw, ty, th = (x + iw_ + 0.4 if side == "left" else x), w - iw_ - 0.4, y, h
    else:
        W, H, mx = frame.W, frame.H, frame.mx
        iw_ = W * 0.46
        ix = 0 if side == "left" else W - iw_
        photo_slot(els, ix, 0, iw_, H, spec, frame)
        tx = (iw_ + mx * 0.8) if side == "left" else mx
        tw = W - iw_ - mx * 1.8
        title = spec.get("title", "")
        ts = fit_size(title, tw, 1.5, 36, 24, "heading", 1.05)
        tth = est_lines(title, ts, tw, "heading") * ts / 72 * 1.08 + 0.05
        els.append(T(tx, 0.8, tw, tth, [P(title, ts, c["text"], "heading", frame.heading_bold)], line=1.05))
        els.append(R(tx, 0.8 + tth + 0.15, 0.7, 0.06, c["accent"]))
        ty = 0.8 + tth + 0.5
        th = H - ty - 0.7
    paras = []
    if spec.get("text"):
        paras.append(P(spec["text"], 18, ink, space=10))
    lines = [(b["text"], 1.0, 0.4) for b in items] + [(s_, 0.85, 0.8) for b in items for s_ in b["sub"]]
    size = fit_paras(lines or [(spec.get("text", ""), 1, 0)], tw, th - (0.6 if spec.get("text") else 0), 22, 10, gap=0.6)
    for b in items:
        paras.append(P(b["text"], size, ink, bullet=c["accent"], space=size * 0.55))
        for s_ in b["sub"]:
            paras.append(P(s_, size * 0.85, soft, bullet=soft, level=1, space=size * 0.4))
    if paras:
        block = _text_height(paras, tw, 1.22)
        els.append(T(tx, _top(ty, th, block), tw, min(th, block + 0.3), paras, line=1.22))


def render_matrix(frame, spec, els):
    """2x2 grid such as SWOT or impact/effort."""
    content_title(frame, spec, els)
    quads = (spec.get("quadrants", []) + [{"heading": "", "text": "", "icon": ""}] * 4)[:4]
    x, y, w, h = frame.content_rect()
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    if frame.style == "bauhaus":
        return _bh_matrix(frame, spec, els)
    lx = 0
    ty_ = 0.34 if spec.get("y_axis") else 0
    by = 0.4 if spec.get("x_axis") else 0
    if ty_:
        els.append(T(x, y, w, ty_, [P("↑  " + spec["y_axis"], 12, soft, "body", True)], valign="m"))
        y, h = y + ty_, h - ty_
    gap = 0.2
    cw, ch = (w - lx - gap) / 2, (h - by - gap) / 2
    iw = cw - 0.6

    def need(q, hs, ts):
        return 0.28 + max(0.42 if has_icon(q) else 0, text_h(q["heading"], hs, iw - (0.55 if has_icon(q) else 0), "heading", 1.1)) + 0.12 + text_h(q["text"], ts, iw, "body", 1.3) + 0.25
    hs, ts = 21, 16
    while max(need(q, hs, ts) for q in quads) > ch and ts > 11:
        ts, hs = ts - 1, max(14, hs - 1)
    for i, q in enumerate(quads):
        r, col = divmod(i, 2)
        qx, qy = x + lx + col * (cw + gap), y + r * (ch + gap)
        acc = accents[i % 4]
        if frame.variant("matrix", design.MATRIX) == "outline":
            els.append(R(qx, qy, cw, ch, None, radius=frame.rad(), line={"color": acc, "width": 1.5}))
        else:
            els.append(R(qx, qy, cw, ch, mix(acc, c["bg"], 0.86), radius=frame.rad()))
            els.append(R(qx, qy, 0.08, ch, acc))
        hx = qx + 0.3
        if has_icon(q):
            els.append(ICON(hx, qy + 0.28, 0.42, q["icon"], acc_text[i % 4]))
            hx += 0.55
        hh = max(0.42 if has_icon(q) else 0, text_h(q["heading"], hs, qx + cw - 0.3 - hx, "heading", 1.1))
        els.append(T(hx, qy + 0.28, qx + cw - 0.3 - hx, hh, [P(q["heading"], hs, acc_text[i % 4], "heading", True)], valign="m", line=1.1))
        els.append(T(qx + 0.3, qy + 0.28 + hh + 0.12, iw, max(0.3, ch - hh - 0.6), [P(q["text"], ts, ink)], line=1.3))
    if spec.get("x_axis"):
        els.append(T(x + lx, y + h - by + 0.05, w - lx, by - 0.05, [P(spec["x_axis"] + "  →", 12, soft, "body", True)], "c", "m"))



def render_process(frame, spec, els):
    """Chevron flow: numbered arrows with a short description under each."""
    content_title(frame, spec, els)
    steps = spec.get("steps", [])
    if not steps:
        return
    x, y, w, h = frame.content_rect()
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    if frame.style == "bauhaus":
        return _bh_process(frame, spec, els)
    n = len(steps)
    seg = w / n
    arrow_h = 1.05
    iw = seg - 0.35
    has_icons = any(has_icon(st) for st in steps)
    if frame.variant("process", design.PROCESS) == "circles":
        return _process_circles(frame, steps, x, y, w, h, els)
    hs = min(fit_size(st["heading"] or " ", seg - 0.9, arrow_h - 0.2, 18, 11, "heading", 1.05) for st in steps)
    ts = 16
    while ts > 11 and max(text_h(st["text"], ts, iw, "body", 1.3) for st in steps) + arrow_h + 0.4 + (0.6 if has_icons else 0) > h:
        ts -= 1
    text_block = max(text_h(st["text"], ts, iw, "body", 1.3) for st in steps)
    top = _top(y, h, arrow_h + 0.35 + (0.6 if has_icons else 0) + text_block)
    for i, st in enumerate(steps):
        sx = x + i * seg
        acc = accents[i % 4]
        els.append({"t": "shape", "geom": "homePlate" if i == 0 else "chevron", "x": sx, "y": top, "w": seg + 0.12, "h": arrow_h, "fill": acc})
        pad_l = 0.25 if i == 0 else arrow_h * 0.45
        els.append(T(sx + pad_l, top, seg - pad_l - arrow_h * 0.3, arrow_h, [P(st["heading"], hs, readable(acc), "heading", True)], "c", "m", line=1.05))
        yy = top + arrow_h + 0.3
        if has_icon(st):
            els.append(ICON(sx + seg / 2 - 0.24, yy, 0.48, st["icon"], acc_text[i % 4]))
        yy += 0.6 if has_icons else 0
        els.append(T(sx + 0.15, yy, iw, text_block + 0.2, [P(st["text"], ts, ink)], "c", line=1.3))


def _process_circles(frame, steps, x, y, w, h, els):
    """Numbered (or icon) circles joined by a line, heading and text under each."""
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    n = len(steps)
    seg = w / n
    d = min(1.1, seg * 0.42)
    iw = seg - 0.35
    hs = min(fit_size(st["heading"] or " ", iw, 0.7, 19, 12, "heading", 1.1) for st in steps)
    ts = 16
    while ts > 11 and max(text_h(st["text"], ts, iw, "body", 1.3) for st in steps) + d + 1.1 > h:
        ts -= 1
    text_block = max(text_h(st["text"], ts, iw, "body", 1.3) for st in steps)
    head_block = max(text_h(st["heading"], hs, iw, "heading", 1.1) for st in steps)
    top = _top(y, h, d + 0.3 + head_block + 0.12 + text_block)
    els.append(R(x + seg / 2, top + d / 2 - 0.02, w - seg, 0.04, c["border"]))
    for i, st in enumerate(steps):
        cx = x + i * seg + (seg - d) / 2
        acc = accents[i % 4]
        els.append(R(cx, top, d, d, acc, shape="ellipse"))
        if has_icon(st):
            els.append(ICON(cx + d * 0.25, top + d * 0.25, d * 0.5, st["icon"], readable(acc)))
        else:
            els.append(T(cx, top, d, d, [P(str(i + 1), d * 30, readable(acc), "heading", True)], "c", "m", line=1.0))
        yy = top + d + 0.3
        els.append(T(x + i * seg + 0.17, yy, iw, head_block, [P(st["heading"], hs, acc_text[i % 4], "heading", True)], "c", line=1.1))
        els.append(T(x + i * seg + 0.17, yy + head_block + 0.12, iw, text_block + 0.2, [P(st["text"], ts, ink)], "c", line=1.3))


def render_funnel(frame, spec, els):
    """Narrowing bars (sales / conversion funnel) with descriptions on the right."""
    content_title(frame, spec, els)
    stages = spec.get("stages", [])
    if not stages:
        return
    x, y, w, h = frame.content_rect()
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    n = len(stages)
    gap = 0.14
    bh = min(0.95, (h - gap * (n - 1)) / n)
    block = n * bh + gap * (n - 1)
    top = _top(y, h, block)
    fw = w * 0.5
    for i, st in enumerate(stages):
        bw = fw * (1 - 0.5 * i / max(n - 1, 1))
        bx = x + (fw - bw) / 2
        by = top + i * (bh + gap)
        acc = accents[i % 4]
        els.append(R(bx, by, bw, bh, acc, radius=0.08))
        label = st["label"] + (f"  {st['value']}" if st.get("value") else "")
        els.append(T(bx + 0.15, by, bw - 0.3, bh, [P(label, fit_size(label, bw - 0.3, bh, 18, 10, "heading", 1.0), readable(acc), "heading", True)], "c", "m", line=1.0))
        if st.get("text"):
            tx = x + fw + 0.45
            els.append(R(tx - 0.3, by + bh / 2 - 0.02, 0.22, 0.04, c["border"]))
            els.append(T(tx, by, w - fw - 0.45, bh, [P(st["text"], fit_size(st["text"], w - fw - 0.45, bh, 16, 11), ink)], valign="m", line=1.25))


def render_quiz(frame, spec, els):
    """Question with lettered answers; interactive when presenting in the browser."""
    content_title(frame, spec, els)
    opts = spec.get("options", [])
    if not opts:
        return
    x, y, w, h = frame.content_rect()
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    n = len(opts)
    cols = 2 if n == 4 else 1
    rows = math.ceil(n / cols)
    gap = 0.22
    cw = (w - gap * (cols - 1)) / cols
    oh = min(1.0, (h - 0.7 - gap * (rows - 1)) / rows)
    size = min(fit_size(o, cw - 1.3, oh - 0.15, 20, 12) for o in opts)
    block = rows * oh + gap * (rows - 1)
    top = _top(y, h - 0.7, block)
    for i, o in enumerate(opts):
        r, col = divmod(i, cols)
        ox, oy = x + col * (cw + gap), top + r * (oh + gap)
        acc = accents[i % 4]
        bh = frame.style == "bauhaus"
        box = R(ox, oy, cw, oh, c["surface"], radius=0 if bh else 0.12,
                line={"color": c["border"], "width": 2 if bh else 1})
        box["quiz"] = {"i": i, "correct": i == spec.get("answer", 0)}
        els.append(box)
        els.append(R(ox + 0.2, oy + (oh - 0.5) / 2, 0.5, 0.5, acc, shape="ellipse",
                     line={"color": c["border"], "width": 1.5} if bh else None))
        els.append(T(ox + 0.2, oy + (oh - 0.5) / 2, 0.5, 0.5, [P("ABCDE"[i], 16, readable(acc), "heading", True)], "c", "m"))
        els.append(T(ox + 0.9, oy, cw - 1.1, oh, [P(o, size, ink)], valign="m", line=1.2))
    if spec.get("explanation"):
        ex = T(x, top + block + 0.2, w, 0.55, [P(f"Answer {'ABCDE'[spec.get('answer', 0)]}: " + spec["explanation"], 14, soft, italic=True)], valign="m")
        ex["quiz_explain"] = True
        els.append(ex)


def _fit_box(avail_w: float, avail_h: float, iw: float, ih: float) -> tuple[float, float]:
    """Largest w x h with the source's aspect ratio that fits the available box."""
    if not iw or not ih or iw <= 0 or ih <= 0:
        return avail_w, avail_h
    ar = iw / ih
    w, h = avail_w, avail_w / ar
    if h > avail_h:
        h, w = avail_h, avail_h * ar
    return w, h


def render_document(frame, spec, els):
    """The real pages of a document the user attached, shown as page images.

    A certificate or offer letter looks like itself here - a photograph of the
    page, not a retyped summary of it."""
    content_title(frame, spec, els)
    pages = [p for p in (spec.get("page_images") or []) if p.get("src")]
    x, y, w, h = frame.content_rect()
    c = frame.c
    caption = spec.get("caption", "")
    cap_h = 0.5 if caption else 0.0
    if not pages:
        els.append(R(x, y, w, h - cap_h, c["surface"], radius=0.1, line={"color": c["border"], "width": 1}))
        els.append(T(x, y, w, h - cap_h, [P("No page of that document is available", 16, c["muted"])], "c", "m"))
        if caption:
            els.append(T(x, y + h - cap_h, w, cap_h, [P(caption, 13, c["muted"], italic=True)], "c", "m"))
        return
    gap = 0.3
    n = len(pages)
    bw = (w - gap * (n - 1)) / n
    bh = h - cap_h
    # one page gets the whole area (a portrait letter is limited by height, not width,
    # so padding it further only makes it smaller); several sit side by side with a margin
    pad = 0.08 if n == 1 else 0.3
    for i, page in enumerate(pages):
        pw, ph = _fit_box(bw - pad, bh - pad, page.get("w") or 0, page.get("h") or 0)
        px = x + i * (bw + gap) + (bw - pw) / 2
        py = y + (bh - ph) / 2
        # a paper shadow so the page reads as a physical sheet on the slide
        els.append(R(px + 0.05, py + 0.06, pw, ph, "#000000", alpha=0.28 if luminance(c["bg"]) < 0.5 else 0.16, radius=0.04))
        els.append({"t": "image", "x": px, "y": py, "w": pw, "h": ph, "src": page["src"], "fit": "contain"})
        els.append(R(px, py, pw, ph, "#FFFFFF", alpha=0.0,
                     line={"color": c["border"], "width": 0.75}, radius=0.04))
    if caption:
        els.append(T(x, y + h - cap_h, w, cap_h,
                     [P(caption, fit_size(caption, w, cap_h, 14, 10), c["muted"], italic=True)], "c", "m", line=1.15))


def _node_box(cx, cy, w, h, tone, frame, accent):
    """A rounded panel for one diagram node, in the deck's own colours."""
    c = frame.c
    fill = mix(c["surface"], accent, 0.10 + 0.06 * (tone % 3))
    return R(cx - w / 2, cy - h / 2, w, h, fill, radius=0.12,
             line={"color": mix(c["border"], accent, 0.35), "width": 1})


def _clip(p_from, p_to, hw_a, hh_a, hw_b, hh_b, gap=0.04):
    """Shorten a centre-to-centre line so it stops just outside both node boxes.

    Without this the arrowhead is hidden underneath the panel it points at."""
    (x1, y1), (x2, y2) = p_from, p_to
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return p_from, p_to
    ux, uy = dx / dist, dy / dist
    # how far from each centre the line leaves that node's box
    out_a = min((hw_a / abs(ux) if abs(ux) > 1e-6 else 1e9), (hh_a / abs(uy) if abs(uy) > 1e-6 else 1e9), dist / 2)
    out_b = min((hw_b / abs(ux) if abs(ux) > 1e-6 else 1e9), (hh_b / abs(uy) if abs(uy) > 1e-6 else 1e9), dist / 2)
    a = (x1 + ux * (out_a + gap), y1 + uy * (out_a + gap))
    b = (x2 - ux * (out_b + gap), y2 - uy * (out_b + gap))
    return a, b


def render_diagram(frame, spec, els):
    """A drawn diagram: the AI names the nodes and the arrows, this lays them out.

    Everything is a real vector shape, so the picture is drawn identically in the
    preview, in the review image and in the exported PowerPoint file."""
    content_title(frame, spec, els)
    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    if not nodes:
        return
    x, y, w, h = frame.content_rect()
    c = frame.c
    ink, soft, accents, acc_text = palette(frame)
    caption = spec.get("caption", "")
    area_h = h - (0.42 if caption else 0)
    n = len(nodes)

    # rank the nodes by their longest path from a root so the flow reads left to right
    depth = {}

    def rank(i, seen=()):  # noqa: B023
        if i in depth:
            return depth[i]
        if i in seen:
            return 0
        ups = [e["from"] for e in edges if e["to"] == i]
        depth[i] = 0 if not ups else 1 + max(rank(u, seen + (i,)) for u in ups)
        return depth[i]

    for i in range(n):
        rank(i)
    cols = max(depth.values()) + 1
    # a column holds the nodes at that depth, so keep it to a readable number of rows
    per_col = math.ceil(n / cols)
    gap_x = 0.62
    gap_y = 0.42 if per_col <= 3 else 0.3
    bw = (w - gap_x * (cols - 1)) / cols
    bh = min(1.35, (area_h - gap_y * (per_col - 1)) / max(per_col, 1))
    col_w = [bw] * cols
    rows_in = {}
    for i, node in enumerate(nodes):
        rows_in.setdefault(depth[i], []).append(i)
    pos = {}
    node_h = bh  # grow with the space available; short flows get tall, airy boxes
    for col, members in rows_in.items():
        cx = x + col * (bw + gap_x) + bw / 2
        block = len(members) * node_h + (len(members) - 1) * gap_y
        top = y + max(0, (area_h - block) / 2)
        for r, i in enumerate(members):
            cy = top + r * (node_h + gap_y) + node_h / 2
            pos[i] = (cx, cy)

    def arrow_between(edge):
        a, b = pos.get(edge["from"]), pos.get(edge["to"])
        if not a or not b:
            return None, None
        return _clip(a, b, bw / 2, node_h / 2, bw / 2, node_h / 2)

    for edge in edges:  # arrows first, so the panels sit on top of them
        a, b = arrow_between(edge)
        if a:
            els.append(CONN(a, b, c["muted"], 1.6, dash=edge.get("dash")))

    for i, node in enumerate(nodes):
        cx, cy = pos[i]
        acc = accents[i % 4]
        bh_ = node_h
        els.append(_node_box(cx, cy, col_w[depth[i]], bh_, i, frame, acc))
        icon = node["icon"] if has_icon(node) else ""
        tw = col_w[depth[i]] - (1.1 if icon else 0.28)
        ls = fit_size(node["label"], tw, 0.42, 15, 10, "heading", face=frame.f_head)
        if icon and est_lines(node["label"], ls, tw, "heading", frame.f_head) > 2:
            # a 3-line label collides with the icon: try two lines, else drop the icon for the full width
            ls = fit_size(node["label"], tw, 0.8, 15, 9, "heading", face=frame.f_head)
            if est_lines(node["label"], ls, tw, "heading", frame.f_head) > 2:
                icon, tw = "", col_w[depth[i]] - 0.28
                ls = fit_size(node["label"], tw, 0.84, 15, 10, "heading", face=frame.f_head)
        paras = [P(node["label"], ls, c["text"], "heading", frame.heading_bold, space=2)]
        if node.get("text"):
            # keep node text only if label + detail genuinely fit the box at readable sizes
            room = bh_ - 0.24
            need = est_lines(node["label"], ls, tw, "heading", frame.f_head) * ls / 72 * 1.12 + 0.03
            ts = fit_size(node["text"], tw, room - need, 11, 9)
            if ts >= 9 and need + est_lines(node["text"], ts, tw, "body", frame.f_body) * ts / 72 * 1.15 <= room:
                paras.append(P(node["text"], ts, soft))
        if icon:
            els.append(ICON(cx - col_w[depth[i]] / 2 + 0.36, cy - 0.22, 0.44, icon, acc))
        # with an icon, left-align the text fully clear of the icon column - wrapped lines can then never touch it
        t_align = "l" if icon else "c"
        t_x = cx - col_w[depth[i]] / 2 + 0.95 if icon else cx - tw / 2 + 0.14
        els.append(T(t_x, cy - bh_ / 2 + 0.1, tw, bh_ - 0.2, paras, t_align, "m", line=1.12))

    for edge in edges:  # arrow labels sit on top of the line, in a gap of background
        if not edge.get("label"):
            continue
        a, b = arrow_between(edge)
        if not a:
            continue
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        lw = min(gap_x - 0.08, max(0.6, 0.075 * len(edge["label"]) + 0.3))
        ls = fit_size(edge["label"], lw, 0.3, 10, 7)
        if ls < 7:  # too long to fit between the columns - skip rather than stamp it on a box
            continue
        clear = all(abs(mx - px) > bw / 2 + lw / 2 + 0.05 or abs(my - py) > node_h / 2 + 0.2
                    for px, py in pos.values())  # any node the label would land on, including ones the edge crosses
        if not clear:  # midpoint falls on a node box - no room for a label here
            continue
        els.append(R(mx - lw / 2 - 0.05, my - 0.17, lw + 0.1, 0.34, c["bg"], radius=0.06))
        els.append(T(mx - lw / 2, my - 0.17, lw, 0.34,
                     [P(edge["label"], ls, c["muted"], "body", True)], "c", "m"))

    if caption:
        els.append(T(x, y + area_h + 0.06, w, 0.4,
                     [P(caption, fit_size(caption, w, 0.4, 13, 9), c["muted"], italic=True)], "c", "m"))


ROLE = {"title": "title", "closing": "title", "section": "section", "bullets": "bullets", "two_column": "two_column",
        "quote": "blank"}
ALT = {"section"}


def _decorate(frame, els):
    """A quiet background motif chosen by the deck's DNA (built-in themes only)."""
    W, H, c = frame.W, frame.H, frame.c
    if frame.style == "bauhaus":
        return _bh_decorate(frame, els)
    deco = frame.dna.get("deco", "none")
    if deco == "corner":
        els.append(R(W - 2.1, -2.1, 4.2, 4.2, c["accent"], 0.16, shape="ellipse"))
    elif deco == "band":
        els.append(R(0, 0, 0.16, H, c["accent"]))
    elif deco == "dots":
        for r_ in range(3):
            for k in range(5):
                els.append(R(W - 0.55 - k * 0.28, 0.35 + r_ * 0.28, 0.07, 0.07, c["accent"], 0.45, shape="ellipse"))
    elif deco == "blob":
        els.append(R(W - 4.2, H - 3.2, 6.2, 6.2, c["accent2"], 0.15, shape="ellipse"))


def layout_slide(spec: dict, theme: dict, index: int, deck: list[dict], deck_title: str) -> dict:
    stype = spec.get("type", "bullets")
    if stype == "template":
        out = render_template(spec, theme) if theme["kind"] == "custom" else None
        if out:
            return out
        spec = {"type": "bullets", "title": spec.get("title") or "Template page unavailable", "bullets": []}
        stype = "bullets"
    frame = Frame(theme, ROLE.get(stype, "visual"), alt=stype in ALT)
    base = template_slide(theme, theme.get("base_slide")) if frame.custom else None
    els: list[dict] = []
    frame.index = index
    frame.occ = sum(1 for sp in deck[:index] if sp.get("type") == stype)  # repeats of this type rotate the variant
    frame._els = els
    if not frame.custom and frame.dna and stype not in ("title", "closing", "section", "image", "quote"):
        _decorate(frame, els)
    if base:
        frame.use_base(base)
        keep = {base["title_key"], base["body_key"]}
        for e in base["elements"]:
            if e.get("key") not in keep:
                els.append({**e, "static": True})
    if stype in ("title", "closing"):
        render_title(frame, spec, els, closing=stype == "closing")
    elif stype == "section":
        number = sum(1 for s in deck[: index + 1] if s.get("type") == "section") or 1
        render_section(frame, spec, els, number)
    elif stype == "two_column":
        render_two_column(frame, spec, els)
    elif stype == "cards":
        render_cards(frame, spec, els)
    elif stype == "stats":
        render_stats(frame, spec, els)
    elif stype == "timeline":
        render_timeline(frame, spec, els)
    elif stype == "chart":
        render_chart(frame, spec, els)
    elif stype == "table":
        render_table(frame, spec, els)
    elif stype == "quote":
        render_quote(frame, spec, els)
    elif stype == "image":
        render_image(frame, spec, els)
    elif stype == "matrix":
        render_matrix(frame, spec, els)
    elif stype == "process":
        render_process(frame, spec, els)
    elif stype == "funnel":
        render_funnel(frame, spec, els)
    elif stype == "quiz":
        render_quiz(frame, spec, els)
    elif stype == "document":
        render_document(frame, spec, els)
    elif stype == "diagram":
        render_diagram(frame, spec, els)
    else:
        render_bullets(frame, spec, els)
    if stype not in ("title", "closing", "section", "quote", "image", "document"):
        footer(frame, deck_title, index, els)
    logo = theme.get("logo") if not frame.custom else None
    if logo and logo.get("src") and not (stype in ("title", "closing", "section") and photo(spec)):
        lh = 0.5 if stype not in ("title", "closing") else 0.75
        lw = min(2.4, lh * logo["w"] / max(logo["h"], 1))
        els.append({"t": "image", "x": frame.W - frame.mx - lw, "y": 0.32 if stype not in ("title", "closing") else frame.H - lh - 0.45,
                    "w": lw, "h": lh, "src": logo["src"], "fit": "contain"})
    out = {
        "w": frame.W, "h": frame.H,
        "bg": frame.bg if not base else base["bg"],
        "layout_key": frame.layout["key"] if frame.layout else None,
        "elements": els,
    }
    if base:
        filled = {e.get("key") for e in els if e.get("key") and not e.get("static")}
        out["clone"] = {"source": base["id"], "remove": [k for k in (base["title_key"], base["body_key"]) if k and k not in filled]}
        out["hide_master"] = base["hide_master"]
        for e in els:  # drawn components use the template's own fonts
            if e["t"] == "text" and not e.get("key"):
                for p in e["paras"]:
                    p.setdefault("face", frame.faces[p.get("font", "body")])
            elif e["t"] in ("chart", "table"):
                e.setdefault("face", frame.faces["body"])
    return out
