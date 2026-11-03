"""Analyze an uploaded .pptx/.potx so decks can be generated *inside* it.

Produces a JSON "profile": slide size, theme colors + fonts, every slide layout with
its placeholders (geometry + text style), background and static decoration
(logos, shapes) for the live HTML preview, and a mapping from our slide types to
the best-matching layouts.
"""
from __future__ import annotations

import colorsys
import hashlib
import io
import math
import re
import shutil
import zipfile
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.enum.shapes import PP_PLACEHOLDER

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
R_EMBED = "{%s}embed" % NS["r"]
EMU = 914400.0  # per inch

PRESET_COLORS = {"black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "008000", "blue": "0000FF",
                 "yellow": "FFFF00", "gray": "808080", "grey": "808080", "orange": "FFA500"}
BROWSER_IMAGE_TYPES = {"png", "jpg", "jpeg", "gif", "bmp", "svg", "webp"}

TITLE_TYPES = {PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.VERTICAL_TITLE}
BODY_TYPES = {PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT, PP_PLACEHOLDER.VERTICAL_BODY, PP_PLACEHOLDER.VERTICAL_OBJECT}
META_TYPES = {PP_PLACEHOLDER.DATE, PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.SLIDE_NUMBER}


def local(tag: str) -> str:
    return tag.split("}", 1)[-1] if isinstance(tag, str) else ""


# ---------------------------------------------------------------- colors

def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


def luminance(h: str) -> float:
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _hex_to_rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a: str, b: str, t: float) -> str:
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    return _rgb_to_hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def _apply_transforms(hex6: str, color_el) -> tuple[str, float]:
    r, g, b = _hex_to_rgb(hex6)
    alpha = 1.0
    for t in color_el:
        name, val = local(t.tag), t.get("val")
        if val is None:
            continue
        v = int(val) / 100000.0
        if name in ("lumMod", "lumOff"):
            h, l, s = colorsys.rgb_to_hls(r, g, b)
            l = l * v if name == "lumMod" else l + v
            r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), s)
        elif name == "tint":
            r, g, b = (c + (1 - c) * (1 - v) for c in (r, g, b))
        elif name == "shade":
            r, g, b = (c * v for c in (r, g, b))
        elif name == "alpha":
            alpha = v
    return _rgb_to_hex((r, g, b)), alpha


class ColorCtx:
    def __init__(self, scheme: dict[str, str], clr_map: dict[str, str]):
        self.scheme = scheme
        self.clr_map = clr_map

    def scheme_hex(self, name: str) -> str | None:
        name = self.clr_map.get(name, name)
        return self.scheme.get(name)

    def resolve(self, parent, ph_color: str | None = None) -> tuple[str, float] | None:
        """Resolve the first color child of a fill-like element."""
        if parent is None:
            return None
        for child in parent:
            tag = local(child.tag)
            base = None
            if tag == "srgbClr":
                base = child.get("val")
            elif tag == "schemeClr":
                val = child.get("val")
                base = (ph_color or "").lstrip("#") if val == "phClr" else (self.scheme_hex(val) or "").lstrip("#")
            elif tag == "sysClr":
                base = child.get("lastClr") or ("000000" if child.get("val") == "windowText" else "FFFFFF")
            elif tag == "prstClr":
                base = PRESET_COLORS.get(child.get("val", ""), "000000")
            elif tag == "scrgbClr":
                try:
                    base = _rgb_to_hex(tuple(int(child.get(k)) / 100000 for k in ("r", "g", "b"))).lstrip("#")
                except (TypeError, ValueError):
                    base = None
            if base:
                return _apply_transforms(base, child)
        return None


def _fill_of(sp_pr, ctx: ColorCtx, part, assets) -> dict | None:
    """Fill description of a spPr/bgPr element: solid, gradient or image."""
    if sp_pr is None:
        return None
    solid = sp_pr.find("a:solidFill", NS)
    if solid is not None:
        c = ctx.resolve(solid)
        return {"type": "solid", "color": c[0], "alpha": c[1]} if c else None
    grad = sp_pr.find("a:gradFill", NS)
    if grad is not None:
        stops = []
        for gs in grad.findall("a:gsLst/a:gs", NS):
            c = ctx.resolve(gs)
            if c:
                stops.append({"pos": int(gs.get("pos", "0")) / 1000.0, "color": c[0], "alpha": c[1]})
        lin = grad.find("a:lin", NS)
        angle = int(lin.get("ang", "0")) / 60000.0 if lin is not None else 90.0
        radial = grad.find("a:path", NS) is not None
        if stops:
            return {"type": "gradient", "stops": sorted(stops, key=lambda s: s["pos"]), "angle": angle, "radial": radial}
        return None
    blip = sp_pr.find("a:blipFill/a:blip", NS)
    if blip is not None:
        src = _save_image(part, blip.get(R_EMBED), assets)
        return {"type": "image", "src": src} if src else None
    patt = sp_pr.find("a:pattFill", NS)
    if patt is not None:
        c = ctx.resolve(patt.find("a:fgClr", NS))
        return {"type": "solid", "color": c[0], "alpha": c[1]} if c else None
    return None


def _save_image(part, rid: str | None, assets) -> str | None:
    if not rid:
        return None
    try:
        img_part = part.related_part(rid)
    except KeyError:
        return None
    ext = str(img_part.partname).rsplit(".", 1)[-1].lower()
    if ext not in BROWSER_IMAGE_TYPES:
        return None
    blob = img_part.blob
    name = hashlib.sha1(blob).hexdigest()[:16] + "." + ext
    target = assets["dir"] / name
    if not target.exists():
        target.write_bytes(blob)
    return f"{assets['url']}/{name}"


