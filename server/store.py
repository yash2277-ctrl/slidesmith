"""JSON-file persistence for projects and uploaded templates."""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

from . import config, design, themes
from .layout import layout_slide
from .template_analyzer import PROFILE_VERSION, analyze


RUNNING: dict = {}  # project id -> cancel event while the AI works on it


def _write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- templates

def template_dir(tid: str) -> Path:
    return config.TEMPLATES_DIR / tid


def list_templates() -> list[dict]:
    out = []
    for d in sorted(config.TEMPLATES_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        prof = d / "profile.json"
        if prof.exists():
            out.append(get_template(d.name))
    return out


def get_template(tid: str) -> dict | None:
    prof = template_dir(tid) / "profile.json"
    if not prof.exists():
        return None
    data = json.loads(prof.read_text(encoding="utf-8"))
    if data.get("version") != PROFILE_VERSION:
        data = _relearn(tid, data)
    return data


def _relearn(tid: str, old: dict) -> dict:
    """Re-analyze a template uploaded before the current analyzer version (e.g. to learn its sample pages)."""
    try:
        profile = analyze(template_dir(tid) / "template.pptx", tid, old.get("name", "Template"),
                          template_dir(tid) / "assets", f"/tpl-assets/{tid}")
        save_template(profile)
        return profile
    except Exception:
        return old


def save_template(profile: dict) -> None:
    _write(template_dir(profile["id"]) / "profile.json", profile)


def delete_template(tid: str) -> None:
    shutil.rmtree(template_dir(tid), ignore_errors=True)


def get_theme(theme_id: str) -> dict:
    """Theme ids: built-in ids ("midnight") or "tpl:<template id>"."""
    if theme_id and theme_id.startswith("tpl:"):
        prof = get_template(theme_id[4:])
        if prof:
            return prof
    if theme_id and not theme_id.startswith(("tpl:", "brand_")) and themes.get_builtin(theme_id) is None:
        prof = get_template(theme_id)
        if prof:
            return prof
    if theme_id and theme_id.startswith("brand_"):
        from .brands import get_brand
        brand = get_brand(theme_id)
        if brand:
            return brand
    return themes.get_builtin(theme_id) or themes.get_builtin(themes.DEFAULT_THEME_ID)


def deck_theme(project: dict) -> dict:
    """The project's theme plus its design DNA (what makes this deck look unlike any other)."""
    theme = get_theme(project["theme_id"])
    return {**theme, "dna": design.dna(design.seed_for(project))}


def template_file(theme: dict) -> Path | None:
    return template_dir(theme["id"]) / "template.pptx" if theme["kind"] == "custom" else None


# ---------------------------------------------------------------- projects

def _distinct_seed(theme_id: str) -> int:
    """Look at the designs of decks already made with this theme/template and pick one unlike all of them."""
    existing = []
    for f in config.PROJECTS_DIR.glob("*.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if p.get("theme_id") == theme_id:
            existing.append(design.dna(design.seed_for(p)))
    return design.distinct_seed(existing)


def new_project(name: str = "", theme_id: str = themes.DEFAULT_THEME_ID) -> dict:
    now = time.time()
    project = {
        "id": uuid.uuid4().hex[:12], "name": name or "Untitled presentation", "created": now, "updated": now,
        "theme_id": theme_id, "deck_title": "", "slides": [], "next_id": 1, "design_seed": _distinct_seed(theme_id),
        "messages": [], "chat": [],
    }
    save_project(project)
    return project


def project_path(pid: str) -> Path:
    return config.PROJECTS_DIR / f"{pid}.json"


def get_project(pid: str) -> dict | None:
    path = project_path(pid)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_project(project: dict) -> None:
    project["updated"] = time.time()
    _write(project_path(project["id"]), project)


def delete_project(pid: str) -> None:
    project_path(pid).unlink(missing_ok=True)


def list_projects() -> list[dict]:
    out = []
    for f in config.PROJECTS_DIR.glob("*.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cover = None
        if p.get("slides"):
            try:
                cover = layout_slide(p["slides"][0]["spec"], deck_theme(p), 0, [p["slides"][0]["spec"]], p["name"])
            except Exception:
                cover = None
        out.append({"id": p["id"], "name": p["name"], "updated": p["updated"], "theme_id": p["theme_id"],
                    "slide_count": len(p.get("slides", [])), "cover": cover})
    return sorted(out, key=lambda x: x["updated"], reverse=True)


HISTORY_LIMIT = 30


def snapshot(project: dict, label: str) -> None:
    """Remember the deck as it is now, so it can be restored (version history / undo)."""
    if not project.get("slides"):
        return
    hist = project.setdefault("history", [])
    state = {"slides": json.loads(json.dumps(project["slides"])), "deck_title": project.get("deck_title", ""),
             "theme_id": project["theme_id"], "name": project["name"], "design_seed": project.get("design_seed")}
    if hist and hist[-1]["state"] == state:
        return
    hist.append({"t": time.time(), "label": label[:80], "state": state})
    del hist[:-HISTORY_LIMIT]


def restore(project: dict, index: int) -> bool:
    hist = project.get("history", [])
    if not 0 <= index < len(hist):
        return False
    target = json.loads(json.dumps(hist[index]["state"]))
    snapshot(project, "Before restoring an earlier version")
    project.update(target)
    return True


def new_slide_id(project: dict) -> str:
    sid = f"s{project['next_id']}"
    project["next_id"] += 1
    return sid


def slide_view(project: dict, theme: dict, index: int) -> dict:
    s = project["slides"][index]
    specs = [x["spec"] for x in project["slides"]]
    return {**s, "index": index, "layout": layout_slide(s["spec"], theme, index, specs, project.get("deck_title") or project["name"])}


def clean_chat(chat: list[dict]) -> list[dict]:
    """Saved activities that were cut off show as interrupted, and raw server errors are explained."""
    from .ai_client import explain
    out = []
    for entry in chat:
        if entry.get("role") == "assistant":
            items = []
            for it in entry.get("items", []):
                if it.get("kind") == "activity":
                    it = dict(it)
                    if it.get("status") == "running":
                        it["status"] = "stopped"
                        it["label"] = (it.get("label") or "Step") + " (interrupted)"
                    if it.get("status") == "error":
                        it["label"] = explain(it.get("label", ""))
                items.append(it)
            entry = {**entry, "items": items}
        out.append(entry)
    return out


def project_view(project: dict) -> dict:
    theme = deck_theme(project)
    return {
        "id": project["id"], "name": project["name"], "theme_id": project["theme_id"], "settings": project.get("settings", {}),
        "can_undo": bool(project.get("history")),
        "deck_title": project.get("deck_title", ""), "chat": clean_chat(project.get("chat", [])),
        "slides": [slide_view(project, theme, i) for i in range(len(project["slides"]))],
        "theme": theme_public(theme),
    }


def theme_public(theme: dict) -> dict:
    """What the browser needs to draw a theme/template (backgrounds, decor, fonts)."""
    keep = ("id", "name", "kind", "slide_w", "slide_h", "dark", "fonts", "colors", "mapping", "scheme", "existing_slides", "brand", "base_slide", "logo")
    out = {k: theme[k] for k in keep if k in theme}
    if theme["kind"] == "custom":
        out["layouts"] = [{k: l[k] for k in ("key", "name", "background", "bg_color", "dark", "decor", "placeholders")}
                          for l in theme["layouts"]]
        out["pages"] = [{"id": t["id"], "role": t["role"], "layout": layout_slide({"type": "template", "source": t["id"]}, theme, 0, [], "")}
                        for t in theme.get("slides", [])]
    return out
