"""One chat turn, Stitch-style:
  1. planner  - outlines a new deck (or performs direct edits), streamed live
  2. writer   - writes every planned slide in its own detailed pass
  3. reviewer - renders the slide to an image, looks at it with the automatic checks, and fixes it if needed
Every step is streamed to the browser as activities and live slide updates."""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from typing import Awaitable, Callable

import openai

from . import ai_client, config, design, media, store, themes
from .layout import layout_slide, template_slide, template_title
from .prompts import PLANNER_PROMPT, REVIEWER_PROMPT, WRITER_PROMPT
from .protocol import StreamParser, complete_json, parse_partial_json
from .raster import inspect
from .slide_schema import normalize, validate

Emit = Callable[[dict], Awaitable[None]]
HISTORY_MESSAGES = 6
TRANSIENT = (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError, openai.RateLimitError)


def is_transient(exc: Exception) -> bool:
    # a bare APIError is an error event sent mid-stream by the server (e.g. a 502 from its backend)
    if isinstance(exc, TRANSIENT) or type(exc) is openai.APIError:
        return True
    # the HTTP layer can raise its own errors when a stream is cut off (e.g. ReadError)
    return type(exc).__module__.startswith(("httpx", "httpcore")) or type(exc).__name__ in ("ReadError", "RemoteProtocolError", "ReadTimeout")
SOURCE_CHARS = 40000
PLACEHOLDER_RE = re.compile(r"<[^>]+>|x{4,}", re.I)
ROLE_LABEL = {"cover": "cover page", "toc": "contents page", "content": "content page", "closing": "closing page",
              "section": "section page", "other": "page", "guide": "instructions"}


# ---------------------------------------------------------------- context builders

