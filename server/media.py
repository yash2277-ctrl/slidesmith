"""Icon and photo library.

Icons:  Iconify (https://iconify.design, 200k+ open-source icons) -> rasterized locally to tinted PNGs.
Photos: Openverse (https://openverse.org, Creative Commons images) -> downloaded and cached, with credits.
Both are cached under data/media so a deck keeps working offline once its media is fetched.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import httpx
from PIL import Image, ImageChops, ImageDraw

from . import config

MEDIA_DIR = config.DATA_DIR / "media"
ICON_SVG_DIR = MEDIA_DIR / "icons-svg"
ICON_PNG_DIR = MEDIA_DIR / "icons"
PHOTO_DIR = MEDIA_DIR / "photos"
UPLOAD_DIR = MEDIA_DIR / "uploads"
PAGE_DIR = MEDIA_DIR / "pages"
for d in (ICON_SVG_DIR, ICON_PNG_DIR, PHOTO_DIR, UPLOAD_DIR, PAGE_DIR):
    d.mkdir(parents=True, exist_ok=True)
INDEX = MEDIA_DIR / "index.json"
ICON_SETS = "mdi,ph,tabler,lucide"  # filled & clean line sets that rasterize well
HEADERS = {"User-Agent": "SlideSmith/1.0 (local presentation builder; contact@example.org) python-httpx"}


def _index() -> dict:
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"icons": {}, "photos": {}}


def _save_index(data: dict) -> None:
    INDEX.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60]


# ---------------------------------------------------------------- icons

async def find_icon(keyword: str, family: str = "mdi") -> str | None:
    """Keyword ('rocket', 'data security') -> icon id like 'mdi:rocket-launch' (cached).
    `family` is the deck's icon family (mdi, ph, tabler, lucide) - different decks get different icon styles."""
    family = family if family in ("mdi", "ph", "tabler", "lucide") else "mdi"
    key = _slug(keyword) + ("" if family == "mdi" else "@" + family)
    if not key:
        return None
    idx = _index()
    if key in idx["icons"]:
        return idx["icons"][key]
    icon = None
    try:
        async with httpx.AsyncClient(timeout=12, headers=HEADERS) as client:
            words = [w for w in re.findall(r"[a-z0-9]+", keyword.lower()) if len(w) > 1]
            for query in dict.fromkeys([keyword] + words):
                r = await client.get("https://api.iconify.design/search", params={"query": query, "prefixes": ICON_SETS, "limit": 48})
                icons = r.json().get("icons", []) if r.status_code == 200 else []
                parts = lambda i: set(i.split(":", 1)[1].split("-"))
                icons = [i for i in icons if parts(i) & set(words)] or ([] if query != keyword else icons)
                # most whole-word matches, then the deck's icon family, then the plainest variant
                icons.sort(key=lambda i: (-len(parts(i) & set(words)), not i.startswith(family + ":"),
                                          any(v in i for v in ("outline", "-fill", "duotone", "-bold", "-light", "-thin")), len(i)))
                if icons:
                    icon = icons[0]
                    break
            if icon and not (ICON_SVG_DIR / f"{icon.replace(':', '__')}.svg").exists():
                prefix, name = icon.split(":", 1)
                svg = await client.get(f"https://api.iconify.design/{prefix}/{name}.svg", params={"height": "24"})
                if svg.status_code == 200 and "<svg" in svg.text:
                    (ICON_SVG_DIR / f"{icon.replace(':', '__')}.svg").write_text(svg.text, encoding="utf-8")
                else:
                    icon = None
    except (httpx.HTTPError, ValueError):
        return None
    idx = _index()
    idx["icons"][key] = icon
    _save_index(idx)
    return icon