# ---------------------------------------------------------------- geometry

class Xform:
    """Maps child EMU coordinates through nested group transforms."""

    def __init__(self, sx=1.0, sy=1.0, dx=0.0, dy=0.0):
        self.sx, self.sy, self.dx, self.dy = sx, sy, dx, dy

    def apply(self, x, y, w, h):
        return x * self.sx + self.dx, y * self.sy + self.dy, w * self.sx, h * self.sy

    def child(self, xfrm):
        off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
        choff, chext = xfrm.find("a:chOff", NS), xfrm.find("a:chExt", NS)
        if off is None or ext is None or choff is None or chext is None:
            return self
        ox, oy = int(off.get("x")), int(off.get("y"))
        cx, cy = int(ext.get("cx")), int(ext.get("cy"))
        chx, chy = int(choff.get("x")), int(choff.get("y"))
        chcx, chcy = int(chext.get("cx")) or 1, int(chext.get("cy")) or 1
        ssx, ssy = cx / chcx, cy / chcy
        # child -> group space: X = ox + (x - chx) * ssx; then group -> parent via self
        return Xform(self.sx * ssx, self.sy * ssy, self.dx + (ox - chx * ssx) * self.sx, self.dy + (oy - chy * ssy) * self.sy)


def _xfrm_box(sp_pr, xf: Xform):
    xfrm = sp_pr.find("a:xfrm", NS) if sp_pr is not None else None
    if xfrm is None:
        return None
    off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    x, y, w, h = xf.apply(int(off.get("x")), int(off.get("y")), int(ext.get("cx")), int(ext.get("cy")))
    return {
        "x": x / EMU, "y": y / EMU, "w": w / EMU, "h": h / EMU,
        "rot": int(xfrm.get("rot", "0")) / 60000.0,
        "flipH": xfrm.get("flipH") == "1", "flipV": xfrm.get("flipV") == "1",
    }


def _preset_path(prst: str, adj: float | None = None) -> str | None:
    """SVG path (in a 0..1000 box) for common preset shapes."""
    a = 250 if adj is None else adj
    paths = {
        "triangle": "M500 0 L1000 1000 L0 1000 Z",
        "rtTriangle": "M0 0 L1000 1000 L0 1000 Z",
        "diamond": "M500 0 L1000 500 L500 1000 L0 500 Z",
        "parallelogram": f"M{a} 0 L1000 0 L{1000 - a} 1000 L0 1000 Z",
        "trapezoid": f"M{a} 0 L{1000 - a} 0 L1000 1000 L0 1000 Z",
        "homePlate": "M0 0 L800 0 L1000 500 L800 1000 L0 1000 Z",
        "chevron": "M0 0 L800 0 L1000 500 L800 1000 L0 1000 L200 500 Z",
        "pentagon": "M500 0 L1000 380 L810 1000 L190 1000 L0 380 Z",
        "hexagon": "M250 0 L750 0 L1000 500 L750 1000 L250 1000 L0 500 Z",
    }
    return paths.get(prst)


def _cust_geom_path(cust) -> str | None:
    parts = []
    for path in cust.findall("a:pathLst/a:path", NS):
        pw = int(path.get("w", "0") or 0) or 1
        ph = int(path.get("h", "0") or 0) or 1
        sx, sy = 1000.0 / pw, 1000.0 / ph
        cur = (0.0, 0.0)

        def pt(el):
            return float(el.get("x")) * sx, float(el.get("y")) * sy

        for cmd in path:
            name = local(cmd.tag)
            pts = [pt(p) for p in cmd.findall("a:pt", NS)]
            if name == "moveTo" and pts:
                cur = pts[0]
                parts.append(f"M{cur[0]:.1f} {cur[1]:.1f}")
            elif name == "lnTo" and pts:
                cur = pts[0]
                parts.append(f"L{cur[0]:.1f} {cur[1]:.1f}")
            elif name == "cubicBezTo" and len(pts) == 3:
                parts.append("C" + " ".join(f"{x:.1f} {y:.1f}" for x, y in pts))
                cur = pts[-1]
            elif name == "quadBezTo" and len(pts) == 2:
                parts.append("Q" + " ".join(f"{x:.1f} {y:.1f}" for x, y in pts))
                cur = pts[-1]
            elif name == "arcTo":
                try:
                    wr, hr = float(cmd.get("wR")) * sx, float(cmd.get("hR")) * sy
                    st, sw = math.radians(int(cmd.get("stAng")) / 60000), math.radians(int(cmd.get("swAng")) / 60000)
                except (TypeError, ValueError):
                    continue
                cx, cy = cur[0] - wr * math.cos(st), cur[1] - hr * math.sin(st)
                ex, ey = cx + wr * math.cos(st + sw), cy + hr * math.sin(st + sw)
                large = 1 if abs(sw) > math.pi else 0
                sweep = 1 if sw > 0 else 0
                parts.append(f"A{wr:.1f} {hr:.1f} 0 {large} {sweep} {ex:.1f} {ey:.1f}")
                cur = (ex, ey)
            elif name == "close":
                parts.append("Z")
    return " ".join(parts) or None


def _line_of(sp_pr, ctx: ColorCtx):
    ln = sp_pr.find("a:ln", NS) if sp_pr is not None else None
    if ln is None or ln.find("a:noFill", NS) is not None:
        return None
    solid = ln.find("a:solidFill", NS)
    c = ctx.resolve(solid) if solid is not None else None
    if not c:
        return None
    return {"color": c[0], "alpha": c[1], "width": int(ln.get("w", "12700")) / 12700.0}


