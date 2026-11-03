"""Endpoints for editing, media, smart layouts, history, exports and brand kits."""
from __future__ import annotations

import asyncio
import base64
import json
import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

from . import brands, config, media, store
from .layout import layout_slide
from .remix import alternatives, remix
from .slide_schema import normalize, validate

router = APIRouter()


def _project(pid: str) -> dict:
    project = store.get_project(pid)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _idle(pid: str):
    if pid in store.RUNNING:
        raise HTTPException(409, "The AI is still working on this deck - wait for it to finish or press stop")


def _slide_index(project: dict, sid: str) -> int:
    idx = next((i for i, s in enumerate(project["slides"]) if s["id"] == sid), -1)
    if idx < 0:
        raise HTTPException(404, "Slide not found")
    return idx


# ---------------------------------------------------------------- media files

@router.get("/media/icon/{icon}/{color}.png")
async def icon_png(icon: str, color: str):
    path = await asyncio.to_thread(media.icon_file, icon, color)
    if not path:
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "max-age=604800"})


@router.get("/media/{kind}/{name}")
async def media_file(kind: str, name: str):
    path = media.local_path(f"/media/{kind}/{name}")
    if not path:
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "max-age=604800"})


@router.get("/brand-assets/{name}")
async def brand_asset(name: str):
    path = media.local_path(f"/brand-assets/{name}")
    if not path:
        raise HTTPException(404)
    return FileResponse(path)


@router.post("/api/media/upload")
async def upload_image(file: UploadFile = File(...)):
    data = await file.read()
    try:
        return await asyncio.to_thread(media.save_upload, data, file.filename or "image")
    except Exception:
        raise HTTPException(400, "That file isn't an image I can use")


@router.get("/api/media/photos")
async def photo_search(q: str):
    return {"results": await media.search_photos(q)}


class PhotoPick(BaseModel):
    url: str
    credit: str = ""
    source: str = ""


@router.post("/api/media/photos/fetch")
async def photo_fetch(body: PhotoPick):
    got = await media.fetch_photo(body.url, body.credit, body.source)
    if not got:
        raise HTTPException(502, "Couldn't download that photo - try another one")
    return got


@router.get("/api/media/icons")
async def icon_search(q: str):
    icon = await media.find_icon(q)
    return {"icon": icon}


# ---------------------------------------------------------------- manual editing

class SlideBody(BaseModel):
    spec: dict


@router.put("/api/projects/{pid}/slides/{sid}")
async def update_slide(pid: str, sid: str, body: SlideBody):
    _idle(pid)
    project = _project(pid)
    idx = _slide_index(project, sid)
    spec = normalize(body.spec)
    if spec["type"] == "template":
        spec["source"] = body.spec.get("source") or project["slides"][idx]["spec"].get("source")
    spec = await media.prepare(spec, store.deck_theme(project).get("dna"))
    store.snapshot(project, f"Before editing slide {idx + 1}")
    project["slides"][idx].update(spec=spec, status="done")
    store.save_project(project)
    return store.project_view(project)


@router.post("/api/projects/{pid}/slides/{sid}/move")
async def move_slide(pid: str, sid: str, body: dict):
    _idle(pid)
    project = _project(pid)
    idx = _slide_index(project, sid)
    to = max(0, min(len(project["slides"]) - 1, int(body.get("to", idx))))
    store.snapshot(project, f"Before moving slide {idx + 1}")
    project["slides"].insert(to, project["slides"].pop(idx))
    store.save_project(project)
    return store.project_view(project)


@router.post("/api/projects/{pid}/slides/add")
async def add_slide(pid: str, body: dict):
    _idle(pid)
    project = _project(pid)
    spec = normalize(body.get("spec") or {"type": "bullets", "title": "New slide", "bullets": ["Your first point"]})
    after = body.get("after")
    pos = next((i + 1 for i, s in enumerate(project["slides"]) if s["id"] == after), len(project["slides"]))
    store.snapshot(project, "Before adding a slide")
    project["slides"].insert(pos, {"id": store.new_slide_id(project), "spec": spec, "status": "done"})
    store.save_project(project)
    return store.project_view(project)


