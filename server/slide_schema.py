"""Slide types and normalization of (possibly partial) slide specs.

A slide spec is a plain dict, e.g. {"type": "bullets", "title": "...", "bullets": [...]}.
Specs are template-agnostic: the layout engine decides how each type looks.
"""
from __future__ import annotations

from typing import Any

SLIDE_TYPES = {
    "title": "Opening slide: title, subtitle, optional kicker (small line above title, e.g. event or date).",
    "section": "Section divider: title, optional subtitle.",
    "bullets": "Title plus 3-6 bullets. Each bullet is a string or {text, sub:[strings]}.",
    "two_column": "Title plus left/right columns, each {heading, bullets:[strings]}. Good for before/after, pros/cons, compare.",
    "cards": "Title plus 2-6 cards [{heading, text}]. Good for pillars, features, agenda, options.",
    "stats": "Title plus 2-4 big numbers [{value, label, detail}].",
    "timeline": "Title plus 3-6 steps [{label, heading, text}]; label is a date/phase like 'Q1' or 'Step 1'.",
    "chart": "Title plus chart {kind: column|bar|line|pie|doughnut, categories:[...], series:[{name, values:[numbers]}], unit} and a one-line takeaway.",
    "table": "Title plus columns:[strings] and rows:[[strings]] (max 6 columns x 8 rows).",
    "quote": "A single quote with attribution.",
    "closing": "Final slide: title (e.g. thank you / call to action), subtitle, optional contact line.",
    "template": "A copy of one of the user's template sample pages with some text replaced.",
    "image": "Photo + text: title, bullets (or text), image (photo search words), side (left|right).",
    "document": "A page of a document the user attached, shown as the real page image: title, doc ('#D1'), pages ([1]), caption.",
    "diagram": "A drawn diagram: title, nodes [{label, text, icon, tone}] and edges [{from, to, label}], plus caption.",
    "matrix": "2x2 grid (SWOT, impact/effort...): title, quadrants:[{heading, text, icon}] x4, optional x_axis/y_axis labels.",
    "process": "Chevron flow of 3-5 steps: title, steps:[{heading, text, icon}].",
    "funnel": "Narrowing funnel of 3-5 stages: title, stages:[{label, value, text}].",
    "quiz": "Interactive question: title (the question), options:[2-5 strings], answer (index of the correct option), explanation.",
}

CHART_KINDS = ("column", "bar", "line", "pie", "doughnut")