def _style_fill(sp, ctx: ColorCtx):
    ref = sp.find("p:style/a:fillRef", NS)
    if ref is not None and ref.get("idx") not in ("0", None):
        c = ctx.resolve(ref)
        if c:
            return {"type": "solid", "color": c[0], "alpha": c[1]}
    return None


def _decor(tree, part, ctx: ColorCtx, xf: Xform, assets, out: list):
    """Collect non-placeholder drawing elements from an spTree/grpSp."""
    for el in tree:
        tag = local(el.tag)
        if tag in ("sp", "pic", "cxnSp") and el.find(".//p:nvPr/p:ph", NS) is not None:
            continue
        if tag == "grpSp":
            gxfrm = el.find("p:grpSpPr/a:xfrm", NS)
            _decor(el, part, ctx, xf.child(gxfrm) if gxfrm is not None else xf, assets, out)
        elif tag == "pic":
            box = _xfrm_box(el.find("p:spPr", NS), xf)
            blip = el.find("p:blipFill/a:blip", NS)
            src = _save_image(part, blip.get(R_EMBED) if blip is not None else None, assets)
            if box and src:
                out.append({"kind": "image", "src": src, **box})
        elif tag == "cxnSp":
            sp_pr = el.find("p:spPr", NS)
            box = _xfrm_box(sp_pr, xf)
            line = _line_of(sp_pr, ctx)
            if box and line:
                out.append({"kind": "line", "line": line, **box})
        elif tag == "sp":
            sp_pr = el.find("p:spPr", NS)
            box = _xfrm_box(sp_pr, xf)
            if not box:
                continue
            fill = None
            if sp_pr is not None and sp_pr.find("a:noFill", NS) is None:
                fill = _fill_of(sp_pr, ctx, part, assets) or _style_fill(el, ctx)
            line = _line_of(sp_pr, ctx)
            prst_el = sp_pr.find("a:prstGeom", NS) if sp_pr is not None else None
            cust = sp_pr.find("a:custGeom", NS) if sp_pr is not None else None
            prst = prst_el.get("prst") if prst_el is not None else None
            item = {"kind": "shape", "fill": fill, "line": line, **box}
            if prst in ("rect", "snip1Rect"):
                item["geom"] = "rect"
            elif prst == "roundRect":
                item["geom"] = "roundRect"
            elif prst == "ellipse":
                item["geom"] = "ellipse"
            elif prst == "line":
                if line:
                    out.append({"kind": "line", "line": line, **box})
                continue
            elif prst and _preset_path(prst):
                item["geom"], item["path"] = "path", _preset_path(prst)
            elif cust is not None:
                path = _cust_geom_path(cust)
                if not path:
                    continue
                item["geom"], item["path"] = "path", path
            else:
                item["geom"] = None
            text = _static_text(el, ctx)
            if text:
                item["text"] = text
            if (fill or line) and item["geom"]:
                out.append(item)
            elif text:
                item["fill"], item["line"], item["geom"] = None, None, "rect"
                out.append(item)


def _static_text(sp, ctx: ColorCtx):
    paras = sp.findall("p:txBody/a:p", NS)
    texts = ["".join(t.text or "" for t in p.findall(".//a:t", NS)) for p in paras]
    text = "\n".join(t for t in texts if t.strip())
    if not text.strip():
        return None
    rpr = sp.find(".//a:rPr", NS)
    if rpr is None:
        rpr = sp.find(".//a:endParaRPr", NS)
    size = int(rpr.get("sz")) / 100.0 if rpr is not None and rpr.get("sz") else 14.0
    color = ctx.resolve(rpr.find("a:solidFill", NS)) if rpr is not None and rpr.find("a:solidFill", NS) is not None else None
    ppr = sp.find(".//a:pPr", NS)
    anchor = sp.find("p:txBody/a:bodyPr", NS)
    return {"text": text[:300], "size": size, "color": color[0] if color else None,
            "bold": rpr is not None and rpr.get("b") == "1",
            "align": (ppr.get("algn") if ppr is not None else None) or "l",
            "anchor": (anchor.get("anchor") if anchor is not None else None) or "t"}


# ---------------------------------------------------------------- placeholders

def _lvl1(el):
    return el.find("a:lvl1pPr", NS) if el is not None else None


def _ph_style(layout_ph_el, master_ph_el, master_txstyle, ctx: ColorCtx, is_title: bool):
    """Resolve lvl1 text style + vertical anchor for a placeholder."""
    chain = [
        _lvl1(layout_ph_el.find("p:txBody/a:lstStyle", NS)) if layout_ph_el is not None else None,
        _lvl1(master_ph_el.find("p:txBody/a:lstStyle", NS)) if master_ph_el is not None else None,
        _lvl1(master_txstyle),
    ]
    style = {"size": None, "color": None, "bold": None, "align": None, "italic": None}
    for ppr in chain:
        if ppr is None:
            continue
        if style["align"] is None and ppr.get("algn"):
            style["align"] = ppr.get("algn")
        d = ppr.find("a:defRPr", NS)
        if d is None:
            continue
        if style["size"] is None and d.get("sz"):
            style["size"] = int(d.get("sz")) / 100.0
        if style["bold"] is None and d.get("b") is not None:
            style["bold"] = d.get("b") == "1"
        if style["italic"] is None and d.get("i") is not None:
            style["italic"] = d.get("i") == "1"
        if style["color"] is None and d.find("a:solidFill", NS) is not None:
            c = ctx.resolve(d.find("a:solidFill", NS))
            if c:
                style["color"] = c[0]
    anchor = None
    for el in (layout_ph_el, master_ph_el):
        if el is None:
            continue
        bp = el.find("p:txBody/a:bodyPr", NS)
        if bp is not None and bp.get("anchor"):
            anchor = bp.get("anchor")
            break
    style["anchor"] = anchor or "t"
    style["size"] = style["size"] or (44.0 if is_title else 24.0)
    style["align"] = style["align"] or "l"
    return style