def _capacity(field: dict) -> str:
    lines = [l for l in field["lines"] if l["text"].strip()]
    if field["role"] != "body" or not lines:
        return ""
    size = sorted(l["size"] for l in lines)[len(lines) // 2]
    rows = int(field["h"] / (size * 1.25 / 72))
    chars = int(field["w"] / (size / 72 * 0.5))
    return f", fits about {rows} lines of {chars} characters at {size:g}pt"


def describe_pages(theme: dict) -> str:
    if theme["kind"] != "custom" or not theme.get("slides"):
        return ""
    out = [f'Template pages from the user\'s file "{theme["name"]}" - reuse them with type "template":']
    for ts in theme["slides"][:25]:
        if ts["role"] == "guide":
            out.append(f'{ts["id"]} [INSTRUCTIONS written by the template author - follow them; never output this page]:\n    {ts["text"][:1500]}')
            continue
        pics = sum(1 for e in ts["elements"] if e["t"] == "decor" and e["d"].get("kind") == "image")
        extra = " - also the frame that generated visual slides are drawn in" if ts["id"] == theme.get("base_slide") else ""
        out.append(f'{ts["id"]} [{ROLE_LABEL.get(ts["role"], "page")}]{f" ({pics} pictures/logos)" if pics else ""}{extra}')
        for f in ts["fields"]:
            if f["kind"] == "table":
                rows = "; ".join(f"r{r}: " + " | ".join(f'"{c}"' for c in row) for r, row in enumerate(f["rows"]))
                out.append(f'    {f["key"]} table - cells are {f["key"]}.rRcC: {rows}')
                continue
            filled = [l for l in f["lines"] if l["text"].strip()]
            if not filled and f["role"] not in ("title", "body"):
                continue
            desc = " / ".join(f'p{l["p"]} [L{l["level"]} {l["size"]:g}pt{" bold" if l["bold"] else ""}] "{l["text"].strip()[:90]}"' for l in filled[:16])
            out.append(f'    {f["key"]} {f["role"] or "text"} box {f["w"]}x{f["h"]}in{_capacity(f)}: {desc or "(empty)"}')
    return "\n".join(out)


def _deck_listing(project: dict, full: bool = True) -> list[str]:
    lines = []
    if not project["slides"]:
        return ["(none)"]
    for s in project["slides"]:
        spec = s["spec"]
        if s["status"] != "done":
            lines.append(f'{s["id"]}: [not written yet] {json.dumps({k: spec.get(k) for k in ("type", "source", "title") if spec.get(k)}, ensure_ascii=False)}'
                         + (f' brief: {s["brief"]}' if s.get("brief") else ""))
        elif full:
            lines.append(f'{s["id"]}: {json.dumps(spec, ensure_ascii=False)}')
        else:
            lines.append(f'{s["id"]}: ({spec["type"]}) "{spec.get("title", "")}"')
    return lines


def _sources(project: dict, budget: int = SOURCE_CHARS) -> list[str]:
    out = []
    for src in project.get("sources", []):
        chunk = src["text"][:budget]
        budget -= len(chunk)
        out.append(f'--- {src["name"]} ---\n{chunk}')
        if budget <= 0:
            break
    return (["Source documents provided by the user:"] + out) if out else []


def _documents(project: dict) -> list[str]:
    """The attachment pages that can be placed on a slide, as a copyable manifest.

    A PDF the user attached is only useful if the AI can actually put it on a slide:
    this is the list it picks from, e.g. {"type":"document","doc":"#D1","pages":[1]}."""
    lines = []
    for src in project.get("sources", []):
        pages = src.get("pages") or []
        if not pages:
            continue
        nums = ", ".join(str(p["page"]) for p in pages)
        lines.append(f'  {src["doc_id"]} = "{src["name"]}" - pages {nums} (the page images are already uploaded)')
    return (["Attached documents you can SHOW on a slide (use type \"document\"):"] + lines) if lines else []


def _workspace(project: dict, theme: dict, selected: list[str]) -> str:
    lines = ["[workspace]"]
    if theme["kind"] == "custom":
        lines.append(f'Design: the user\'s own template "{theme["name"]}".')
        pages = describe_pages(theme)
        if pages:
            lines.append(pages)
    else:
        lines.append(f'Design: built-in theme "{theme["id"]}" ({theme["name"]}).')
    if theme.get("dna"):
        lines.append(design.direction(theme["dna"]))
    lines.append(f'Deck title: {project.get("deck_title") or "(none yet)"}')
    lines.append("Slides (in order):")
    lines.extend(_deck_listing(project))
    sel = [sid for sid in selected if any(s["id"] == sid for s in project["slides"])]
    if sel:
        lines.append(f"Selected slides: {', '.join(sel)} - apply the request to these.")
    lines.extend(_documents(project))
    lines.extend(_sources(project))
    lines.append("[/workspace]")
    return "\n".join(lines)


def _compact_assistant(text: str) -> str:
    text = re.sub(r"(<slide[^>]*>).*?(</slide>)", r"\1…\2", text, flags=re.S)
    return re.sub(r"(<plan[^>]*>).*?(</plan>)", r"\1…\2", text, flags=re.S)


COVER_WORDS = re.compile(r"\b(cover|first\s*(page|slide)|frist\s*(page|slide)|1st\s*(page|slide)|front\s*page|title\s*(page|slide)|"
                         r"pehla|pahla|starting\s*page)\b", re.I)


def guard_cover(spec: dict, theme: dict, allow_all: bool = False) -> dict:
    """The template's cover page stays the same: only <placeholder> fields may change -
    unless the user explicitly asked to change the cover (then their request is followed)."""
    ts = template_slide(theme, spec.get("source"))
    if not ts or ts["role"] != "cover" or allow_all:
        return spec
    fields = {f["key"]: f for f in ts["fields"]}
    clean = {}
    for key, value in (spec.get("fill") or {}).items():
        base, _, sub = key.partition(".")
        f = fields.get(base)
        original = None
        if f and f["kind"] == "text" and sub.startswith("p") and sub[1:].isdigit():
            original = next((l["text"] for l in f["lines"] if l["p"] == int(sub[1:])), None)
        elif f and f["kind"] == "table" and sub.startswith("r") and "c" in sub:
            try:
                r, c = (int(x) for x in sub[1:].split("c"))
                original = f["rows"][r][c]
            except (ValueError, IndexError):
                original = None
        if original is not None and PLACEHOLDER_RE.search(original):
            clean[key] = value
    return {**spec, "fill": clean}


# ---------------------------------------------------------------- the turn

class Turn:
    def __init__(self, project: dict, emit: Emit, cancel: asyncio.Event):
        self.p = project
        self.emit = emit
        self.cancel = cancel
        self.theme = store.deck_theme(project)
        self.plan_queue: list[str] = []
        self.plan_ids: list[str] = []
        self.cur: dict | None = None
        self.step_id: str | None = None
        self.think_id: str | None = None
        self.text_item: str | None = None
        self.n = 0
        self.items: list[dict] = []
        self.last_emit = 0.0
        self.quiet = False            # writer/reviewer phases: no separate "thinking" rows
        self.review_aid: str | None = None
        self.review_note = ""
        self.review_ok = False
        self.touched: list[str] = []  # slides written or changed in this turn
        self.improved = 0
        self.request = ""
        self.vision_failed = False
        self.cover_ok = False  # the user asked to change the cover page this turn

    # ---------------------------------------------------------------- helpers
    def uid(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{int(time.time() * 1000) % 10_000_000}_{self.n}"

    def index_of(self, sid: str) -> int:
        return next((i for i, s in enumerate(self.p["slides"]) if s["id"] == sid), -1)

    def finish_spec(self, spec: dict) -> dict:
        if spec.get("type") == "template":
            spec = guard_cover(spec, self.theme, allow_all=self.cover_ok and not self.review_aid)
            ts = template_slide(self.theme, spec.get("source"))
            fill = spec.setdefault("fill", {})
            if ts and ts["title_key"] and ts["role"] not in ("cover", "closing"):
                title = fill.get(ts["title_key"]) or fill.get(ts["title_key"] + ".p0")
                title = title if isinstance(title, str) else (spec.get("title") or "")
                if title and not any(k.split(".")[0] == ts["title_key"] for k in fill):
                    fill[ts["title_key"]] = title  # never leave the template's title bar empty
                body = ts["body_key"]
                same = lambda v: isinstance(v, str) and v.strip().strip("\t").casefold() == title.strip().casefold()
                if title and body and isinstance(fill.get(body), list) and fill[body]:
                    first = fill[body][0]
                    if same(first if isinstance(first, str) else first.get("text")):
                        fill[body] = fill[body][1:]  # don't repeat the title as the first body line
                if title and body and same(fill.get(body + ".p0")):
                    fill[body + ".p0"] = ""
            spec["title"] = template_title(spec, self.theme)
        return spec

    async def slide_event(self, sid: str):
        i = self.index_of(sid)
        if i >= 0:
            await self.emit({"type": "slide", "slide": store.slide_view(self.p, self.theme, i)})

    async def order_event(self):
        await self.emit({"type": "order", "order": [s["id"] for s in self.p["slides"]],
                         "deck_title": self.p.get("deck_title", ""), "name": self.p["name"]})

    async def activity(self, aid: str, kind: str, label: str, status: str, **extra):
        item = next((it for it in self.items if it.get("id") == aid), None)
        if item is None:
            item = {"kind": "activity", "id": aid}
            self.items.append(item)
            self.text_item = None
        item.update(type=kind, label=label, status=status, **extra)
        await self.emit({"type": "activity", "item": item})

    async def say(self, delta: str):
        if not delta:
            return
        if self.review_aid:
            self.review_note += delta
            return
        if self.text_item is None:
            if not delta.strip():
                return
            self.text_item = self.uid("t")
            self.items.append({"kind": "text", "id": self.text_item, "text": ""})
            delta = delta.lstrip()
        item = next(it for it in self.items if it.get("id") == self.text_item)
        item["text"] += delta
        await self.emit({"type": "text", "id": self.text_item, "delta": delta})

    async def end_step(self):
        if self.step_id:
            item = next(it for it in self.items if it.get("id") == self.step_id)
            await self.activity(self.step_id, "step", item["label"].strip(), "done")
            self.step_id = None

    async def end_think(self):
        if self.think_id:
            item = next(it for it in self.items if it.get("id") == self.think_id)
            await self.activity(self.think_id, "think", "Thought it through", "done", detail=item.get("detail", ""))
            self.think_id = None

    async def think(self, delta: str):
        if self.quiet:
            return
        if not self.think_id:
            self.think_id = self.uid("a")
            await self.activity(self.think_id, "think", "Thinking", "running", detail="")
        item = next(it for it in self.items if it.get("id") == self.think_id)
        item["detail"] = (item.get("detail", "") + delta)[-4000:]
        if time.monotonic() - self.last_emit > 0.25:
            self.last_emit = time.monotonic()
            await self.emit({"type": "activity", "item": item})

    # ---------------------------------------------------------------- protocol handlers
    async def on_event(self, kind: str, tag: str, attrs: dict, content: str):
        if tag != "think" and self.think_id and kind in ("open", "selfclose"):
            await self.end_think()
        if kind == "text_delta":
            if tag == "say":
                await self.say(content)
            elif tag == "step" and self.step_id and not self.quiet:
                item = next(it for it in self.items if it.get("id") == self.step_id)
                item["label"] += content
                await self.emit({"type": "activity", "item": item})
            elif tag == "think":
                await self.think(content)
            return
        if kind == "open":
            if tag == "say":
                self.text_item = None
            elif tag == "step" and not self.quiet:
                await self.end_step()
                self.step_id = self.uid("a")
                await self.activity(self.step_id, "step", "", "running")
            elif tag == "plan":
                await self.open_plan(attrs)
            elif tag == "slide":
                await self.open_slide(attrs)
            return
        if kind == "partial":
            if tag == "plan":
                await self.partial_plan(content)
            elif tag == "slide" and self.cur and time.monotonic() - self.cur["t"] > 0.09:
                self.cur["t"] = time.monotonic()
                await self.partial_slide(content)
            return
        if kind == "close":
            if tag == "plan":
                await self.close_plan(attrs, content)
            elif tag == "slide":
                await self.close_slide(content)
            elif tag == "say":
                self.text_item = None
            return
        if kind == "selfclose":
            if tag == "ok":
                self.review_ok = True
            else:
                await self.command(tag, attrs)

    async def open_plan(self, attrs):
        await self.end_step()
        if self.p["slides"]:
            self.p["slides"] = []
            await self.order_event()
        if attrs.get("title"):
            self.p["deck_title"] = attrs["title"]
            if self.p["name"] in ("", "Untitled presentation"):
                self.p["name"] = attrs["title"]
        self.plan_ids = []
        self.plan_aid = self.uid("a")
        await self.activity(self.plan_aid, "plan", "Planning the outline", "running")

    def _plan_spec(self, raw: dict) -> dict:
        spec = normalize({k: raw.get(k) for k in ("type", "title", "source")})
        if spec["type"] == "template":
            ts = template_slide(self.theme, spec.get("source"))
            if ts and ts["title_key"] and ts["role"] not in ("cover", "closing") and raw.get("title"):
                spec["fill"] = {ts["title_key"]: raw["title"]}
            spec["title"] = raw.get("title") or template_title(spec, self.theme)
        return spec

    async def partial_plan(self, content: str, final=False):
        items = parse_partial_json(content)
        if not isinstance(items, list):
            return
        changed_order = False
        for i, raw in enumerate(items):
            if not isinstance(raw, dict) or (not final and i == len(items) - 1 and "title" not in raw):
                continue
            spec = self._plan_spec(raw)
            brief = str(raw.get("brief") or "")[:600]
            if i >= len(self.plan_ids):
                sid = store.new_slide_id(self.p)
                self.plan_ids.append(sid)
                self.plan_queue.append(sid)
                self.p["slides"].append({"id": sid, "spec": spec, "status": "planned", "brief": brief})
                changed_order = True
                await self.slide_event(sid)
            else:
                j = self.index_of(self.plan_ids[i])
                if j >= 0 and self.p["slides"][j]["status"] == "planned" and (self.p["slides"][j]["spec"] != spec or self.p["slides"][j].get("brief") != brief):
                    self.p["slides"][j].update(spec=spec, brief=brief)
                    await self.slide_event(self.plan_ids[i])
        if changed_order:
            await self.order_event()

    async def close_plan(self, attrs, content):
        await self.partial_plan(content, final=True)
        cover = next((ts for ts in self.theme.get("slides", []) if ts["role"] == "cover"), None) if self.theme["kind"] == "custom" else None
        first = self.p["slides"][0]["spec"] if self.p["slides"] else {}
        if cover and not (first.get("type") == "template" and first.get("source") == cover["id"]):
            sid = store.new_slide_id(self.p)  # the template's cover page always opens the deck
            self.p["slides"].insert(0, {"id": sid, "spec": {"type": "template", "source": cover["id"], "title": "Cover"},
                                        "status": "planned", "brief": "The template's cover page, kept as it is."})
            self.plan_ids.insert(0, sid)
            self.plan_queue.insert(0, sid)
            await self.slide_event(sid)
        await self.activity(self.plan_aid, "plan", f"Planned {len(self.plan_ids)} slides", "done")
        await self.order_event()

    async def open_slide(self, attrs):
        ref, after = attrs.get("ref"), attrs.get("after")
        if ref and self.index_of(ref) >= 0:
            sid, mode = ref, "replace"
            if sid in self.plan_queue:
                self.plan_queue.remove(sid)
                mode = "fill"
        elif self.plan_queue and not after:
            sid, mode = self.plan_queue.pop(0), "fill"
        else:
            sid, mode = store.new_slide_id(self.p), "insert"
            pos = len(self.p["slides"])
            if after == "start":
                pos = 0
            elif after and self.index_of(after) >= 0:
                pos = self.index_of(after) + 1
            self.p["slides"].insert(pos, {"id": sid, "spec": {"type": "bullets", "title": ""}, "status": "generating"})
            await self.order_event()
        i = self.index_of(sid)
        slide = self.p["slides"][i]
        verb = {"replace": "Updating", "fill": "Designing", "insert": "Adding"}[mode]
        aid = self.review_aid or self.uid("a")
        if self.review_aid:
            verb = "Improving"
        self.cur = {"id": sid, "mode": mode, "orig": json.loads(json.dumps(slide["spec"])), "orig_status": slide["status"],
                    "aid": aid, "t": 0.0, "verb": verb}
        slide["status"] = "generating"
        await self.activity(aid, "slide", f"{verb} slide {i + 1}", "running", slide_id=sid)
        await self.slide_event(sid)

    async def partial_slide(self, content):
        raw = parse_partial_json(content)
        if not isinstance(raw, dict) or "type" not in raw:
            return
        i = self.index_of(self.cur["id"])
        if i < 0:
            return
        spec = normalize(raw)
        if spec["type"] == "template":
            spec["title"] = template_title(spec, self.theme)
        self.p["slides"][i]["spec"] = spec
        title = spec.get("title") or spec.get("quote", "")[:40]
        await self.activity(self.cur["aid"], "slide", f'{self.cur["verb"]} slide {i + 1}' + (f" · {title}" if title else ""), "running", slide_id=self.cur["id"])
        await self.slide_event(self.cur["id"])

    async def close_slide(self, content):
        if not self.cur:
            return
        sid = self.cur["id"]
        i = self.index_of(sid)
        try:
            raw = json.loads(content.strip().strip("`"))
        except json.JSONDecodeError:
            raw = complete_json(content)  # a reply that was cut off mid-JSON is rejected, never saved half-written
        spec = normalize(raw) if isinstance(raw, dict) else None
        err = validate(spec) if spec else "the reply was cut off or not valid JSON"
        if spec and not err and spec["type"] == "template" and not template_slide(self.theme, spec.get("source")):
            err = f"Template page {spec.get('source')} does not exist."
        if i >= 0:
            slide = self.p["slides"][i]
            if spec and not err:
                spec = self.finish_spec(spec)
                try:
                    spec = await asyncio.wait_for(media.prepare(spec, self.theme.get("dna")), 40)
                except Exception:
                    pass  # media is optional: the slide still works without icons/photos
                spec = media.resolve_document(spec, self.p.get("sources", []))
                slide["spec"], slide["status"] = spec, "done"
                if sid not in self.touched:
                    self.touched.append(sid)
                title = slide["spec"].get("title") or slide["spec"].get("quote", "")[:40]
                if not self.review_aid:
                    verb = "Updated" if self.cur["mode"] == "replace" else "Designed"
                    await self.activity(self.cur["aid"], "slide", f"{verb} slide {i + 1} · {title}", "done", slide_id=sid)
            elif self.cur["mode"] == "insert":
                self.p["slides"].pop(i)
                await self.order_event()
                await self.activity(self.cur["aid"], "slide", "Skipped a slide that came back malformed", "error")
            else:
                slide["spec"], slide["status"] = self.cur["orig"], self.cur["orig_status"]
                if not self.review_aid:
                    await self.activity(self.cur["aid"], "slide", f"Couldn't write slide {i + 1} ({err})", "error", slide_id=sid)
            if i < len(self.p["slides"]) and self.p["slides"][i]["id"] == sid:
                await self.slide_event(sid)
        self.cur = None

    async def command(self, tag, attrs):
        ref = attrs.get("ref")
        if tag == "delete" and ref and self.index_of(ref) >= 0:
            i = self.index_of(ref)
            title = self.p["slides"][i]["spec"].get("title", "")
            self.p["slides"].pop(i)
            if ref in self.plan_queue:
                self.plan_queue.remove(ref)
            await self.order_event()
            await self.activity(self.uid("a"), "delete", f"Removed slide {i + 1} · {title}", "done")
        elif tag == "move" and ref and self.index_of(ref) >= 0:
            slide = self.p["slides"].pop(self.index_of(ref))
            after = attrs.get("after")
            pos = 0 if after == "start" else (self.index_of(after) + 1 if after and self.index_of(after) >= 0 else len(self.p["slides"]))
            self.p["slides"].insert(pos, slide)
            await self.order_event()
            await self.activity(self.uid("a"), "move", f"Moved “{slide['spec'].get('title', '')}” to position {pos + 1}", "done")
        elif tag == "theme":
            tid = attrs.get("id", "")
            if themes.get_builtin(tid) and not self.p["theme_id"].startswith("tpl:"):
                self.p["theme_id"] = tid
                self.theme = store.deck_theme(self.p)
                await self.activity(self.uid("a"), "theme", f"Switched theme to {self.theme['name']}", "done")
                await self.emit({"type": "project", "project": store.project_view(self.p)})

    # ---------------------------------------------------------------- streaming one model call
    async def stream_call(self, messages: list[dict], model: str | None = None, stop: list[str] | None = None) -> str:
        try:
            return await self._stream_call(messages, model, stop)
        except Exception:
            if self.cur:  # connection dropped mid-slide: put the slide back as it was
                i = self.index_of(self.cur["id"])
                if i >= 0:
                    self.p["slides"][i].update(spec=self.cur["orig"], status=self.cur["orig_status"])
                    await self.slide_event(self.cur["id"])
                self.cur = None
            raise

    async def retrying(self, fn, *args, attempts: int = 3):
        """Retry a model call on transient network/server errors with a short backoff."""
        for attempt in range(attempts):
            try:
                return await fn(*args)
            except Exception as exc:
                if not is_transient(exc) or attempt == attempts - 1 or self.cancel.is_set():
                    raise
                aid = self.uid("a")
                await self.activity(aid, "retry", f"Endpoint hiccup — retrying ({attempt + 2}/{attempts})", "running")
                await asyncio.sleep(4 * (attempt + 1))
                await self.activity(aid, "retry", "Endpoint hiccup — retried", "done")

    async def _stream_call(self, messages: list[dict], model: str | None = None, stop: list[str] | None = None) -> str:
        parser = StreamParser()
        raw_out = []
        async for kind, chunk in ai_client.stream_chat(messages, model=model, stop=stop):
            if self.cancel.is_set():
                break
            if kind == "reasoning":
                await self.think(chunk)
                continue
            if self.think_id:
                await self.end_think()
            raw_out.append(chunk)
            for ev in parser.feed(chunk):
                await self.on_event(*ev)
        for ev in parser.finish():
            await self.on_event(*ev)
        if self.cur:  # stream ended mid-slide: keep what we have
            sid = self.cur["id"]
            i = self.index_of(sid)
            if i >= 0:
                s = self.p["slides"][i]
                s["status"] = "done" if s["spec"].get("title") else self.cur["orig_status"]
                await self.slide_event(sid)
            self.cur = None
        return "".join(raw_out)

    # ---------------------------------------------------------------- phase 2: write each slide
    def _writer_context(self, sid: str) -> str:
        i = self.index_of(sid)
        slide = self.p["slides"][i]
        total = len(self.p["slides"])
        lines = ["[deck]", f"User request: {self.request}", f'Deck title: {self.p.get("deck_title") or self.p["name"]}']
        if self.theme.get("dna"):
            lines.append(design.direction(self.theme["dna"]))
        if self.theme["kind"] == "custom":
            lines.append(describe_pages(self.theme) or f'Design: template "{self.theme["name"]}".')
        lines.append("Outline (► = the slide to write now):")
        for k, s in enumerate(self.p["slides"]):
            spec = s["spec"]
            mark = "►" if s["id"] == sid else " "
            src = f' {spec["source"]}' if spec.get("source") else ""
            lines.append(f'{mark} {k + 1}. {s["id"]} {spec["type"]}{src} "{spec.get("title", "")}"' + (f' - {s["brief"]}' if s.get("brief") else ""))
        written = [s for s in self.p["slides"][:i] if s["status"] == "done"][-4:]
        if written:
            lines.append("Most recent slides already written (stay consistent, don't repeat them):")
            lines.extend(f'{s["id"]}: {json.dumps(s["spec"], ensure_ascii=False)}' for s in written)
        lines.extend(_documents(self.p))
        lines.extend(_sources(self.p, 25000))
        lines.append("[/deck]")
        spec = slide["spec"]
        task = f'Write slide {i + 1} of {total} now: type "{spec["type"]}"' + (f', template page {spec["source"]}' if spec.get("source") else "") + f', title "{spec.get("title", "")}".'
        if slide.get("brief"):
            task += f"\nBrief: {slide['brief']}"
        ts = template_slide(self.theme, spec.get("source")) if spec["type"] == "template" else None
        if ts and ts["role"] == "cover" and self.cover_ok:
            task += f"\nThis is the template cover page. The user asked for changes on it - apply exactly what they asked: {self.request}"
        elif ts and ts["role"] == "cover":
            task += (f'\nThis is the template cover page: it must stay exactly the same. Only fill <placeholder> fields (with "#id.pN" / "#id.rRcC" keys) '
                     f'using details the user explicitly gave. If the user gave none, output {{"type":"template","source":"{ts["id"]}","notes":"…"}} with no fill.')
        elif ts and ts["role"] == "closing":
            task += f'\nKeep this closing page as it is unless the user asked otherwise: {{"type":"template","source":"{ts["id"]}","notes":"…"}}.'
        elif ts:
            task += "\nFill this page's heading box and body box with detailed content in the sample's structure."
        elif spec["type"] == "document":
            docs = [s for s in self.p.get("sources", []) if s.get("doc_id") and s.get("pages")]
            if not docs:
                task += ('\nNo attached document page is available to show, so output '
                         '{"type":"document","title":"…","caption":"…","notes":"…","pages":[]} only if a page exists - '
                         'otherwise write this slide as "bullets" with the document\'s details.')
            else:
                task += "\nUse a \"doc\" handle and \"pages\" exactly as listed in the attached documents manifest above."
        elif spec["type"] == "diagram":
            task += ("\nName the real components of this system as nodes (3-7 of them) and connect them with arrows. "
                     "Do not write \"Diagram\", \"Architecture\" or \"Overview\" as a node label - name the actual parts.")
        task += "\nOutput exactly one <slide>{…}</slide>."
        return "\n".join(lines) + "\n\n" + task

    async def write_slide(self, sid: str):
        self.plan_queue = [sid]
        messages = [{"role": "system", "content": WRITER_PROMPT}, {"role": "user", "content": self._writer_context(sid)}]
        await self.retrying(self.stream_call, messages)
        i = self.index_of(sid)
        if i >= 0 and self.p["slides"][i]["status"] != "done" and not self.cancel.is_set():
            await self.retrying(self.stream_call, messages)  # one more try if the reply was unusable
        self.plan_queue = []

    # ---------------------------------------------------------------- phase 3: look at it and fix it
    async def review_slide(self, sid: str):
        i = self.index_of(sid)
        if i < 0 or self.p["slides"][i]["status"] != "done":
            return
        slide = self.p["slides"][i]
        specs = [s["spec"] for s in self.p["slides"]]
        lay = layout_slide(slide["spec"], self.theme, i, specs, self.p.get("deck_title") or self.p["name"])
        png, issues = await asyncio.to_thread(inspect, lay, slide["spec"], self.theme)
        aid = self.uid("a")
        title = slide["spec"].get("title", "")
        await self.activity(aid, "review", f"Reviewing slide {i + 1} · {title}", "running", slide_id=sid,
                            detail=("Checks: " + " ".join(issues)) if issues else "")
        ctx = [f"Slide {sid} (slide {i + 1} of {len(self.p['slides'])}) of the deck \"{self.p.get('deck_title') or self.p['name']}\".",
               f"User request: {self.request}"]
        if slide.get("brief"):
            ctx.append(f"Brief: {slide['brief']}")
        if slide["spec"]["type"] == "template" or self.theme.get("base_slide"):
            ctx.append(describe_pages(self.theme))
        ctx.append("Automatic checks: " + ("; ".join(issues) if issues else "none found"))
        ctx.append(f"Current JSON: {json.dumps(slide['spec'], ensure_ascii=False)}")
        ctx.append(f'Reply <ok/> or <say>…</say><slide ref="{sid}">{{…}}</slide>.')
        text = "\n".join(ctx)
        image = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}
        before = json.dumps(slide["spec"], sort_keys=True)
        with_image = [{"role": "system", "content": REVIEWER_PROMPT}, {"role": "user", "content": [{"type": "text", "text": text}, image]}]
        text_only = [{"role": "system", "content": REVIEWER_PROMPT},
                     {"role": "user", "content": text + "\n(The image could not be attached; rely on the checks and JSON.)"}]
        attempts = []
        if not self.vision_failed:
            attempts.append((with_image, await ai_client.resolve_review_model()))
        attempts.append((text_only, None))
        for msgs, model in attempts:
            self.review_aid, self.review_note, self.review_ok = aid, "", False
            try:
                await self.retrying(self.stream_call, msgs, model, attempts=1 if msgs is with_image else 2)
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if msgs is with_image:  # vision model/backend unusable: stop sending images this turn
                    self.vision_failed = True
                    ai_client.mark_broken(model)
                    continue
                self.review_aid = None
                await self.activity(aid, "review", f"Skipped review of slide {i + 1} ({ai_client.friendly_error(exc)[:80]})", "error", slide_id=sid, detail="")
                return
            finally:
                self.review_aid = None
        j = self.index_of(sid)
        changed = j >= 0 and json.dumps(self.p["slides"][j]["spec"], sort_keys=True) != before
        if changed:
            self.improved += 1
            note = self.review_note.strip() or "polished the layout and wording"
            await self.activity(aid, "review", f"Improved slide {j + 1} · {note}", "done", slide_id=sid, detail="")
        else:
            await self.activity(aid, "review", f"Reviewed slide {i + 1} · looks good", "done", slide_id=sid, detail="")

    # ---------------------------------------------------------------- run
    async def run(self, text: str, selected: list[str], attachments: list[dict]):
        p = self.p
        self.request = text
        cover_ids = {s["id"] for s in p["slides"][:1] if s["spec"].get("type") == "template"}
        self.cover_ok = bool(COVER_WORDS.search(text)) or bool(cover_ids & set(selected))
        store.snapshot(p, f"Before: {text[:60]}")
        existing = p.setdefault("sources", [])
        for att in attachments:
            doc_id = ""
            if att.get("pages"):
                # a stable handle the AI can copy into a slide's "doc" field
                taken = {s.get("doc_id") for s in existing}
                n = len([s for s in existing if s.get("doc_id")]) + 1
                while f"#D{n}" in taken:
                    n += 1
                doc_id = f"#D{n}"
            entry = {"name": att["name"], "text": att["text"], "pages": att.get("pages") or [], "doc_id": doc_id}
            # re-attaching the same file replaces it instead of piling up duplicates
            old = next((s for s in existing if s["name"] == att["name"]), None)
            if old and old.get("doc_id") and not doc_id:
                doc_id = old["doc_id"]
            if old:
                existing[existing.index(old)] = entry
            else:
                existing.append(entry)
            if doc_id:
                entry["doc_id"] = doc_id
        p["chat"].append({"role": "user", "text": text, "selected": selected, "attachments": [a["name"] for a in attachments]})
        content = _workspace(p, self.theme, selected) + "\n\nUser request: " + text
        history = [{"role": m["role"], "content": _compact_assistant(m["content"]) if m["role"] == "assistant" else m["content"]}
                   for m in p["messages"][-HISTORY_MESSAGES:]]
        messages = [{"role": "system", "content": PLANNER_PROMPT}] + history + [{"role": "user", "content": content}]

        reply, error = "", None
        try:
            await self.think("")  # a live "Thinking" row right away while the model reasons
            reply = await self.retrying(self.stream_call, messages, None, ["</plan>"])
            await self.end_think()
            await self.end_step()
            review = config.review_enabled() and not config.demo_mode()
            pending = [s["id"] for s in self.p["slides"] if s["status"] == "planned"]  # includes slides left from an interrupted build
            if pending:
                self.quiet = True
                for sid in pending:
                    if self.cancel.is_set():
                        break
                    await self.write_slide(sid)
                    if review and not self.cancel.is_set():
                        await self.review_slide(sid)
                    store.save_project(p)
                self.quiet = False
                done = sum(1 for s in p["slides"] if s["status"] == "done")
                if not self.cancel.is_set():
                    await self.say(f"Your deck is ready: {done} slides" + (f", and I improved {self.improved} of them after looking at how they rendered" if self.improved else "")
                                   + ". Select any slide on the canvas and tell me what to change, or export it as .pptx.")
            elif review and self.touched and not self.cancel.is_set():
                self.quiet = True
                for sid in list(self.touched):
                    await self.review_slide(sid)
                self.quiet = False
        except asyncio.CancelledError:
            self.cancel.set()
        except Exception as exc:  # network / API errors are reported in the chat
            error = ai_client.friendly_error(exc)
        self.quiet = False
        await self.end_think()
        await self.end_step()
        for s in p["slides"]:
            if s["status"] == "generating":
                s["status"] = "done"
        for it in self.items:  # never leave a spinner running in the saved chat
            if it.get("kind") == "activity" and it.get("status") == "running":
                await self.activity(it["id"], it["type"], it["label"] or "Stopped", "error" if error else "done", **{k: it[k] for k in ("slide_id",) if k in it})
        if self.cancel.is_set():
            await self.activity(self.uid("a"), "stop", "Stopped", "done")
        if error:
            if any(s["status"] == "planned" for s in p["slides"]):
                error += " Your finished slides are saved - say \"continue\" to build the rest."
            await self.activity(self.uid("a"), "error", error, "error")
            await self.emit({"type": "error", "message": error})

        user_msg = text + (f"\n[Attached: {', '.join(a['name'] for a in attachments)}]" if attachments else "")
        if selected:
            user_msg += f"\n[Selected slides: {', '.join(selected)}]"
        p["messages"].append({"role": "user", "content": user_msg})
        p["messages"].append({"role": "assistant", "content": reply or "<say>(no response)</say>"})
        p["chat"].append({"role": "assistant", "items": self.items})
        if p["name"] in ("", "Untitled presentation") and p["slides"]:  # name the deck once it has content
            p["name"] = p.get("deck_title") or p["slides"][0]["spec"].get("title") or p["name"]
        store.save_project(p)
        await self.emit({"type": "done", "project": store.project_view(p)})


async def run_turn(project: dict, text: str, selected: list[str], attachments: list[dict], emit: Emit, cancel: asyncio.Event):
    await Turn(project, emit, cancel).run(text, selected, attachments)
