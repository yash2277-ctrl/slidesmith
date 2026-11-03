"""Brand kits: your colors, fonts and logo as a reusable theme (optionally imported from a website)."""
from __future__ import annotations

import colorsys
import io
import json
import re
import time
import uuid
from collections import Counter
from urllib.parse import urljoin

import httpx
from PIL import Image

from . import config
from .template_analyzer import contrast, luminance, mix

BRAND_DIR = config.DATA_DIR / "brands"
ASSET_DIR = BRAND_DIR / "assets"
ASSET_DIR.mkdir(parents=True, exist_ok=True)
FONTS = ["Segoe UI", "Calibri", "Arial", "Georgia", "Cambria", "Century Gothic", "Trebuchet MS", "Verdana",
         "Times New Roman", "Garamond", "Tahoma", "Arial Black", "Outfit"]
HEADERS = {"User-Agent": "Mozilla/5.0 (SlideSmith brand importer)"}


def _hex(c: str) -> str:
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return "#" + c[:6].upper()


def _shift(color: str, hue: float, light: float = 0.0) -> str:
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb((h + hue) % 1, max(0.2, min(0.75, l + light)), max(0.35, s))
    return "#" + "".join(f"{int(v * 255):02X}" for v in (r, g, b))


def build_theme(bid: str, name: str, primary: str, secondary: str, mode: str, heading: str, body: str,
                logo: dict | None, style: str = "bar") -> dict:
    primary, secondary = _hex(primary), _hex(secondary or _shift(_hex(primary), 0.45))
    dark = mode == "dark"
    bg = "#0F1422" if dark else "#FFFFFF"
    text = "#F3F5FA" if dark else "#141821"
    bg_alt = mix(primary, "#05070D", 0.72) if not dark else mix(primary, "#05070D", 0.6)
    colors = {
        "bg": bg, "bg_alt": bg_alt, "text": text, "muted": mix(text, bg, 0.4),
        "accent": primary, "accent2": secondary, "accent3": _shift(primary, 0.12, 0.05), "accent4": _shift(secondary, -0.15, 0.05),
        "surface": mix(bg, primary, 0.06) if not dark else mix(bg, "#FFFFFF", 0.06),
        "border": mix(bg, text, 0.14), "on_accent": "#FFFFFF" if luminance(primary) < 0.45 else "#111111",
    }
    return {
        "id": f"brand_{bid}", "name": name or "My brand", "kind": "builtin", "brand": True,
        "slide_w": 13.333, "slide_h": 7.5, "dark": dark,
        "fonts": {"heading": heading if heading in FONTS else "Segoe UI", "body": body if body in FONTS else "Segoe UI", "heading_bold": heading != "Arial Black"},
        "title_style": style if style in ("orb", "split", "bar", "frame") else "bar",
        "colors": colors, "logo": logo,
    }


def save_brand(form: dict, logo_bytes: bytes | None) -> dict:
    bid = uuid.uuid4().hex[:8]
    logo = None
    if logo_bytes:
        with Image.open(io.BytesIO(logo_bytes)) as im:
            im = im.convert("RGBA")
            im.thumbnail((800, 800))
            name = f"logo_{bid}.png"
            im.save(ASSET_DIR / name, "PNG")
            logo = {"src": f"/brand-assets/{name}", "w": im.width, "h": im.height}
    elif form.get("logo_url"):
        logo = _download_logo(form["logo_url"], bid)
    theme = build_theme(bid, form.get("name", ""), form.get("primary", "#2563EB"), form.get("secondary", ""),
                        form.get("mode", "light"), form.get("heading", "Segoe UI"), form.get("body", "Segoe UI"),
                        logo, form.get("style", "bar"))
    theme["created"] = time.time()
    (BRAND_DIR / f"{bid}.json").write_text(json.dumps(theme), encoding="utf-8")
    return theme


def get_brand(bid: str) -> dict | None:
    path = BRAND_DIR / f"{bid.removeprefix('brand_')}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def list_brands() -> list[dict]:
    out = []
    for f in sorted(BRAND_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def delete_brand(bid: str) -> None:
    (BRAND_DIR / f"{bid.removeprefix('brand_')}.json").unlink(missing_ok=True)


def _download_logo(url: str, bid: str) -> dict | None:
    try:
        r = httpx.get(url, timeout=15, headers=HEADERS, follow_redirects=True)
        if r.status_code != 200:
            return None
        with Image.open(io.BytesIO(r.content)) as im:
            im = im.convert("RGBA")
            im.thumbnail((800, 800))
            name = f"logo_{bid}.png"
            im.save(ASSET_DIR / name, "PNG")
            return {"src": f"/brand-assets/{name}", "w": im.width, "h": im.height}
    except Exception:
        return None


def import_from_website(url: str) -> dict:
    """Best-effort brand guess from a website: theme color, most used saturated colors, logo, fonts."""
    if not re.match(r"^https?://", url):
        url = "https://" + url
    r = httpx.get(url, timeout=20, headers=HEADERS, follow_redirects=True)
    html = r.text[:600_000]
    css = html
    for href in re.findall(r'<link[^>]+rel=["\']?stylesheet[^>]*href=["\']([^"\']+)', html, re.I)[:3]:
        try:
            css += httpx.get(urljoin(str(r.url), href), timeout=10, headers=HEADERS, follow_redirects=True).text[:400_000]
        except httpx.HTTPError:
            continue
    counts: Counter = Counter()
    theme_color = re.search(r'<meta[^>]+name=["\']theme-color["\'][^>]+content=["\'](#[0-9a-fA-F]{3,6})', html)
    if theme_color:
        counts[_hex(theme_color.group(1))] += 50
    for c in re.findall(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", css):
        hx = _hex(c)
        rr, gg, bb = (int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5))
        _, l, s = colorsys.rgb_to_hls(rr, gg, bb)
        if s > 0.35 and 0.18 < l < 0.75:
            counts[hx] += 1
    picked = []
    for color, _ in counts.most_common(30):
        if all(sum(abs(int(color[i:i + 2], 16) - int(p[i:i + 2], 16)) for i in (1, 3, 5)) > 90 for p in picked):
            picked.append(color)
        if len(picked) == 2:
            break
    logo = None
    for pattern in (r'<img[^>]+(?:class|id|alt|src)=["\'][^"\']*logo[^"\']*["\'][^>]*>',
                    r'<link[^>]+rel=["\']apple-touch-icon[^>]*>', r'<meta[^>]+property=["\']og:image["\'][^>]*>'):
        m = re.search(pattern, html, re.I)
        if m:
            src = re.search(r'(?:src|href|content)=["\']([^"\']+\.(?:png|jpg|jpeg|webp|gif)[^"\']*)', m.group(0), re.I)
            if src:
                logo = urljoin(str(r.url), src.group(1))
                break
    fonts = re.findall(r"fonts\.googleapis\.com/css2?\?family=([A-Za-z+]+)", html)
    title = re.search(r"<title>([^<]{1,80})", html, re.I)
    return {"name": (title.group(1).strip().split("|")[0].split(" - ")[0].strip() if title else ""),
            "primary": picked[0] if picked else "#2563EB", "secondary": picked[1] if len(picked) > 1 else "",
            "logo_url": logo or "", "web_fonts": [f.replace("+", " ") for f in fonts[:2]]}