def _master_ph(master_el, ph_type: str):
    want = {"title": ("title", "ctrTitle"), "ctrTitle": ("title", "ctrTitle"), "subTitle": ("body",),
            "body": ("body",), "obj": ("body",), "dt": ("dt",), "ftr": ("ftr",), "sldNum": ("sldNum",)}.get(ph_type, ("body",))
    for sp in master_el.findall("p:cSld/p:spTree/p:sp", NS):
        ph = sp.find("p:nvSpPr/p:nvPr/p:ph", NS)
        if ph is not None and ph.get("type", "body") in want:
            return sp
    return None


# ---------------------------------------------------------------- main

def convert_potx(path: Path) -> None:
    """python-pptx refuses .potx content types; rewrite them in place as .pptx."""
    with zipfile.ZipFile(path) as zin:
        ct = zin.read("[Content_Types].xml").decode("utf-8")
        if "presentationml.template.main+xml" not in ct:
            return
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "[Content_Types].xml":
                    data = ct.replace("presentationml.template.main+xml", "presentationml.presentation.main+xml").encode("utf-8")
                zout.writestr(item, data)
    path.write_bytes(buf.getvalue())


def _avg_image_color(src_url: str, assets) -> str | None:
    try:
        from PIL import Image
        name = src_url.rsplit("/", 1)[-1]
        with Image.open(assets["dir"] / name) as im:
            im = im.convert("RGB").resize((16, 16))
            px = list(im.getdata())
        r = sum(p[0] for p in px) / len(px) / 255
        g = sum(p[1] for p in px) / len(px) / 255
        b = sum(p[2] for p in px) / len(px) / 255
        return _rgb_to_hex((r, g, b))
    except Exception:
        return None


def _bg_color(bg: dict | None, fallback: str, assets) -> str:
    if not bg:
        return fallback
    if bg["type"] == "solid":
        return bg["color"]
    if bg["type"] == "gradient":
        stops = bg["stops"]
        avg = stops[0]["color"]
        for s in stops[1:]:
            avg = mix(avg, s["color"], 0.5)
        return avg
    if bg["type"] == "image":
        return _avg_image_color(bg["src"], assets) or fallback
    return fallback


def _background(el, part, ctx: ColorCtx, theme_el, assets):
    bg = el.find("p:cSld/p:bg", NS)
    if bg is None:
        return None
    bg_pr = bg.find("p:bgPr", NS)
    if bg_pr is not None:
        return _fill_of(bg_pr, ctx, part, assets)
    ref = bg.find("p:bgRef", NS)
    if ref is not None:
        color = ctx.resolve(ref)
        idx = int(ref.get("idx", "0"))
        styles = theme_el.findall(".//a:fmtScheme/a:bgFillStyleLst/*", NS) if theme_el is not None else []
        if idx >= 1001 and idx - 1001 < len(styles) and color:
            style = styles[idx - 1001]
            name = local(style.tag)
            if name == "gradFill":
                stops = []
                for gs in style.findall("a:gsLst/a:gs", NS):
                    c = ctx.resolve(gs, ph_color=color[0])
                    if c:
                        stops.append({"pos": int(gs.get("pos", "0")) / 1000.0, "color": c[0], "alpha": c[1]})
                lin = style.find("a:lin", NS)
                if stops:
                    return {"type": "gradient", "stops": stops, "angle": int(lin.get("ang", "0")) / 60000.0 if lin is not None else 90.0,
                            "radial": style.find("a:path", NS) is not None}
            elif name == "solidFill":
                c = ctx.resolve(style, ph_color=color[0])
                if c:
                    return {"type": "solid", "color": c[0], "alpha": 1.0}
        if color:
            return {"type": "solid", "color": color[0], "alpha": 1.0}
    return None


def _ph_kind(t) -> str:
    if t in TITLE_TYPES:
        return "title"
    if t == PP_PLACEHOLDER.SUBTITLE:
        return "subtitle"
    if t in BODY_TYPES:
        return "body"
    if t in META_TYPES:
        return "meta"
    if t == PP_PLACEHOLDER.PICTURE:
        return "picture"
    return "other"


PH_XML_TYPE = {
    PP_PLACEHOLDER.TITLE: "title", PP_PLACEHOLDER.CENTER_TITLE: "ctrTitle", PP_PLACEHOLDER.SUBTITLE: "subTitle",
    PP_PLACEHOLDER.BODY: "body", PP_PLACEHOLDER.OBJECT: "obj", PP_PLACEHOLDER.DATE: "dt",
    PP_PLACEHOLDER.FOOTER: "ftr", PP_PLACEHOLDER.SLIDE_NUMBER: "sldNum",
}


PROFILE_VERSION = 3
GUIDE_RE = re.compile(r"guideline|instructions? for|font[- ]?size\s*=|font type\s*=", re.I)
CLOSING_RE = re.compile(r"thank|questions\s*\??$|q\s*&\s*a", re.I)
TOC_RE = re.compile(r"table of content|contents|agenda|outline|index", re.I)
SAMPLE_RE = re.compile(r"<[^>]+>|x{4,}|lorem|ipsum|click to|your (name|title|text)|^\s*(title|content|heading|subtitle|text)\s*$", re.I)