@router.get("/api/projects/{pid}/slides/{sid}/alternatives")
async def slide_alternatives(pid: str, sid: str):
    project = _project(pid)
    idx = _slide_index(project, sid)
    spec = project["slides"][idx]["spec"]
    theme = store.deck_theme(project)
    specs = [s["spec"] for s in project["slides"]]
    out = []
    for target in alternatives(spec):
        alt = normalize(remix(spec, target))
        out.append({"type": target, "layout": layout_slide(alt, theme, idx, specs, project.get("deck_title") or project["name"])})
    return {"alternatives": out}


@router.post("/api/projects/{pid}/slides/{sid}/remix")
async def remix_slide(pid: str, sid: str, body: dict):
    _idle(pid)
    project = _project(pid)
    idx = _slide_index(project, sid)
    new = remix(project["slides"][idx]["spec"], body.get("type"))
    if not new:
        raise HTTPException(400, "This slide has no alternative layouts")
    spec = await media.prepare(normalize(new), store.deck_theme(project).get("dna"))
    store.snapshot(project, f"Before changing the layout of slide {idx + 1}")
    project["slides"][idx]["spec"] = spec
    store.save_project(project)
    return store.project_view(project)


@router.post("/api/projects/{pid}/shuffle")
async def shuffle_design(pid: str):
    """New design DNA for this deck: different layouts, colors emphasis, icon family and decoration - same content."""
    from . import design
    _idle(pid)
    project = _project(pid)
    store.snapshot(project, "Before shuffling the design")
    project["design_seed"] = store._distinct_seed(project["theme_id"])
    dna = store.deck_theme(project)["dna"]
    specs = await asyncio.gather(*(media.prepare(s["spec"], dna) for s in project["slides"]), return_exceptions=True)
    for s, spec in zip(project["slides"], specs):
        if isinstance(spec, dict):
            s["spec"] = spec
    store.save_project(project)
    return store.project_view(project)


# ---------------------------------------------------------------- version history

@router.get("/api/projects/{pid}/history")
async def history(pid: str):
    project = _project(pid)
    return {"history": [{"i": i, "t": h["t"], "label": h["label"], "slides": len(h["state"]["slides"])}
                        for i, h in enumerate(project.get("history", []))][::-1]}


@router.post("/api/projects/{pid}/history/{i}/restore")
async def restore_version(pid: str, i: int):
    _idle(pid)
    project = _project(pid)
    if not store.restore(project, i):
        raise HTTPException(404, "Version not found")
    store.save_project(project)
    return store.project_view(project)


@router.post("/api/projects/{pid}/undo")
async def undo(pid: str):
    _idle(pid)
    project = _project(pid)
    hist = project.get("history", [])
    if not hist:
        raise HTTPException(400, "Nothing to undo")
    last = hist.pop()
    project.update(json.loads(json.dumps(last["state"])))
    store.save_project(project)
    return store.project_view(project)


# ---------------------------------------------------------------- deck settings

@router.patch("/api/projects/{pid}/settings")
async def deck_settings(pid: str, body: dict):
    project = _project(pid)
    settings = project.setdefault("settings", {})
    if body.get("transition") in ("none", "fade", "push", "zoom", "prezi"):
        settings["transition"] = body["transition"]
    if isinstance(body.get("builds"), bool):
        settings["builds"] = body["builds"]
    store.save_project(project)
    return {"settings": settings}


# ---------------------------------------------------------------- standalone web presentation

