"""FastAPI app: REST endpoints + the streaming chat endpoint."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, ai_client, brands, config, features, media, store, themes
from .extract import extract_pages, extract_text
from .layout import layout_slide
from .renderer import build_pptx
from .template_analyzer import analyze

app = FastAPI(title="SlideSmith")
RUNNING = store.RUNNING
app.include_router(features.router)

SAMPLE_TITLE = {"type": "title", "kicker": "Preview", "title": "Your presentation title", "subtitle": "Subtitle goes here"}
SAMPLE_CONTENT = {"type": "cards", "title": "Three key ideas", "cards": [
    {"heading": "Clarity", "text": "One idea per slide."}, {"heading": "Contrast", "text": "Make the point pop."},
    {"heading": "Story", "text": "Lead to a decision."}]}


def _project_or_404(pid: str) -> dict:
    project = store.get_project(pid)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _read_attachments(files: list[UploadFile]) -> list[dict]:
    """Each upload becomes a source: its text for the AI to read, plus its pages
    rendered as images so the document can be shown on a slide as itself."""
    out = []
    for f in files:
        try:
            data = f.read()
        except Exception:
            continue
        name = f.filename or "file.txt"
        try:
            text = extract_text(name, data)
        except Exception:
            text = ""
        pages = []
        try:
            tag = hashlib.sha1(data).hexdigest()[:12]
            for num, png in extract_pages(name, data):
                saved = media.save_page(png, tag, num)
                if saved:
                    pages.append(saved)
        except Exception:
            pages = []
        if not text and not pages:
            continue  # nothing readable and nothing showable
        out.append({"name": name, "text": text, "pages": pages})
    return out


def _theme_card(theme: dict) -> dict:
    card = store.theme_public(theme)
    card["theme_id"] = theme["id"] if theme["kind"] == "builtin" else f"tpl:{theme['id']}"
    if theme.get("brand") is True:  # brand kits; templates also have "brand" (a list of colors)
        card["theme_id"] = theme["id"]
    pages = [t for t in theme.get("slides", []) if t["role"] != "guide"]
    if pages:  # show the user's real pages: the cover and the content page
        second = next((t for t in pages if t["id"] == theme.get("base_slide")), pages[min(1, len(pages) - 1)])
        card["previews"] = [layout_slide({"type": "template", "source": t["id"]}, theme, 0, [], "") for t in (pages[0], second)]
    else:
        card["previews"] = [layout_slide(SAMPLE_TITLE, theme, 0, [SAMPLE_TITLE], "Preview"),
                            layout_slide(SAMPLE_CONTENT, theme, 1, [SAMPLE_TITLE, SAMPLE_CONTENT], "Preview")]
    return card


# ---------------------------------------------------------------- status & settings

@app.get("/api/status")
async def status():
    return {"demo": config.demo_mode(), "base_url": config.base_url(), "model": config.model(),
            "has_key": bool(config.api_key())}


class Settings(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    review: bool | None = None
    review_model: str | None = None


@app.get("/api/settings")
async def get_settings():
    key = config.api_key()
    return {"base_url": config.base_url(), "model": config.model(), "review": config.review_enabled(),
            "review_model": config.review_model(),
            "api_key_hint": (key[:5] + "…" + key[-4:]) if len(key) > 10 else ("set" if key else "")}


@app.post("/api/settings")
async def post_settings(s: Settings):
    config.save_settings({"AI_BASE_URL": s.base_url, "AI_API_KEY": s.api_key or None, "AI_MODEL": s.model,
                          "AI_REVIEW": None if s.review is None else ("1" if s.review else "0"),
                          "AI_REVIEW_MODEL": s.review_model})
    ai_client._model_cache.clear()
    return await status()


@app.get("/api/models")
async def models():
    try:
        return {"models": await asyncio.wait_for(ai_client.list_models(), 15)}
    except Exception as exc:
        return JSONResponse({"models": [], "error": ai_client.friendly_error(exc)}, status_code=200)


# ---------------------------------------------------------------- themes & templates

@app.get("/api/themes")
async def list_themes():
    out = [_theme_card(themes.get_builtin(t["id"])) for t in themes.BUILTIN_THEMES]
    out += [{**_theme_card(b), "theme_id": b["id"]} for b in brands.list_brands()]
    out += [_theme_card(t) for t in store.list_templates()]
    return {"themes": out}


@app.post("/api/templates")
async def upload_template(file: UploadFile = File(...)):
    name = file.filename or "template.pptx"
    if not re.search(r"\.(pptx|potx)$", name, re.I):
        raise HTTPException(400, "Please upload a .pptx or .potx file")
    tid = uuid.uuid4().hex[:10]
    folder = store.template_dir(tid)
    folder.mkdir(parents=True)
    path = folder / "template.pptx"
    path.write_bytes(await file.read())
    try:
        profile = await asyncio.to_thread(analyze, path, tid, re.sub(r"\.(pptx|potx)$", "", name, flags=re.I),
                                          folder / "assets", f"/tpl-assets/{tid}")
    except Exception as exc:
        store.delete_template(tid)
        raise HTTPException(400, f"Couldn't read this template: {exc}")
    store.save_template(profile)
    return _theme_card(profile)


@app.delete("/api/templates/{tid}")
async def delete_template(tid: str):
    store.delete_template(tid)
    return {"ok": True}


@app.get("/tpl-assets/{tid}/{name}")
async def template_asset(tid: str, name: str):
    path = (store.template_dir(tid) / "assets" / name).resolve()
    if not path.is_file() or store.template_dir(tid).resolve() not in path.parents:
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "max-age=86400"})


# ---------------------------------------------------------------- projects

class NewProject(BaseModel):
    name: str = ""
    theme_id: str = themes.DEFAULT_THEME_ID


class PatchProject(BaseModel):
    name: str | None = None
    theme_id: str | None = None


@app.get("/api/projects")
async def projects():
    return {"projects": store.list_projects()}


@app.post("/api/projects")
async def create_project(body: NewProject):
    return store.project_view(store.new_project(body.name, body.theme_id))


@app.get("/api/projects/{pid}")
async def get_project(pid: str):
    return store.project_view(_project_or_404(pid))


@app.patch("/api/projects/{pid}")
async def patch_project(pid: str, body: PatchProject):
    project = _project_or_404(pid)
    if body.name is not None:
        project["name"] = body.name.strip() or project["name"]
    if body.theme_id is not None:
        project["theme_id"] = body.theme_id
    store.save_project(project)
    return store.project_view(project)


@app.delete("/api/projects/{pid}")
async def delete_project(pid: str):
    store.delete_project(pid)
    return {"ok": True}


class SlideOps(BaseModel):
    delete: list[str] = []
    order: list[str] | None = None
    duplicate: str | None = None


@app.post("/api/projects/{pid}/slides")
async def slide_ops(pid: str, ops: SlideOps):
    project = _project_or_404(pid)
    if pid in RUNNING:
        raise HTTPException(409, "The AI is still working on this deck")
    project["slides"] = [s for s in project["slides"] if s["id"] not in set(ops.delete)]
    if ops.order:
        by_id = {s["id"]: s for s in project["slides"]}
        ordered = [by_id[i] for i in ops.order if i in by_id]
        project["slides"] = ordered + [s for s in project["slides"] if s["id"] not in ops.order]
    if ops.duplicate:
        idx = next((i for i, s in enumerate(project["slides"]) if s["id"] == ops.duplicate), -1)
        if idx >= 0:
            copy = json.loads(json.dumps(project["slides"][idx]))
            copy["id"] = store.new_slide_id(project)
            project["slides"].insert(idx + 1, copy)
    store.save_project(project)
    return store.project_view(project)


@app.get("/api/projects/{pid}/slides/{sid}.png")
async def slide_png(pid: str, sid: str):
    """The slide exactly as the AI reviewer sees it (handy for any external tool, too)."""
    from fastapi.responses import Response
    from .raster import inspect
    project = _project_or_404(pid)
    idx = next((i for i, s in enumerate(project["slides"]) if s["id"] == sid), -1)
    if idx < 0:
        raise HTTPException(404, "Slide not found")
    theme = store.deck_theme(project)
    view = store.slide_view(project, theme, idx)
    png, issues = await asyncio.to_thread(inspect, view["layout"], view["spec"], theme)
    return Response(png, media_type="image/png", headers={"X-Slide-Checks": json.dumps(issues)[:4000], "Cache-Control": "no-cache"})


@app.get("/api/projects/{pid}/export")
async def export(pid: str):
    project = _project_or_404(pid)
    slides = [s for s in project["slides"] if s["status"] == "done"]
    if not slides:
        raise HTTPException(400, "No finished slides to export yet")
    theme = store.deck_theme(project)
    out = config.DATA_DIR / "exports"
    out.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w\- ]+", "", project.get("deck_title") or project["name"]).strip() or "presentation"
    path = out / f"{project['id']}.pptx"
    await asyncio.to_thread(build_pptx, slides, theme, project.get("deck_title") or project["name"], path, store.template_file(theme),
                            project.get("settings", {}).get("transition", "none"))
    return FileResponse(path, filename=f"{safe}.pptx",
                        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


@app.post("/api/projects/{pid}/stop")
async def stop(pid: str):
    if pid in RUNNING:
        RUNNING[pid].set()
    return {"ok": True}


@app.post("/api/projects/{pid}/chat")
async def chat(pid: str, text: str = Form(""), selected: str = Form("[]"), files: list[UploadFile] = File(default=[])):
    project = _project_or_404(pid)
    if pid in RUNNING:
        raise HTTPException(409, "Already generating — wait or press stop")
    try:
        sel = [s for s in json.loads(selected) if isinstance(s, str)]
    except json.JSONDecodeError:
        sel = []
    attachments = await asyncio.to_thread(_read_attachments, files)

    queue: asyncio.Queue = asyncio.Queue()
    cancel = asyncio.Event()
    RUNNING[pid] = cancel

    async def emit(event: dict):
        await queue.put(event)

    async def runner():
        try:
            await agent.run_turn(project, text, sel, attachments, emit, cancel)
        except Exception as exc:
            await queue.put({"type": "error", "message": f"Internal error: {exc}"})
            await queue.put({"type": "done", "project": store.project_view(project)})
        finally:
            RUNNING.pop(pid, None)

    task = asyncio.create_task(runner())

    async def events():
        try:
            yield "retry: 100000\n\n"
            while True:
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    yield f"data: {json.dumps(getter.result(), ensure_ascii=False)}\n\n"
                    continue
                getter.cancel()
                while not queue.empty():
                    yield f"data: {json.dumps(queue.get_nowait(), ensure_ascii=False)}\n\n"
                break
        finally:
            if not task.done():
                cancel.set()

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- web app

@app.get("/")
async def index():
    return FileResponse(config.WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.middleware("http")
async def no_cache_web(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/web/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/web", StaticFiles(directory=config.WEB_DIR), name="web")