def icon_file(icon: str, color: str, size: int = 160) -> Path | None:
    """Tinted PNG for an icon id (rasterized from the cached SVG)."""
    if not icon or ":" not in icon:
        return None
    color = (color or "#000000").lstrip("#")[:6].upper()
    out = ICON_PNG_DIR / f"{icon.replace(':', '__')}_{color}_{size}.png"
    if out.exists():
        return out
    svg_path = ICON_SVG_DIR / f"{icon.replace(':', '__')}.svg"
    if not svg_path.exists():
        return None
    try:
        mask = _rasterize_svg(svg_path.read_text(encoding="utf-8"), size)
    except Exception:
        return None
    rgb = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    img = Image.new("RGBA", (size, size), rgb + (0,))
    img.putalpha(mask)
    img.save(out, "PNG")
    return out


def _rasterize_svg(svg_text: str, size: int) -> Image.Image:
    """SVG icon -> antialiased alpha mask (supports filled paths and stroked line icons)."""
    from svgelements import SVG, Path as SPath, Shape

    svg = SVG.parse(io.StringIO(svg_text))
    big = size * 4
    vb = getattr(svg, "viewbox", None)
    vb_w = float(getattr(vb, "width", 0) or 24) if vb else 24.0
    vb_h = float(getattr(vb, "height", 0) or 24) if vb else 24.0
    vb_x = float(getattr(vb, "x", 0) or 0) if vb else 0.0
    vb_y = float(getattr(vb, "y", 0) or 0) if vb else 0.0
    root_w = float(svg.width or vb_w)
    k = big / max(root_w, 1e-6)  # points come out in the root's user units (viewBox mapped to width/height)
    pad = big * 0.04
    k_inner = (big - 2 * pad) / big
    tx = lambda x, y: (pad + (x * k) * k_inner, pad + (y * k) * k_inner)
    mask = Image.new("L", (big, big), 0)
    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        path = SPath(element) if not isinstance(element, SPath) else element
        stroke_w = float(element.stroke_width or 0) if element.stroke is not None and str(element.stroke) not in ("None", "none") else 0
        filled = element.fill is not None and str(element.fill) not in ("None", "none")
        subpaths = []
        for sub in path.as_subpaths():
            sp = SPath(sub)
            length = sp.length(error=1e-2) or 1
            n = max(16, min(800, int(length * k / 5)))
            pts = [tx(p.x, p.y) for p in (sp.point(i / n) for i in range(n + 1)) if p is not None]
            if len(pts) >= 2:
                subpaths.append(pts)
        if filled:
            layer = Image.new("L", (big, big), 0)
            for pts in subpaths:  # even-odd fill: each subpath toggles coverage
                sub = Image.new("L", (big, big), 0)
                if len(pts) >= 3:
                    ImageDraw.Draw(sub).polygon(pts, fill=255)
                layer = ImageChops.logical_xor(layer.convert("1"), sub.convert("1")).convert("L")
            mask = ImageChops.lighter(mask, layer)
        if stroke_w:
            d = ImageDraw.Draw(mask)
            w = max(1, int(round(stroke_w * k * k_inner)))
            for pts in subpaths:
                d.line(pts, fill=255, width=w, joint="curve")
                r = w / 2
                for x, y in (pts[0], pts[-1]):
                    d.ellipse((x - r, y - r, x + r, y + r), fill=255)
    return mask.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- photos

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"


def _strip_html(s) -> str:
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


async def _openverse_candidates(query: str, orientation: str, count: int) -> list[dict]:
    """Openverse CC-photo search, normalized. Unreachable on some networks (Cloudflare 403/hang),
    so it is only one source among two."""
    params = {"q": query, "page_size": count, "mature": "false", "license_type": "commercial,modification"}
    if orientation in ("wide", "tall"):
        params["aspect_ratio"] = orientation
    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
            r = await client.get("https://api.openverse.org/v1/images/", params=params)
            results = r.json().get("results", []) if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        return []
    # prefer large photos from photo sites
    results.sort(key=lambda x: (x.get("category") not in (None, "photograph"), -((x.get("width") or 0) * (x.get("height") or 0))))
    out = []
    for item in results:
        if not item.get("url"):
            continue
        lic = (item.get("license") or "").upper()
        out.append({"url": item["url"], "thumb": item.get("thumbnail") or item["url"],
                    "title": item.get("title") or "Photo", "creator": item.get("creator") or "unknown",
                    "license": f"CC {lic} {item.get('license_version') or ''}".strip(),
                    "source": item.get("foreign_landing_url") or item["url"]})
    return out