def _theme_face(face: str | None, fonts: dict) -> str | None:
    if not face:
        return None
    if face.startswith("+mj"):
        return fonts["heading"]
    if face.startswith("+mn"):
        return fonts["body"]
    return face


def _para(p_el, ctx: ColorCtx, fonts: dict, d: dict) -> dict:
    """One paragraph -> display paragraph (text + resolved first-run style)."""
    text = "".join((t.text or "") for t in p_el.iter("{%s}t" % NS["a"]))
    ppr = p_el.find("a:pPr", NS)
    rpr = p_el.find("a:r/a:rPr", NS)
    if rpr is None:
        rpr = p_el.find("a:fld/a:rPr", NS)
    if rpr is None:
        rpr = p_el.find("a:endParaRPr", NS)
    size, bold, italic, color, face = d["size"], d["bold"], False, d["color"], d.get("face")
    if rpr is not None:
        if rpr.get("sz"):
            size = int(rpr.get("sz")) / 100.0
        if rpr.get("b") is not None:
            bold = rpr.get("b") == "1"
        italic = rpr.get("i") == "1"
        fill = rpr.find("a:solidFill", NS)
        if fill is not None:
            c = ctx.resolve(fill)
            if c:
                color = c[0]
        latin = rpr.find("a:latin", NS)
        if latin is not None:
            face = _theme_face(latin.get("typeface"), fonts) or face
    level = int(ppr.get("lvl", "0")) if ppr is not None else 0
    align = (ppr.get("algn") if ppr is not None else None) or d["align"]
    bullet = None
    if ppr is not None and ppr.find("a:buNone", NS) is None:
        if ppr.find("a:buChar", NS) is not None:
            bullet = color or "#000000"
        elif ppr.find("a:buAutoNum", NS) is not None:
            bullet = color or "#000000"
    elif ppr is None and d.get("bullets"):
        bullet = "tpl"
    para = {"text": text, "size": round(size, 1), "color": color, "font": "body", "bold": bool(bold), "level": level,
            "align": {"ctr": "c", "r": "r", "just": "j", "dist": "j"}.get(align, "l")}
    if face:
        para["face"] = face
    if italic:
        para["italic"] = True
    if bullet:
        para["bullet"] = bullet
    spc = ppr.find("a:spcAft/a:spcPts", NS) if ppr is not None else None
    if spc is not None:
        para["space"] = int(spc.get("val", "0")) / 100.0
    return para


def _text_element(key, box, txbody, ctx, fonts, defaults, anchor_default="t"):
    body_pr = txbody.find("a:bodyPr", NS)
    ins = {k: int(body_pr.get(a, dflt)) / EMU for k, a, dflt in
           (("l", "lIns", 91440), ("r", "rIns", 91440), ("t", "tIns", 45720), ("b", "bIns", 45720))} if body_pr is not None else {"l": .1, "r": .1, "t": .05, "b": .05}
    anchor = (body_pr.get("anchor") if body_pr is not None else None) or anchor_default
    lst = txbody.find("a:lstStyle", NS)
    d = dict(defaults)
    lvl1 = _lvl1(lst)
    if lvl1 is not None:
        if lvl1.get("algn"):
            d["align"] = lvl1.get("algn")
        dr = lvl1.find("a:defRPr", NS)
        if dr is not None and dr.get("sz"):
            d["size"] = int(dr.get("sz")) / 100.0
    paras = [_para(p, ctx, fonts, d) for p in txbody.findall("a:p", NS)]
    line = 1.0
    ln = txbody.find("a:p/a:pPr/a:lnSpc/a:spcPct", NS)
    if ln is not None:
        line = int(ln.get("val", "100000")) / 100000.0
    return {
        "t": "text", "key": key, "x": box["x"] + ins["l"], "y": box["y"] + ins["t"],
        "w": max(0.2, box["w"] - ins["l"] - ins["r"]), "h": max(0.2, box["h"] - ins["t"] - ins["b"]),
        "rot": box.get("rot", 0), "paras": paras, "align": paras[0]["align"] if paras else "l",
        "valign": {"ctr": "m", "b": "b"}.get(anchor, "t"), "line": round(1.2 * line, 3),
    }


def _table_element(gf, key, box, ctx, fonts):
    tbl = gf.find(".//a:tbl", NS)
    cols = [int(g.get("w", "0")) / EMU for g in tbl.findall("a:tblGrid/a:gridCol", NS)]
    rows = []
    for tr in tbl.findall("a:tr", NS):
        row = []
        for tc in tr.findall("a:tc", NS):
            txb = tc.find("a:txBody", NS)
            paras = [_para(p, ctx, fonts, {"size": 14.0, "bold": False, "color": "#000000", "align": "l"}) for p in txb.findall("a:p", NS)] if txb is not None else []
            fill = None
            tcpr = tc.find("a:tcPr", NS)
            if tcpr is not None and tcpr.find("a:solidFill", NS) is not None:
                c = ctx.resolve(tcpr.find("a:solidFill", NS))
                fill = c[0] if c else None
            row.append({"text": "\n".join(p["text"] for p in paras), "paras": paras, "fill": fill})
        rows.append({"h": int(tr.get("h", "0")) / EMU, "cells": row})
    return {"t": "tpltable", "key": key, **{k: box[k] for k in ("x", "y", "w", "h")}, "cols": cols, "rows": rows}