def _s(value: Any, limit: int = 600) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _list(value: Any, limit: int) -> list:
    return list(value)[:limit] if isinstance(value, list) else []


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("%", "").replace("$", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _image(value: Any):
    if isinstance(value, str):
        return _s(value, 120) or None
    if isinstance(value, dict) and (value.get("src") or value.get("query")):
        out = {k: value[k] for k in ("src", "credit", "query", "source") if isinstance(value.get(k), str)}
        for k in ("w", "h"):
            if isinstance(value.get(k), (int, float)):
                out[k] = value[k]
        return out
    return None


def _icon(value: Any) -> str:
    return _s(value, 60)


def _with_kw(item: dict, raw: dict) -> dict:
    kw = _s(raw.get("icon_kw"), 60)
    if kw:
        item["icon_kw"] = kw
    return item


def _bullets(value: Any, limit: int = 8) -> list[dict]:
    out = []
    for item in _list(value, limit):
        if isinstance(item, str):
            if item.strip():
                out.append({"text": _s(item), "sub": []})
        elif isinstance(item, dict):
            text = _s(item.get("text"))
            subs = [_s(x) for x in _list(item.get("sub"), 4) if _s(x)]
            if text or subs:
                out.append({"text": text, "sub": subs})
    return out


def normalize(raw: Any) -> dict:
    """Coerce a model-produced (maybe partial) slide dict into a clean spec."""
    if not isinstance(raw, dict):
        return {"type": "bullets", "title": ""}
    stype = raw.get("type") if raw.get("type") in SLIDE_TYPES else "bullets"
    spec: dict[str, Any] = {"type": stype, "title": _s(raw.get("title"), 200)}
    for key in ("subtitle", "kicker", "takeaway", "attribution", "contact", "notes", "text", "explanation", "x_axis", "y_axis", "caption"):
        val = _s(raw.get(key), 2000 if key == "notes" else 400)
        if val:
            spec[key] = val
    img = _image(raw.get("image"))
    if img:
        spec["image"] = img
    if raw.get("side") in ("left", "right"):
        spec["side"] = raw["side"]

    if stype in ("bullets", "image"):
        spec["bullets"] = _bullets(raw.get("bullets"))
    elif stype == "two_column":
        for side in ("left", "right"):
            col = raw.get(side) if isinstance(raw.get(side), dict) else {}
            spec[side] = {
                "heading": _s(col.get("heading"), 120),
                "bullets": [b["text"] for b in _bullets(col.get("bullets"), 7)],
            }
    elif stype == "cards":
        spec["cards"] = [
            _with_kw({"heading": _s(c.get("heading"), 120), "text": _s(c.get("text"), 400), "icon": _icon(c.get("icon"))}, c)
            for c in _list(raw.get("cards"), 6)
            if isinstance(c, dict)
        ]
    elif stype == "stats":
        spec["stats"] = [
            _with_kw({"value": _s(c.get("value"), 24), "label": _s(c.get("label"), 120), "detail": _s(c.get("detail"), 240), "icon": _icon(c.get("icon"))}, c)
            for c in _list(raw.get("stats"), 4)
            if isinstance(c, dict)
        ]
    elif stype == "timeline":
        spec["steps"] = [
            _with_kw({"label": _s(c.get("label"), 40), "heading": _s(c.get("heading"), 120), "text": _s(c.get("text"), 300), "icon": _icon(c.get("icon"))}, c)
            for c in _list(raw.get("steps"), 6)
            if isinstance(c, dict)
        ]
    elif stype == "document":
        spec["doc"] = _s(raw.get("doc"), 12)
        pages = []
        for value in _list(raw.get("pages"), 3):
            try:
                pages.append(max(1, int(value)))
            except (TypeError, ValueError):
                continue
        spec["pages"] = pages[:3]
        spec["caption"] = _s(raw.get("caption"), 240)
    elif stype == "diagram":
        nodes = []
        for i, node in enumerate(_list(raw.get("nodes"), 10)):
            if isinstance(node, dict):
                label = _s(node.get("label") or node.get("text"), 60)
                if not label:
                    continue
                nodes.append({"id": i, "label": label,
                              "text": _s(node.get("text") if node.get("text") != node.get("label") else "", 200),
                              "icon": _icon(node.get("icon")),
                              "icon_kw": _s(node.get("icon_kw"), 60)})
        edges = []
        for edge in _list(raw.get("edges"), 16):
            if not isinstance(edge, dict):
                continue
            try:
                a, b = int(edge.get("from", -1)), int(edge.get("to", -1))
            except (TypeError, ValueError):
                continue
            if a == b or not (0 <= a < len(nodes) and 0 <= b < len(nodes)):
                continue
            edges.append({"from": a, "to": b, "label": _s(edge.get("label"), 40),
                          "dash": bool(edge.get("dash"))})
        spec["nodes"] = nodes
        spec["edges"] = edges
        spec["caption"] = _s(raw.get("caption"), 240)
    elif stype == "chart":
        chart = raw.get("chart") if isinstance(raw.get("chart"), dict) else {}
        kind = chart.get("kind") if chart.get("kind") in CHART_KINDS else "column"
        categories = [_s(c, 60) for c in _list(chart.get("categories"), 12)]
        series = []
        for s in _list(chart.get("series"), 4):
            if not isinstance(s, dict):
                continue
            values = [_num(v) for v in _list(s.get("values"), 12)]
            series.append({"name": _s(s.get("name"), 60) or "Series", "values": [v if v is not None else 0.0 for v in values]})
        if kind in ("pie", "doughnut"):
            series = series[:1]
        spec["chart"] = {"kind": kind, "categories": categories, "series": series, "unit": _s(chart.get("unit"), 12)}
    elif stype == "table":
        columns = [_s(c, 60) for c in _list(raw.get("columns"), 6)]
        rows = []
        for r in _list(raw.get("rows"), 8):
            if isinstance(r, list):
                rows.append([_s(c, 160) for c in r[: max(len(columns), 1)]])
        spec["columns"] = columns
        spec["rows"] = rows
    elif stype == "quote":
        spec["quote"] = _s(raw.get("quote"), 500)
    elif stype == "matrix":
        spec["quadrants"] = [
            _with_kw({"heading": _s(c.get("heading"), 80), "text": _s(c.get("text"), 300), "icon": _icon(c.get("icon"))}, c)
            for c in _list(raw.get("quadrants"), 4) if isinstance(c, dict)
        ]
    elif stype == "process":
        spec["steps"] = [
            _with_kw({"heading": _s(c.get("heading"), 60), "text": _s(c.get("text"), 240), "icon": _icon(c.get("icon"))}, c)
            for c in _list(raw.get("steps"), 5) if isinstance(c, dict)
        ]
    elif stype == "funnel":
        spec["stages"] = [
            {"label": _s(c.get("label"), 60), "value": _s(c.get("value"), 24), "text": _s(c.get("text"), 200)}
            for c in _list(raw.get("stages"), 5) if isinstance(c, dict)
        ]
    elif stype == "quiz":
        spec["options"] = [_s(o, 160) for o in _list(raw.get("options"), 5) if _s(o, 160)]
        try:
            spec["answer"] = max(0, min(len(spec["options"]) - 1, int(raw.get("answer", 0))))
        except (TypeError, ValueError):
            spec["answer"] = 0
    elif stype == "template":
        spec["source"] = _s(raw.get("source"), 12).upper()
        fill = raw.get("fill") if isinstance(raw.get("fill"), dict) else {}
        clean = {}
        for key, value in list(fill.items())[:60]:
            if not isinstance(key, str) or not key.startswith("#"):
                continue
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                clean[key] = str(value)[:2000]
            elif isinstance(value, list):
                items = []
                for item in value[:30]:
                    if isinstance(item, (str, int, float)):
                        items.append(str(item)[:600])
                    elif isinstance(item, dict):
                        try:
                            level = int(item.get("level", 0) or 0)
                        except (TypeError, ValueError):
                            level = 0
                        items.append({"text": _s(item.get("text"), 600), "level": max(0, min(4, level))})
                clean[key] = items
        spec["fill"] = clean
    return spec


def validate(spec: dict) -> str | None:
    """Return an error message if a completed spec is unusable, else None."""
    t = spec["type"]
    if t == "template":
        return None if spec.get("source") else "A 'template' slide needs 'source' (e.g. \"T3\")."
    if t != "quote" and not spec.get("title"):
        return "Missing 'title'."
    if t == "bullets" and not spec.get("bullets"):
        return "A 'bullets' slide needs a non-empty 'bullets' list."
    if t == "cards" and len(spec.get("cards", [])) < 2:
        return "A 'cards' slide needs 2-6 cards."
    if t == "stats" and not spec.get("stats"):
        return "A 'stats' slide needs 1-4 stats."
    if t == "timeline" and len(spec.get("steps", [])) < 2:
        return "A 'timeline' slide needs 2-6 steps."
    if t == "chart":
        chart = spec["chart"]
        if not chart["categories"] or not chart["series"]:
            return "A 'chart' slide needs categories and at least one series."
        for s in chart["series"]:
            if len(s["values"]) != len(chart["categories"]):
                return f"Series '{s['name']}' has {len(s['values'])} values but there are {len(chart['categories'])} categories."
    if t == "table" and (not spec.get("columns") or not spec.get("rows")):
        return "A 'table' slide needs columns and rows."
    if t == "quote" and not spec.get("quote"):
        return "A 'quote' slide needs 'quote'."
    if t == "matrix" and len(spec.get("quadrants", [])) < 4:
        return "A 'matrix' slide needs 4 quadrants."
    if t == "process" and len(spec.get("steps", [])) < 2:
        return "A 'process' slide needs 2-5 steps."
    if t == "funnel" and len(spec.get("stages", [])) < 2:
        return "A 'funnel' slide needs 2-5 stages."
    if t == "quiz" and len(spec.get("options", [])) < 2:
        return "A 'quiz' slide needs 2-5 options and an 'answer' index."
    if t == "image" and not (spec.get("bullets") or spec.get("text")):
        return "An 'image' slide needs bullets or text."
    if t == "document":
        if not spec.get("doc"):
            return "A 'document' slide needs 'doc' (the attached document id, e.g. \"#D1\")."
        if not spec.get("pages"):
            return "A 'document' slide needs 'pages' (which pages to show, e.g. [1])."
    if t == "diagram":
        if len(spec.get("nodes", [])) < 2:
            return "A 'diagram' slide needs 2-10 nodes."
        if not spec.get("edges"):
            return "A 'diagram' slide needs edges connecting the nodes (e.g. [{\"from\":0,\"to\":1}])."
    return None


def outline_line(index: int, slide: dict) -> str:
    spec = slide["spec"]
    status = "" if slide.get("status") == "done" else f" [{slide.get('status')}]"
    return f'{index + 1}. {slide["id"]} ({spec["type"]}) "{spec.get("title") or spec.get("quote", "")[:60]}"{status}'
