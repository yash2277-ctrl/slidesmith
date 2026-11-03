"""Rasterize a slide display list to PNG so the AI can *see* what it built,
and collect automatic quality checks (overflow, leftover sample text, sparse slides)."""
from __future__ import annotations

import io
import math
import os
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config, media

FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
LOCAL_FONT_DIR = Path(__file__).parent / "fonts"
FONT_FILES = {  # regular, bold, italic, bold-italic
    "segoe ui": ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    "georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "times new roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "arial black": ("ariblk.ttf",) * 4,
    "century gothic": ("GOTHIC.TTF", "GOTHICB.TTF", "GOTHICI.TTF", "GOTHICBI.TTF"),
    "cambria": ("cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf"),
    "trebuchet ms": ("trebuc.ttf", "trebucbd.ttf", "trebucit.ttf", "trebucbi.ttf"),
    "verdana": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
    "tahoma": ("tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf"),
    "garamond": ("GARA.TTF", "GARABD.TTF", "GARAIT.TTF", "GARABD.TTF"),
    "outfit": ("Outfit-Regular.ttf", "Outfit-Bold.ttf", "Outfit-Italic.ttf", "Outfit-Bold.ttf"),
    "ink free": ("Inkfree.ttf",) * 4,
    "segoe print": ("segoepr.ttf", "segoeprb.ttf", "segoepr.ttf", "segoeprb.ttf"),
    "comic sans ms": ("comic.ttf", "comicbd.ttf", "comici.ttf", "comicz.ttf"),
}
SAMPLE_RE = re.compile(r"<[^>]+>|x{4,}|lorem|ipsum|click to add", re.I)
BRACKET_RE = re.compile(r"\[[A-Za-z][^\]]{2,30}\]")


@lru_cache(maxsize=256)
def _font(face: str, bold: bool, italic: bool, px: int):
    files = FONT_FILES.get((face or "").lower().strip()) or FONT_FILES["arial"]
    name = files[(1 if bold else 0) + (2 if italic else 0)]
    for candidate in (name, files[0], "arial.ttf"):
        for base in (LOCAL_FONT_DIR, FONT_DIR):
            path = base / candidate
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), max(4, px))
                except OSError:
                    continue
    return ImageFont.load_default(size=max(4, px))


def _rgba(hex_color: str | None, alpha: float = 1.0):
    if not hex_color:
        return None
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * max(0.0, min(1.0, alpha))))


def _asset(src: str) -> Path | None:
    return media.local_path(src)


def _path_points(d: str, x0, y0, w, h):
    """Very small SVG path -> polygons converter for M/L/C/Q/A/Z in a 0..1000 box."""
    tokens = re.findall(r"[MLCQAZ]|-?\d+(?:\.\d+)?", d)
    polys, cur, pts, i = [], (0.0, 0.0), [], 0
    sx, sy = w / 1000.0, h / 1000.0
    to = lambda px, py: (x0 + px * sx, y0 + py * sy)

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v
    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        if cmd == "M":
            if len(pts) > 2:
                polys.append(pts)
            cur = (num(), num())
            pts = [to(*cur)]
        elif cmd == "L":
            cur = (num(), num())
            pts.append(to(*cur))
        elif cmd in ("C", "Q"):
            n = 3 if cmd == "C" else 2
            ctrl = [(num(), num()) for _ in range(n)]
            p0 = cur
            for k in range(1, 9):
                t = k / 8
                if n == 3:
                    (x1, y1), (x2, y2), (x3, y3) = ctrl
                    bx = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t * t * x2 + t ** 3 * x3
                    by = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t * t * y2 + t ** 3 * y3
                else:
                    (x1, y1), (x2, y2) = ctrl
                    bx = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * x1 + t * t * x2
                    by = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * y1 + t * t * y2
                pts.append(to(bx, by))
            cur = ctrl[-1]
        elif cmd == "A":
            for _ in range(5):
                num()
            cur = (num(), num())
            pts.append(to(*cur))
        elif cmd == "Z":
            if len(pts) > 2:
                polys.append(pts)
            pts = [to(*cur)]
    if len(pts) > 2:
        polys.append(pts)
    return polys