def _slide_profile(slide, index: int, layout_key: str, ctx: ColorCtx, theme_el, fonts: dict, layouts: dict, assets) -> dict:
    el = slide._element
    lay = layouts.get(layout_key)
    bg = _background(el, slide.part, ctx, theme_el, assets)
    bg_hex = _bg_color(bg, lay["bg_color"] if lay else "#FFFFFF", assets)
    dark = luminance(bg_hex) < 0.35
    text_default = "#" + (ctx.scheme_hex("tx1") or "000000") if not dark else "#" + (ctx.scheme_hex("bg1") or "FFFFFF")
    elements, fields, texts = [], [], []
    ph_by_idx = {p["idx"]: p for p in (lay["placeholders"] if lay else [])}
    for shape in slide.shapes:
        sel = shape._element
        tag = local(sel.tag)
        key = f"#{shape.shape_id}"
        if tag in ("grpSp", "pic", "cxnSp"):
            items: list = []
            _decor([sel], slide.part, ctx, Xform(), assets, items)
            elements.extend({"t": "decor", "d": it} for it in items)
            continue
        if tag == "graphicFrame":
            box = {"x": shape.left / EMU, "y": shape.top / EMU, "w": shape.width / EMU, "h": shape.height / EMU}
            if sel.find(".//a:tbl", NS) is not None:
                tbl = _table_element(sel, key, box, ctx, fonts)
                elements.append(tbl)
                fields.append({"key": key, "kind": "table", "rows": [[c["text"] for c in r["cells"]] for r in tbl["rows"]]})
                texts.extend(c["text"] for r in tbl["rows"] for c in r["cells"])
            else:
                elements.append({"t": "decor", "d": {"kind": "shape", "geom": "rect", "fill": {"type": "solid", "color": "#888888", "alpha": 0.15},
                                                     "line": None, **box, "rot": 0, "flipH": False, "flipV": False,
                                                     "text": {"text": "Chart", "size": 14, "color": "#888888", "bold": False, "align": "ctr", "anchor": "ctr"}}})
            continue
        if tag != "sp":
            continue
        sp_pr = sel.find("p:spPr", NS)
        box = _xfrm_box(sp_pr, Xform())
        ph = sel.find("p:nvSpPr/p:nvPr/p:ph", NS)
        ph_info = None
        if ph is not None:
            ph_info = ph_by_idx.get(int(ph.get("idx", "0"))) or next(
                (p for p in (lay["placeholders"] if lay else []) if p["xml_type"] == ph.get("type", "body")), None)
            if box is None and ph_info:
                box = {k: ph_info[k] for k in ("x", "y", "w", "h")} | {"rot": 0, "flipH": False, "flipV": False}
        if box is None:
            continue
        if ph is None:
            deco: list = []
            _decor([sel], slide.part, ctx, Xform(), assets, deco)
            for it in deco:
                it.pop("text", None)
                if it.get("fill") or it.get("line"):
                    elements.append({"t": "decor", "d": it})
        txbody = sel.find("p:txBody", NS)
        if txbody is None:
            continue
        st = ph_info["style"] if ph_info else {}
        defaults = {"size": st.get("size") or 18.0, "bold": bool(st.get("bold")), "color": st.get("color") or text_default,
                    "align": st.get("align") or "l", "bullets": bool(ph_info and ph_info["kind"] == "body")}
        tel = _text_element(key, box, txbody, ctx, fonts, defaults, (st.get("anchor") if st else None) or "t")
        if ph_info and ph_info["kind"] == "title":
            for p in tel["paras"]:
                p["font"] = "heading"
        elements.append(tel)
        full = "\n".join(p["text"] for p in tel["paras"])
        if full.strip():
            texts.append(full)
        role = "title" if (ph_info and ph_info["kind"] == "title") or shape.name.lower().startswith("title") else None
        fields.append({"key": key, "kind": "text", "name": shape.name, "role": role, "w": round(box["w"], 2), "h": round(box["h"], 2),
                       "y": round(box["y"], 2), "lines": [{"p": i, "text": p["text"], "level": p["level"], "size": p["size"], "bold": p["bold"]}
                                                          for i, p in enumerate(tel["paras"])]})

    # title / body detection
    text_fields = [f for f in fields if f["kind"] == "text"]
    title = next((f for f in text_fields if f["role"] == "title"), None)
    if title is None:
        short = [f for f in text_fields if 0 < len("".join(l["text"] for l in f["lines"]).strip()) <= 70 and f["y"] < 2.0]
        title = max(short, key=lambda f: max((l["size"] for l in f["lines"]), default=0), default=None)
        if title:
            title["role"] = "title"
    body = max((f for f in text_fields if f is not title and any(l["text"].strip() for l in f["lines"])),
               key=lambda f: f["w"] * f["h"], default=None)
    if body:
        body["role"] = "body"
    alltext = " ".join(texts)

    def first_line(f):
        return next((l["text"].strip() for l in f["lines"] if l["text"].strip()), "") if f else ""
    head = " ".join(x for x in (first_line(title), first_line(body)) if x)
    if GUIDE_RE.search(alltext):
        role = "guide"
    elif CLOSING_RE.search(alltext.strip()) and len(alltext.strip()) < 140:
        role = "closing"
    elif index > 0 and TOC_RE.search(head):
        role = "toc"
    elif index == 0:
        role = "cover"
    elif title and body:
        role = "content"
    else:
        role = "other"
    return {
        "id": f"T{index + 1}", "index": index, "layout_key": layout_key, "role": role,
        "bg": bg, "bg_color": bg_hex, "dark": dark, "hide_master": el.get("showMasterSp") == "0",
        "elements": elements, "fields": fields,
        "title_key": title["key"] if title else None, "body_key": body["key"] if body else None,
        "text": alltext[:2000],
    }