_WIKIMEDIA_STOPWORDS = {"a", "an", "the", "on", "in", "with", "of", "and", "for", "at", "by", "from",
                        "to", "into", "over", "under", "during", "through", "or", "as", "is", "are"}


def _search_terms(query: str, max_words: int) -> str:
    """Commons search ANDs all terms, so a long natural-language query matches nothing —
    keep only content words, progressively fewer on retry."""
    words = [w for w in re.findall(r"[A-Za-z0-9']+", query) if w.lower() not in _WIKIMEDIA_STOPWORDS]
    return " ".join(words[:max_words])


async def _wikimedia_candidates(query: str, orientation: str, count: int) -> list[dict]:
    """Wikimedia Commons search: no key, everything free-licensed, and reachable on networks
    where Openverse is blocked. Returns the same normalized shape as _openverse_candidates."""
    pages = []
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
            for words in (8, 5, 3):
                params = {"action": "query", "format": "json", "formatversion": "2",
                          "generator": "search", "gsrsearch": f"filetype:bitmap {_search_terms(query, words)}",
                          "gsrnamespace": 6, "gsrlimit": count, "prop": "imageinfo",
                          "iiprop": "url|size|extmetadata", "iiurlwidth": 1600}
                r = await client.get(WIKIMEDIA_API, params=params)
                pages = ((r.json().get("query") or {}).get("pages") or []) if r.status_code == 200 else []
                if pages:
                    break
    except (httpx.HTTPError, ValueError):
        return []
    out = []
    for page in sorted(pages, key=lambda p: p.get("index", 99)):
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        meta = info.get("extmetadata") or {}
        val = lambda k: _strip_html((meta.get(k) or {}).get("value"))  # noqa: E731
        w, h = info.get("width") or 0, info.get("height") or 0
        out.append({"url": url, "thumb": url,
                    "title": (page.get("title") or "Photo").removeprefix("File:"),
                    "creator": val("Artist") or val("Credit") or "unknown",
                    "license": val("LicenseShortName") or "free license (Wikimedia Commons)",
                    "source": info.get("descriptionurl") or url,
                    "w": w, "h": h})
    if orientation == "wide":
        out = [c for c in out if c["w"] >= c["h"]] or out
    elif orientation == "tall":
        out = [c for c in out if c["h"] >= c["w"]] or out
    return out


async def find_photo(query: str, orientation: str = "any", pick: int = 0) -> dict | None:
    """Search free-photo providers (Wikimedia Commons first, then Openverse), download the photo,
    return {src, credit, w, h}. `pick` chooses among the good matches so decks on the same topic
    don't share photos."""
    pick = max(0, int(pick or 0)) % 5
    key = _slug(query) + ("-" + orientation if orientation != "any" else "") + (f"#{pick}" if pick else "")
    if not _slug(query):
        return None
    idx = _index()
    if key in idx["photos"] and (PHOTO_DIR / idx["photos"][key]["file"]).exists():
        return _photo_info(idx["photos"][key])
    cands = await _wikimedia_candidates(query, orientation, 10)
    if len(cands) <= pick:
        cands += await _openverse_candidates(query, orientation, 10)
    try:
        async with httpx.AsyncClient(timeout=25, headers=HEADERS, follow_redirects=True) as client:
            for item in cands[pick:] + cands[:pick]:
                url = item.get("url")
                if not url:
                    continue
                try:
                    img_r = await client.get(url)
                    if img_r.status_code != 200 or len(img_r.content) < 8000:
                        continue
                    with Image.open(io.BytesIO(img_r.content)) as im:
                        im = im.convert("RGB")
                        if min(im.size) < 400:
                            continue
                        im.thumbnail((1920, 1920))
                        name = hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg"
                        im.save(PHOTO_DIR / name, "JPEG", quality=86)
                        w, h = im.size
                except (httpx.HTTPError, OSError):
                    continue
                credit = f'"{(item.get("title") or "Photo")[:60]}" by {item.get("creator") or "unknown"}, {item.get("license") or "CC"}'.strip()
                entry = {"file": name, "credit": credit, "w": w, "h": h, "source": item.get("source") or url}
                idx = _index()
                idx["photos"][key] = entry
                _save_index(idx)
                return _photo_info(entry)
    except httpx.HTTPError:
        return None
    return None