async def _player_html(project: dict, inline_images: bool) -> str:
    view = store.project_view(project)
    view["slides"] = [x for x in view["slides"] if x["status"] == "done"]
    if not view["slides"]:
        raise HTTPException(400, "No finished slides yet")
    data = json.dumps({"id": project["id"], "slides": view["slides"], "theme": view["theme"], "name": view["name"],
                       "settings": project.get("settings", {})}, ensure_ascii=False)
    if inline_images:
        cache: dict[str, str] = {}

        def inline(m):  # embed every image so the file works anywhere, offline
            src = m.group(1)
            if src not in cache:
                path = media.local_path(src)
                if path is None:
                    cache[src] = src
                else:
                    mime = {".png": "image/png", ".svg": "image/svg+xml", ".gif": "image/gif", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")
                    cache[src] = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
            return f'"{cache[src]}"'
        data = await asyncio.to_thread(lambda: re.sub(r'"(/(?:media|tpl-assets|brand-assets)/[^"]+)"', inline, data))
    js = (config.WEB_DIR / "slides.js").read_text(encoding="utf-8").replace("export function", "function").replace("export const", "const")
    player = (config.WEB_DIR / "player.html").read_text(encoding="utf-8")
    return player.replace("/*__SLIDES_JS__*/", js).replace('"__DECK_DATA__"', data.replace("</", "<\\/"))


@router.get("/present/{pid}")
async def present(pid: str):
    """Full-screen presentation (also presenter view with ?presenter=1 and printable PDF with ?print=1)."""
    return HTMLResponse(await _player_html(_project(pid), inline_images=False), headers={"Cache-Control": "no-cache"})


@router.get("/api/projects/{pid}/export.html")
async def export_html(pid: str):
    project = _project(pid)
    html = await _player_html(project, inline_images=True)
    safe = re.sub(r"[^\w\- ]+", "", project.get("deck_title") or project["name"]).strip() or "presentation"
    return Response(html, media_type="text/html", headers={"Content-Disposition": f'attachment; filename="{safe}.html"'})


# ---------------------------------------------------------------- brand kits

@router.get("/api/brands/fonts")
async def brand_fonts():
    return {"fonts": brands.FONTS}


@router.post("/api/brands")
async def create_brand(name: str = Form(""), primary: str = Form("#2563EB"), secondary: str = Form(""), mode: str = Form("light"),
                       heading: str = Form("Segoe UI"), body: str = Form("Segoe UI"), style: str = Form("bar"),
                       logo_url: str = Form(""), logo: UploadFile | None = File(default=None)):
    logo_bytes = await logo.read() if logo is not None else None
    form = {"name": name, "primary": primary, "secondary": secondary, "mode": mode, "heading": heading,
            "body": body, "style": style, "logo_url": logo_url}
    try:
        theme = await asyncio.to_thread(brands.save_brand, form, logo_bytes or None)
    except Exception as exc:
        raise HTTPException(400, f"Couldn't create the brand kit: {exc}")
    return {"theme_id": theme["id"]}


@router.delete("/api/brands/{bid}")
async def remove_brand(bid: str):
    brands.delete_brand(bid)
    return {"ok": True}


@router.post("/api/brands/import")
async def brand_import(body: dict):
    try:
        return await asyncio.to_thread(brands.import_from_website, str(body.get("url", "")))
    except Exception as exc:
        raise HTTPException(400, f"Couldn't read that website: {exc}")


# ---------------------------------------------------------------- open on phone

def lan_ips() -> list[str]:
    """This PC's IPv4 addresses, home/office network ranges first (192.168.x, 10.x, 172.16-31.x)."""
    import ipaddress
    import socket
    ips = set()
    try:
        ips.update(a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            ips.add(sock.getsockname()[0])
    except OSError:
        pass
    ips = [ip for ip in ips if not ip.startswith(("127.", "169.254."))]

    def rank(ip):
        a = ipaddress.ip_address(ip)
        return (0 if ip.startswith("192.168.") else 1 if ip.startswith("10.") else 2 if a.is_private else 3, ip)
    return sorted(ips, key=rank)


@router.get("/api/network")
async def network():
    import os
    lan = os.getenv("SLIDESMITH_LAN") == "1"
    port = os.getenv("PORT", "8000")
    urls = [f"http://{ip}:{port}" for ip in lan_ips()] if lan else []
    import ipaddress
    best = lan_ips()[0] if lan and lan_ips() else ""
    public = bool(best) and not ipaddress.ip_address(best).is_private
    return {"lan": lan, "url": urls[0] if urls else "", "others": urls[1:4], "public": public}


@router.get("/api/network/qr.png")
async def network_qr(url: str):
    import io
    import qrcode
    img = qrcode.make(url, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")