def analyze(path: Path, template_id: str, name: str, assets_dir: Path, assets_url: str) -> dict:
    convert_potx(path)
    prs = Presentation(str(path))
    W, H = prs.slide_width / EMU, prs.slide_height / EMU
    assets = {"dir": assets_dir, "url": assets_url}
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    assets_dir.mkdir(parents=True)

    master0 = prs.slide_masters[0]
    theme_el = None
    for rel in master0.part.rels.values():
        if rel.reltype.endswith("/theme"):
            theme_el = etree.fromstring(rel.target_part.blob)
            break
    scheme: dict[str, str] = {}
    fonts = {"heading": "Calibri", "body": "Calibri"}
    if theme_el is not None:
        for child in theme_el.find(".//a:clrScheme", NS) if theme_el.find(".//a:clrScheme", NS) is not None else []:
            c = ColorCtx({}, {}).resolve(child)
            if c:
                scheme[local(child.tag)] = c[0].lstrip("#")
        maj = theme_el.find(".//a:fontScheme/a:majorFont/a:latin", NS)
        mnr = theme_el.find(".//a:fontScheme/a:minorFont/a:latin", NS)
        if maj is not None and maj.get("typeface"):
            fonts["heading"] = maj.get("typeface")
        if mnr is not None and mnr.get("typeface"):
            fonts["body"] = mnr.get("typeface")
    scheme.setdefault("dk1", "000000")
    scheme.setdefault("lt1", "FFFFFF")
    scheme.setdefault("dk2", scheme["dk1"])
    scheme.setdefault("lt2", scheme["lt1"])
    for i, default in enumerate(["4472C4", "ED7D31", "A5A5A5", "FFC000", "5B9BD5", "70AD47"], start=1):
        scheme.setdefault(f"accent{i}", default)

    layouts = []
    ctxs: dict[int, ColorCtx] = {}
    part_keys: dict = {}
    for mi, master in enumerate(prs.slide_masters):
        m_el = master._element
        cm = m_el.find("p:clrMap", NS)
        clr_map = dict(cm.attrib) if cm is not None else {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}
        ctx = ColorCtx(scheme, clr_map)
        ctxs[mi] = ctx
        m_bg = _background(m_el, master.part, ctx, theme_el, assets)
        m_decor: list = []
        _decor(m_el.find("p:cSld/p:spTree", NS), master.part, ctx, Xform(), assets, m_decor)
        tx = m_el.find("p:txStyles", NS)
        title_style = tx.find("p:titleStyle", NS) if tx is not None else None
        body_style = tx.find("p:bodyStyle", NS) if tx is not None else None

        for li, layout in enumerate(master.slide_layouts):
            part_keys[str(layout.part.partname)] = f"{mi}:{li}"
            l_el = layout._element
            bg = _background(l_el, layout.part, ctx, theme_el, assets) or m_bg
            decor: list = []
            if l_el.get("showMasterSp") != "0":
                decor.extend(m_decor)
            _decor(l_el.find("p:cSld/p:spTree", NS), layout.part, ctx, Xform(), assets, decor)
            bg_hex = _bg_color(bg, "#" + scheme["lt1"], assets)
            dark = luminance(bg_hex) < 0.35
            phs = []
            for ph in layout.placeholders:
                try:
                    pf = ph.placeholder_format
                    if ph.left is None or ph.width is None:
                        continue
                    kind = _ph_kind(pf.type)
                    xml_type = PH_XML_TYPE.get(pf.type, "body")
                    m_ph = _master_ph(m_el, xml_type)
                    style = _ph_style(ph._element, m_ph, title_style if kind == "title" else body_style, ctx, kind == "title")
                    if not style["color"]:
                        style["color"] = "#" + (scheme["lt1"] if dark else scheme["dk1"])
                    phs.append({
                        "idx": pf.idx, "kind": kind, "xml_type": xml_type, "name": ph.name,
                        "x": ph.left / EMU, "y": ph.top / EMU, "w": ph.width / EMU, "h": ph.height / EMU,
                        "style": style,
                    })
                except Exception:
                    continue
            layouts.append({
                "key": f"{mi}:{li}", "master": mi, "index": li, "name": layout.name or f"Layout {li + 1}",
                "placeholders": phs, "background": bg, "bg_color": bg_hex, "dark": dark, "decor": decor[:80],
            })

    mapping = _map_layouts(layouts, W, H)
    by_key = {l["key"]: l for l in layouts}
    slides = []
    for i, slide in enumerate(prs.slides):
        key = part_keys.get(str(slide.slide_layout.part.partname), layouts[0]["key"])
        try:
            slides.append(_slide_profile(slide, i, key, ctxs[int(key.split(":")[0])], theme_el, fonts, by_key, assets))
        except Exception:
            continue
    base_slide = next((sl for sl in slides if sl["role"] == "content" and sl["title_key"] and sl["body_key"]), None)
    if base_slide:
        bt = next((e for e in base_slide["elements"] if e.get("key") == base_slide["title_key"]), None)
        style = next((q for q in (bt or {}).get("paras", []) if q["text"].strip()), None)
        for sl in slides:
            for e in sl["elements"]:
                if (style and e["t"] == "text" and e is not bt and not any(q["text"].strip() for q in e["paras"])
                        and abs(e["x"] - bt["x"]) < 0.4 and abs(e["y"] - bt["y"]) < 0.4):
                    e["paras"] = [{**style, "text": "", "explicit": True}]
                    e["align"], e["valign"] = bt["align"], bt["valign"]
    base = next((l for l in layouts if l["key"] == mapping["bullets"]), layouts[0])
    bg = base["bg_color"]
    text = "#" + (scheme["lt1"] if base["dark"] else scheme["dk1"])
    if contrast(text, bg) < 3:
        text = "#FFFFFF" if base["dark"] else "#111111"
    accents = ["#" + scheme[f"accent{i}"] for i in range(1, 7)]
    colors = {
        "bg": bg, "bg_alt": bg, "text": text, "muted": mix(text, bg, 0.38),
        "accent": accents[0], "accent2": accents[1], "accent3": accents[2], "accent4": accents[3],
        "surface": mix(bg, text, 0.06), "border": mix(bg, text, 0.16),
        "on_accent": "#FFFFFF" if luminance(accents[0]) < 0.45 else "#111111",
    }
    return {
        "brand": _brand_colors(layouts, slides),
        "id": template_id, "name": name, "kind": "custom",
        "slide_w": round(W, 4), "slide_h": round(H, 4),
        "dark": base["dark"], "fonts": {"heading": fonts["heading"], "body": fonts["body"], "heading_bold": False},
        "colors": colors, "scheme": {k: "#" + v for k, v in scheme.items()},
        "layouts": layouts, "mapping": mapping, "existing_slides": len(prs.slides),
        "version": PROFILE_VERSION, "slides": slides, "base_slide": base_slide["id"] if base_slide else None,
    }