def _photo_info(entry: dict) -> dict:
    return {"src": f"/media/photos/{entry['file']}", "credit": entry["credit"], "w": entry["w"], "h": entry["h"],
            "source": entry.get("source", "")}


def save_upload(data: bytes, filename: str) -> dict:
    """A user's own image -> cached JPEG/PNG usable on slides."""
    with Image.open(io.BytesIO(data)) as im:
        has_alpha = im.mode in ("RGBA", "LA", "P")
        im = im.convert("RGBA" if has_alpha else "RGB")
        im.thumbnail((2400, 2400))
        name = hashlib.sha1(data).hexdigest()[:16] + (".png" if has_alpha else ".jpg")
        im.save(UPLOAD_DIR / name, "PNG" if has_alpha else "JPEG", quality=88)
        w, h = im.size
    return {"src": f"/media/uploads/{name}", "credit": "", "w": w, "h": h, "source": "upload"}


def local_path(src: str) -> Path | None:
    """Map a /media/... URL used on slides to the file on disk (icons are rasterized on demand)."""
    m = re.match(r"^/media/icon/([^/]+)/([0-9A-Fa-f]{6})\.png$", src or "")
    if m:
        return icon_file(m.group(1), m.group(2))
    m = re.match(r"^/media/(photos|uploads|pages)/([\w.-]+)$", src or "")
    if m:
        path = {"photos": PHOTO_DIR, "uploads": UPLOAD_DIR, "pages": PAGE_DIR}[m.group(1)] / m.group(2)
        return path if path.exists() else None
    m = re.match(r"^/tpl-assets/([^/]+)/([^/]+)$", src or "")
    if m:
        path = config.TEMPLATES_DIR / m.group(1) / "assets" / m.group(2)
        return path if path.exists() else None
    m = re.match(r"^/brand-assets/([\w.-]+)$", src or "")
    if m:
        path = config.DATA_DIR / "brands" / "assets" / m.group(1)
        return path if path.exists() else None
    return None


# ---------------------------------------------------------------- pages of attached documents

def save_page(data: bytes, tag: str, page: int) -> dict | None:
    """One rendered page of a user's attached document -> a slide-ready image.

    `tag` is a stable id for the document (its own hash), so re-attaching the same
    file reuses the same cached page instead of storing a second copy."""
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            im.thumbnail((2400, 2400))
            name = f"{_slug(tag) or hashlib.sha1(data).hexdigest()[:16]}_p{page}.jpg"
            im.save(PAGE_DIR / name, "JPEG", quality=90)
            w, h = im.size
    except Exception:
        return None
    return {"src": f"/media/pages/{name}", "w": w, "h": h, "page": page}


def icon_url(icon: str, color: str) -> str:
    return f"/media/icon/{icon}/{(color or '#000000').lstrip('#')[:6].upper()}.png"


# ---------------------------------------------------------------- resolve a slide's media

ICON_LISTS = {"cards": "cards", "stats": "stats", "timeline": "steps", "process": "steps", "matrix": "quadrants",
              "funnel": "stages", "diagram": "nodes"}