class Raster:
    def __init__(self, layout: dict, theme: dict, ppi: int = 72):
        self.L, self.theme, self.s = layout, theme, ppi
        self.W, self.H = int(layout["w"] * ppi), int(layout["h"] * ppi)
        self.img = Image.new("RGBA", (self.W, self.H), (255, 255, 255, 255))
        self.issues: list[str] = []

    def px(self, v):
        return int(round(v * self.s))

    def overlay(self):
        return Image.new("RGBA", self.img.size, (0, 0, 0, 0))

    def fill_box(self, box, fill, radius=0, ellipse=False, line=None, alpha=1.0, rot=0.0):
        x, y, w, h = (self.px(box[k]) for k in ("x", "y", "w", "h"))
        if w <= 0 or h <= 0:
            return
        color = None
        if isinstance(fill, dict):
            if fill.get("type") == "solid":
                color = _rgba(fill["color"], fill.get("alpha", 1) * alpha)
            elif fill.get("type") == "gradient" and fill.get("stops"):
                self.gradient((x, y, w, h), fill)
                color = None
            elif fill.get("type") == "image":
                self.paste(fill["src"], (x, y, w, h))
        elif isinstance(fill, str):
            color = _rgba(fill, alpha)
        outline = _rgba(line["color"], line.get("alpha", 1)) if line else None
        width = max(1, int(line["width"] * self.s / 72)) if line else 0
        if color is None and outline is None:
            return
        layer = self.overlay()
        d = ImageDraw.Draw(layer)
        if rot and not ellipse:  # rotated rectangle -> polygon (its corners around the centre)
            cx, cy = x + w / 2, y + h / 2
            a = math.radians(rot)
            cos_a, sin_a = math.cos(a), math.sin(a)
            pts = [(cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)
                   for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
            d.polygon(pts, fill=color, outline=outline)
            if outline and width:
                d.line(pts + [pts[0]], fill=outline, width=width, joint="curve")
        else:
            rect = (x, y, x + w, y + h)
            if ellipse:
                d.ellipse(rect, fill=color, outline=outline, width=width)
            elif radius:
                d.rounded_rectangle(rect, radius=self.px(radius), fill=color, outline=outline, width=width)
            else:
                d.rectangle(rect, fill=color, outline=outline, width=width)
        self.img = Image.alpha_composite(self.img, layer)

    def triangle(self, el):
        x, y, w, h = (self.px(el[k]) for k in ("x", "y", "w", "h"))
        pts = [(x, y + h), (x + w, y + h), (x + w / 2, y)]
        outline = _rgba(el["line"]["color"]) if el.get("line") else None
        width = max(1, int(el["line"]["width"] * self.s / 72)) if el.get("line") else 0
        layer = self.overlay()
        d = ImageDraw.Draw(layer)
        d.polygon(pts, fill=_rgba(el.get("fill"), el.get("alpha", 1)), outline=outline)
        if outline and width:
            d.line(pts + [pts[0]], fill=outline, width=width, joint="curve")
        self.img = Image.alpha_composite(self.img, layer)

    def gradient(self, rect, fill):
        x, y, w, h = rect
        a, b = _rgba(fill["stops"][0]["color"]), _rgba(fill["stops"][-1]["color"])
        horizontal = (round(fill.get("angle", 90)) % 180) in range(0, 45) or (round(fill.get("angle", 90)) % 180) >= 135
        n = w if horizontal else h
        strip = Image.new("RGBA", (max(n, 1), 1))
        for i in range(max(n, 1)):
            t = i / max(n - 1, 1)
            strip.putpixel((i, 0), tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(4)))
        grad = strip.resize((w, h)) if horizontal else strip.rotate(-90, expand=True).resize((w, h))
        self.img.alpha_composite(grad, (max(x, 0), max(y, 0))) if x >= 0 and y >= 0 else None

    def paste(self, src, rect):
        path = _asset(src)
        if not path or not path.exists():
            return
        try:
            with Image.open(path) as im:
                im = im.convert("RGBA").resize((max(1, rect[2]), max(1, rect[3])))
            layer = self.overlay()
            layer.paste(im, (rect[0], rect[1]))
            self.img = Image.alpha_composite(self.img, layer)
        except Exception:
            pass

    def background(self):
        lay = None
        if self.theme.get("kind") == "custom" and self.L.get("layout_key"):
            lay = next((l for l in self.theme.get("layouts", []) if l["key"] == self.L["layout_key"]), None)
        bg = self.L.get("bg") or (lay or {}).get("background")
        base = (lay or {}).get("bg_color") or self.theme.get("colors", {}).get("bg", "#FFFFFF")
        self.fill_box({"x": 0, "y": 0, "w": self.L["w"], "h": self.L["h"]}, {"type": "solid", "color": base})
        if bg:
            self.fill_box({"x": 0, "y": 0, "w": self.L["w"], "h": self.L["h"]}, bg)
        if lay and not self.L.get("hide_master"):
            for d in lay.get("decor", []):
                self.decor(d)

    def decor(self, d):
        if d["kind"] == "image":
            self.paste(d["src"], (self.px(d["x"]), self.px(d["y"]), self.px(d["w"]), self.px(d["h"])))
        elif d["kind"] == "line":
            dr = ImageDraw.Draw(self.img)
            x0, y0, x1, y1 = d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]
            if d.get("flipH"):
                x0, x1 = x1, x0
            if d.get("flipV"):
                y0, y1 = y1, y0
            dr.line([(self.px(x0), self.px(y0)), (self.px(x1), self.px(y1))], fill=_rgba(d["line"]["color"]), width=max(1, int(d["line"]["width"] * self.s / 72)))
        elif d.get("geom") == "path" and d.get("path"):
            fill = d.get("fill") or {}
            color = _rgba(fill.get("color") if fill.get("type") == "solid" else (fill.get("stops") or [{}])[0].get("color"), fill.get("alpha", 1))
            layer = self.overlay()
            dr = ImageDraw.Draw(layer)
            for poly in _path_points(d["path"], self.px(d["x"]), self.px(d["y"]), self.px(d["w"]), self.px(d["h"])):
                dr.polygon(poly, fill=color, outline=_rgba(d["line"]["color"]) if d.get("line") else None)
            self.img = Image.alpha_composite(self.img, layer)
        else:
            self.fill_box(d, d.get("fill"), radius=min(d["w"], d["h"]) * 0.16 if d.get("geom") == "roundRect" else 0,
                          ellipse=d.get("geom") == "ellipse", line=d.get("line"))
        if d.get("text"):
            t = d["text"]
            self.text({"x": d["x"] + 0.1, "y": d["y"] + 0.05, "w": d["w"] - 0.2, "h": d["h"] - 0.1,
                       "paras": [{"text": t["text"], "size": t["size"], "color": t.get("color") or "#000000", "bold": t.get("bold"), "font": "body"}],
                       "align": {"ctr": "c", "r": "r"}.get(t.get("align"), "l"), "valign": {"ctr": "m", "b": "b"}.get(t.get("anchor"), "t")}, check=False)

    # ---------------------------------------------------------------- text
    def _face(self, p):
        fonts = self.theme.get("fonts", {})
        return p.get("face") or (fonts.get("heading") if p.get("font") == "heading" else fonts.get("body")) or "Arial"

    def _wrap(self, text, font, width):
        lines = []
        for raw in (text.replace("\t", "    ") or " ").split("\n"):
            words, cur = raw.split(" "), ""
            for w in words:
                trial = (cur + " " + w) if cur else w
                if font.getlength(trial) <= width or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = w
            lines.append(cur)
        return lines

    def text(self, el, check=True):
        x, y, w, h = el["x"], el["y"], el["w"], el["h"]
        line_k = el.get("line", 1.15)
        laid, total = [], 0.0
        for p in el["paras"]:
            size_px = max(4, int(p["size"] * self.s / 72))
            font = _font(self._face(p), bool(p.get("bold")), bool(p.get("italic")), size_px)
            indent = self.px(0.35 * p.get("level", 0)) + (int(size_px * 1.1) if p.get("bullet") else 0)
            text = p["text"].upper() if p.get("caps") else p["text"]
            lines = self._wrap(text, font, max(10, self.px(w) - indent))
            lh = size_px * line_k
            laid.append((p, font, indent, lines, lh, size_px))
            total += lh * len(lines) + p.get("space", 0) * self.s / 72
        box_h = self.px(h)
        if check and total > box_h * 1.08 and any(p["text"].strip() for p in el["paras"]):
            first = next((p["text"].strip() for p in el["paras"] if p["text"].strip()), "")[:50]
            self.issues.append(f"Text overflows its box by {int((total / max(box_h, 1) - 1) * 100)}% (starts \"{first}\") - shorten it or split the slide.")
        if check and y + total / self.s > self.L["h"] + 0.05:
            self.issues.append("Some text runs off the bottom edge of the slide.")
        top = self.px(y) + {"m": (box_h - total) / 2, "b": box_h - total}.get(el.get("valign"), 0)
        dr = ImageDraw.Draw(self.img)
        cy = top
        for p, font, indent, lines, lh, size_px in laid:
            color = _rgba(p.get("color") or "#000000")
            align = p.get("align") or el.get("align", "l")
            for k, ln in enumerate(lines):
                tw = font.getlength(ln)
                if align == "c":
                    tx = self.px(x) + (self.px(w) - tw) / 2
                elif align == "r":
                    tx = self.px(x) + self.px(w) - tw
                else:
                    tx = self.px(x) + indent
                if k == 0 and p.get("bullet") and p["text"].strip():
                    dr.text((self.px(x) + indent - size_px * 1.1 + self.px(0.0), cy), "\u2022", font=font,
                            fill=_rgba(p["bullet"]) if str(p["bullet"]).startswith("#") else color)
                dr.text((tx, cy), ln, font=font, fill=color)
                cy += lh
            cy += p.get("space", 0) * self.s / 72

    # ---------------------------------------------------------------- data
    def chart(self, el):
        ch = el["chart"]
        x, y, w, h = (self.px(el[k]) for k in ("x", "y", "w", "h"))
        dr = ImageDraw.Draw(self.img)
        cols = [_rgba(c) for c in el["colors"]]
        font = _font(self._face({"face": el.get("face")}), False, False, max(8, int(12 * self.s / 72)))
        series, cats = ch.get("series", []), ch.get("categories", [])
        if not series or not cats:
            return
        if ch["kind"] in ("pie", "doughnut"):
            vals = [max(0.0, v) for v in series[0]["values"]]
            tot = sum(vals) or 1
            r = min(w * 0.32, h * 0.44)
            cx, cy = x + w * 0.38, y + h / 2
            a0 = -90.0
            for i, v in enumerate(vals):
                a1 = a0 + v / tot * 360
                dr.pieslice((cx - r, cy - r, cx + r, cy + r), a0, a1, fill=cols[i % len(cols)])
                a0 = a1
            if ch["kind"] == "doughnut":
                dr.ellipse((cx - r * .55, cy - r * .55, cx + r * .55, cy + r * .55), fill=_rgba(el.get("bg") or "#FFFFFF"))
            for i, c in enumerate(cats):
                ly = cy - len(cats) * 11 + i * 22
                dr.rectangle((x + w * .74, ly, x + w * .74 + 10, ly + 10), fill=cols[i % len(cols)])
                dr.text((x + w * .74 + 16, ly - 3), c, font=font, fill=_rgba(el["text"]))
            return
        vmax = max([v for s in series for v in s["values"]] + [0]) or 1
        n = len(cats)
        pl, pb = int(w * 0.08), int(h * 0.12)
        if ch["kind"] == "bar":
            pl = int(min(w * 0.32, max(font.getlength(c) for c in cats) + 14))
        pw, ph = w - pl, h - pb
        dr.line([(x + pl, y + ph), (x + w, y + ph)], fill=_rgba(el["grid"]), width=1)
        band = (ph if ch["kind"] == "bar" else pw) / n
        for ci, c in enumerate(cats):
            for si, s in enumerate(series):
                v = s["values"][ci] if ci < len(s["values"]) else 0
                col = cols[si % len(cols)]
                if ch["kind"] == "bar":
                    bh = band * 0.7 / len(series)
                    by = y + ci * band + band * .15 + si * bh
                    dr.rectangle((x + pl, by, x + pl + pw * v / vmax * 0.9, by + bh * .9), fill=col)
                elif ch["kind"] == "line":
                    px_ = x + pl + band * ci + band / 2
                    py_ = y + ph - ph * v / vmax * 0.9
                    if ci:
                        pv = s["values"][ci - 1]
                        dr.line([(x + pl + band * (ci - 1) + band / 2, y + ph - ph * pv / vmax * .9), (px_, py_)], fill=col, width=3)
                    dr.ellipse((px_ - 4, py_ - 4, px_ + 4, py_ + 4), fill=col)
                else:
                    bw = band * 0.62 / len(series)
                    bx = x + pl + band * ci + band * .19 + si * bw
                    dr.rectangle((bx, y + ph - ph * v / vmax * .9, bx + bw * .92, y + ph), fill=col)
            if ch["kind"] != "bar":
                dr.text((x + pl + band * ci + band / 2 - font.getlength(c) / 2, y + ph + 4), c, font=font, fill=_rgba(el["text"]))
            else:
                dr.text((x + pl - 8 - font.getlength(c), y + ci * band + band / 2 - 6), c, font=font, fill=_rgba(el["text"]))

    def table(self, el):
        rows = [el["columns"]] + el["rows"]
        x, y, w = self.px(el["x"]), self.px(el["y"]), self.px(el["w"])
        rh = self.px(el["h"]) / max(len(rows), 1)
        cw = w / max(len(el["columns"]), 1)
        dr = ImageDraw.Draw(self.img)
        for r, row in enumerate(rows):
            fill = el["header_fill"] if r == 0 else (el["fill_a"] if r % 2 else el["fill_b"])
            dr.rectangle((x, y + r * rh, x + w, y + (r + 1) * rh), fill=_rgba(fill))
            font = _font(self._face({"face": el.get("face")}), r == 0, False, int(el["size"] * self.s / 72))
            for c, val in enumerate(row):
                txt = val if font.getlength(val) < cw - 10 else val[: max(3, int(len(val) * (cw - 10) / max(font.getlength(val), 1)) - 1)] + "…"
                dr.text((x + c * cw + 8, y + r * rh + rh / 2 - el["size"] * self.s / 144), txt, font=font,
                        fill=_rgba(el["header_text"] if r == 0 else el["text"]))

    def tpltable(self, el):
        x, y = self.px(el["x"]), self.px(el["y"])
        total = sum(el["cols"]) or 1
        dr = ImageDraw.Draw(self.img)
        cy = y
        for row in el["rows"]:
            rh = max(self.px(row["h"]), 14)
            cx = x
            for c, cell in enumerate(row["cells"]):
                cw = self.px(el["w"]) * (el["cols"][c] / total if c < len(el["cols"]) else 0)
                dr.rectangle((cx, cy, cx + cw, cy + rh), fill=_rgba(cell.get("fill")) if cell.get("fill") else None, outline=(90, 90, 90, 255))
                p = cell["paras"][0] if cell["paras"] else {"size": 12, "bold": False, "color": "#000000"}
                font = _font(self._face(p), bool(p.get("bold")), False, max(6, int(p["size"] * self.s / 72)))
                dr.text((cx + 6, cy + 3), cell["text"][:60], font=font, fill=_rgba(p.get("color") or "#000000"))
                cx += cw
            cy += rh

    def picture(self, el):
        path = _asset(el.get("src", ""))
        x, y, w, h = (self.px(el[k]) for k in ("x", "y", "w", "h"))
        if not path or not path.exists() or w <= 0 or h <= 0:
            return
        try:
            with Image.open(path) as im:
                im = im.convert("RGBA")
                if el.get("fit") == "contain":
                    im.thumbnail((w, h))
                    ox, oy = x + (w - im.width) // 2, y + (h - im.height) // 2
                else:  # cover: crop to the box's aspect ratio
                    ar, br = im.width / im.height, w / h
                    if ar > br:
                        cw = int(im.height * br)
                        im = im.crop(((im.width - cw) // 2, 0, (im.width + cw) // 2, im.height))
                    else:
                        ch = int(im.width / br)
                        im = im.crop((0, (im.height - ch) // 2, im.width, (im.height + ch) // 2))
                    im = im.resize((w, h))
                    ox, oy = x, y
            layer = self.overlay()
            layer.paste(im, (ox, oy), im)
            self.img = Image.alpha_composite(self.img, layer)
        except Exception:
            pass

    def connector(self, el):
        """A line between two points, with an arrowhead where it ends."""
        x1, y1 = self.px(el["x1"]), self.px(el["y1"])
        x2, y2 = self.px(el["x2"]), self.px(el["y2"])
        color = _rgba(el.get("color"))
        w = max(1, int(el.get("width", 1.5) * self.s / 72))
        layer = self.overlay()
        d = ImageDraw.Draw(layer)
        if el.get("dash"):
            # a dashed line: walk the segment in on/off runs
            import math as _m
            dist = _m.hypot(x2 - x1, y2 - y1)
            if dist > 0:
                ux, uy = (x2 - x1) / dist, (y2 - y1) / dist
                on, t = max(2, w * 3), 0.0
                while t < dist:
                    e = min(t + on, dist)
                    d.line([(x1 + ux * t, y1 + uy * t), (x1 + ux * e, y1 + uy * e)], fill=color, width=w)
                    t = e + on * 0.7
        else:
            d.line([(x1, y1), (x2, y2)], fill=color, width=w)
        if el.get("arrow"):
            ang = math.atan2(y2 - y1, x2 - x1)
            size = max(6.0, w * 3.4)
            pts = [(x2, y2),
                   (x2 - size * math.cos(ang - 0.42), y2 - size * math.sin(ang - 0.42)),
                   (x2 - size * math.cos(ang + 0.42), y2 - size * math.sin(ang + 0.42))]
            d.polygon(pts, fill=color)
        self.img = Image.alpha_composite(self.img, layer)

    def chevron(self, el):
        x, y, w, h = (self.px(el[k]) for k in ("x", "y", "w", "h"))
        d = min(w * 0.5, h * 0.5)
        pts = [(x, y), (x + w - d, y), (x + w, y + h / 2), (x + w - d, y + h), (x, y + h)]
        if el.get("geom") == "chevron":
            pts.append((x + d, y + h / 2))
        outline = _rgba(el["line"]["color"]) if el.get("line") else None
        width = max(1, int(el["line"]["width"] * self.s / 72)) if el.get("line") else 0
        dr = ImageDraw.Draw(self.img)
        dr.polygon(pts, fill=_rgba(el["fill"]), outline=outline)
        if outline and width:
            dr.line(pts + [pts[0]], fill=outline, width=width, joint="curve")

    def render(self) -> tuple[bytes, list[str]]:
        self.background()
        for el in self.L.get("elements", []):
            t = el["t"]
            if t == "decor":
                self.decor(el["d"])
            elif t in ("rect", "ellipse"):
                self.fill_box(el, el.get("fill"), radius=el.get("radius", 0), ellipse=t == "ellipse", line=el.get("line"), alpha=el.get("alpha", 1), rot=el.get("rot", 0))
            elif t == "triangle":
                self.triangle(el)
            elif t == "text":
                self.text(el, check=not el.get("static"))
            elif t == "chart":
                self.chart(el)
            elif t == "table":
                self.table(el)
            elif t == "tpltable":
                self.tpltable(el)
            elif t == "image":
                self.picture(el)
            elif t == "shape":
                self.chevron(el)
            elif t == "connector":
                self.connector(el)
        buf = io.BytesIO()
        self.img.convert("RGB").save(buf, "PNG", optimize=True)
        return buf.getvalue(), self.issues


def render_png(layout: dict, theme: dict, ppi: int = 72) -> bytes:
    return Raster(layout, theme, ppi).render()[0]


def inspect(layout: dict, spec: dict, theme: dict) -> tuple[bytes, list[str]]:
    """PNG + a list of human-readable problems the reviewer should consider."""
    png, issues = Raster(layout, theme).render()
    issues = ["MUST FIX: " + i if "overflow" in i.lower() else i for i in issues]
    elements = layout.get("elements", [])
    for el in elements:
        if el.get("shrink") and el["shrink"] < 0.85:
            issues.append(f"Text was auto-shrunk to {int(el['shrink'] * 100)}% to fit its box - consider shortening it.")
        if el["t"] == "text" and el.get("static"):
            sample = next((p["text"].strip() for p in el["paras"] if SAMPLE_RE.search(p["text"] or "")), None)
            if sample:
                issues.append(f"Template sample text is still shown: \"{sample[:60]}\" (keep only if the user hasn't given this detail).")
        if el["t"] == "text" and not el.get("static"):
            for p in el["paras"]:
                txt = (p.get("text") or "").strip()
                size = p.get("size") or 0
                if txt and 0 < size < 9 and len(txt) >= 25 and not txt.startswith("Photo: "):
                    issues.append(f"MUST FIX: text renders at {size:g}pt - too small to read; cut words instead of shrinking further.")
            first = (el["paras"][0].get("text") or "").strip() if el["paras"] else ""
            if first.startswith("Image:") or first.startswith("Image :"):
                issues.append("MUST FIX: a photo slot is still an empty placeholder (no photo was found) - name a more common subject, or drop the photo from this slide.")
            ph = BRACKET_RE.search(first) or next((m for p in el["paras"] for m in [BRACKET_RE.search(p.get("text") or "")] if m), None)
            if ph:
                issues.append(f'MUST FIX: placeholder text "{ph.group(0)}" is still there - use real details from the deck, or remove it.')
    words = sum(len((p.get("text") or "").split()) for el in elements if el["t"] == "text" and not el.get("static") for p in el["paras"])
    role = next((t["role"] for t in theme.get("slides", []) if t["id"] == spec.get("source")), None) if spec.get("type") == "template" else None
    thin = 30 if role == "content" else 18
    # a document slide is a picture of a page: the words are in the image, not in text
    visual = spec.get("type") in ("document", "diagram")
    if (spec.get("type") not in ("title", "closing", "section", "quote", "template", "chart", "stats") or role == "content") and words < thin and not visual:
        issues.append(f"The slide looks sparse ({words} words of content) - add specific detail.")
    return png, list(dict.fromkeys(issues))