def _brand_colors(layouts: list[dict], slides: list[dict]) -> list[str]:
    """Most prominent saturated colors used by the template's own decoration."""
    weights: dict[str, float] = {}

    def add(color: str | None, area: float):
        if not color:
            return
        r, g, b = _hex_to_rgb(color)
        _, l, sat = colorsys.rgb_to_hls(r, g, b)
        if sat < 0.3 or l < 0.12 or l > 0.88:
            return
        key = color.upper()
        weights[key] = weights.get(key, 0) + max(area, 0.05)

    items = [d for l in layouts for d in l["decor"]] + [e["d"] for sl in slides for e in sl["elements"] if e["t"] == "decor"]
    for d in items:
        area = d.get("w", 0) * d.get("h", 0)
        fill = d.get("fill") or {}
        if fill.get("type") == "solid":
            add(fill.get("color"), area)
        elif fill.get("type") == "gradient":
            for st in fill.get("stops", []):
                add(st["color"], area / max(len(fill["stops"]), 1))
        if d.get("line"):
            add(d["line"].get("color"), 0.02)
    picked: list[str] = []
    for color, _ in sorted(weights.items(), key=lambda kv: -kv[1]):
        if all(sum(abs(a - b) for a, b in zip(_hex_to_rgb(color), _hex_to_rgb(c))) > 0.35 for c in picked):
            picked.append(color)
        if len(picked) == 4:
            break
    return picked


def _area(ph):
    return ph["w"] * ph["h"]


def _map_layouts(layouts: list[dict], W: float, H: float) -> dict:
    slide_area = W * H

    def kinds(l, k):
        return [p for p in l["placeholders"] if p["kind"] == k]

    def score(l, role):
        name = l["name"].lower()
        titles, bodies, subs, pics = kinds(l, "title"), kinds(l, "body"), kinds(l, "subtitle"), kinds(l, "picture")
        big = [b for b in bodies if _area(b) > 0.18 * slide_area]
        has_ctr = any(p["xml_type"] == "ctrTitle" for p in titles)
        s = 0.0
        if role == "title":
            s += 5 * has_ctr + 3 * bool(subs) + 4 * bool(re.search(r"title slide|cover|title$", name))
            s += 2 * (l["index"] == 0 and l["master"] == 0) - 4 * bool(pics) - 2 * len(big) - 6 * (not titles)
        elif role == "section":
            s += 6 * bool(re.search(r"section|divider|header|break", name)) + 1 * bool(titles)
            s -= 3 * len(big) + 3 * bool(pics) + 6 * (not titles) + 2 * (l["index"] == 0)
        elif role == "bullets":
            s += 5 * (len(big) == 1) + 3 * bool(re.search(r"content|text|bullet", name)) + 2 * bool(titles)
            s -= 4 * bool(pics) + 2 * max(0, len(bodies) - 1) + 6 * (not titles) + 3 * has_ctr
        elif role == "two_column":
            side = len(big) >= 2 and abs(big[0]["y"] - big[1]["y"]) < 0.5
            s += 6 * side + 3 * bool(re.search(r"two|comparison|2", name)) + 2 * bool(titles)
            s -= 4 * bool(pics) + 6 * (not titles)
        elif role == "visual":
            s += 6 * (bool(titles) and not bodies and not subs) + 4 * bool(re.search(r"title only", name))
            s -= 4 * bool(pics) + 6 * (not titles) + 3 * has_ctr + 2 * len(bodies)
        elif role == "blank":
            s += 4 * (not titles and not bodies and not subs) + 4 * bool(re.search(r"blank", name)) - 4 * bool(pics)
        return s

    mapping = {}
    for role in ("title", "section", "bullets", "two_column", "visual", "blank"):
        best = max(layouts, key=lambda l: score(l, role))
        mapping[role] = best["key"] if score(best, role) > 0 else None
    mapping["title"] = mapping["title"] or layouts[0]["key"]
    mapping["bullets"] = mapping["bullets"] or mapping["visual"] or mapping["title"]
    mapping["visual"] = mapping["visual"] or mapping["bullets"]
    mapping["two_column"] = mapping["two_column"] or mapping["visual"]
    mapping["section"] = mapping["section"] or mapping["title"]
    mapping["blank"] = mapping["blank"] or mapping["visual"]
    return mapping