async def prepare(spec: dict, dna: dict | None = None) -> dict:
    """Resolve icon keywords and photo queries in a finished slide spec (network, cached)."""
    import asyncio
    dna = dna or {}
    family = dna.get("icon_set", "mdi")
    key = ICON_LISTS.get(spec.get("type"))
    if key:
        todo = []
        for item in spec.get(key, []):
            icon = item.get("icon") or ""
            kw = item.get("icon_kw") or (icon.split(":", 1)[1].replace("-", " ") if ":" in icon else icon)
            if kw and (":" not in icon or not icon.startswith(family + ":")):
                item["icon_kw"] = kw
                todo.append(item)
        found = await asyncio.gather(*(find_icon(item["icon_kw"], family) for item in todo), return_exceptions=True)
        for item, icon in zip(todo, found):
            if isinstance(icon, str) and icon:
                item["icon"] = icon
            elif ":" not in (item.get("icon") or ""):
                item["icon"] = ""
    img = spec.get("image")
    orient = "tall" if spec.get("type") == "image" else "wide"
    if isinstance(img, str) and img.strip():
        pick = (dna.get("photo_pick", 0) + len(img)) % 5
        photo = await find_photo(img, orient, pick) or await find_photo(img, "any", pick)
        spec["image"] = ({**photo, "query": img} if photo else {"query": img, "src": ""})
    elif isinstance(img, dict) and img.get("query") and not img.get("src"):
        # a previous prepare found no photo (offline/blocked) - retry it now
        q = img["query"]
        pick = (dna.get("photo_pick", 0) + len(q)) % 5
        photo = await find_photo(q, orient, pick) or await find_photo(q, "any", pick)
        if photo:
            spec["image"] = {**photo, "query": q}
    return spec


def resolve_document(spec: dict, sources: list[dict]) -> dict:
    """Turn a "document" slide's doc id + page numbers into the actual page images.

    The AI only knows the handle (#D1) and which pages it wants; the real file URLs
    stay a server-side detail, so a stale or invented handle simply renders nothing
    instead of putting a broken image on the slide."""
    if spec.get("type") != "document":
        return spec
    doc = str(spec.get("doc", "")).strip().upper()
    src = next((s for s in sources if (s.get("doc_id") or "").upper() == doc), None)
    pages = {p["page"]: p for p in (src.get("pages") or [])} if src else {}
    wanted = spec.get("pages") or [1]
    got = []
    for num in wanted:
        page = pages.get(num)
        if page and media_page_exists(page):
            got.append(page)
    if not got:  # the whole slide's page set was unusable - keep it valid so it isn't rejected
        got = [p for p in (src or {}).get("pages", [])][:len(wanted)] or []
    spec["page_images"] = [{"src": p["src"], "w": p.get("w"), "h": p.get("h"), "page": p.get("page")} for p in got]
    if src:
        spec["doc_name"] = src.get("name", "")
    return spec


def media_page_exists(page: dict) -> bool:
    path = local_path(page.get("src", ""))
    return bool(path and path.exists())


async def search_photos(query: str, count: int = 12) -> list[dict]:
    """Photo choices for the editor (thumbnails only; the chosen one is downloaded by fetch_photo)."""
    cands = await _wikimedia_candidates(query, "any", count)
    if len(cands) < count:
        cands += await _openverse_candidates(query, "any", count - len(cands))
    return [{"url": c["url"], "thumb": c["thumb"],
             "credit": f'"{c["title"][:60]}" by {c["creator"]}, {c["license"]}',
             "source": c["source"]} for c in cands[:count]]


async def fetch_photo(url: str, credit: str = "", source: str = "") -> dict | None:
    """Download one chosen photo into the cache."""
    try:
        async with httpx.AsyncClient(timeout=25, headers=HEADERS, follow_redirects=True) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return None
        with Image.open(io.BytesIO(r.content)) as im:
            im = im.convert("RGB")
            im.thumbnail((1920, 1920))
            name = hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg"
            im.save(PHOTO_DIR / name, "JPEG", quality=86)
            w, h = im.size
    except (httpx.HTTPError, OSError):
        return None
    return _photo_info({"file": name, "credit": credit, "w": w, "h": h, "source": source or url})
