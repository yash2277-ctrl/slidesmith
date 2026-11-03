"""Smart layouts: switch a slide to another layout instantly, keeping its content (no AI call)."""
from __future__ import annotations

import re


def _split(text: str) -> tuple[str, str]:
    """'Heading: detail' or 'Heading - detail' -> (heading, detail); otherwise first words as heading."""
    m = re.match(r"^\s*([^:–—-]{2,48})\s*[:–—-]\s+(.+)$", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    words = text.split()
    return (" ".join(words[:3]), " ".join(words[3:])) if len(words) > 6 else (text, "")


def _items(spec: dict) -> list[dict]:
    """Any list-like slide -> neutral items {heading, text, icon, label, value}."""
    t = spec["type"]
    if t in ("bullets", "image"):
        out = []
        for b in spec.get("bullets", []):
            h, d = _split(b["text"])
            out.append({"heading": h, "text": (d + (" " + " ".join(b["sub"]) if b["sub"] else "")).strip()})
        return out
    if t == "cards":
        return [dict(c) for c in spec.get("cards", [])]
    if t in ("timeline", "process"):
        return [{"heading": s["heading"], "text": s["text"], "icon": s.get("icon", ""), "label": s.get("label", "")} for s in spec.get("steps", [])]
    if t == "matrix":
        return [dict(q) for q in spec.get("quadrants", [])]
    if t == "stats":
        return [{"heading": s["label"], "text": s.get("detail", ""), "value": s["value"], "icon": s.get("icon", "")} for s in spec.get("stats", [])]
    if t == "funnel":
        return [{"heading": s["label"], "text": s.get("text", ""), "value": s.get("value", "")} for s in spec.get("stages", [])]
    if t == "two_column":
        return [{"heading": col.get("heading", ""), "text": "; ".join(col.get("bullets", []))} for col in (spec.get("left", {}), spec.get("right", {}))]
    if t == "diagram":
        return [{"heading": n.get("label", ""), "text": n.get("text", ""), "icon": n.get("icon", "")} for n in spec.get("nodes", [])]
    return []


def _build(base: dict, target: str, items: list[dict]) -> dict:
    out = {k: base[k] for k in ("title", "notes", "kicker", "subtitle") if base.get(k)}
    out["type"] = target
    if target == "cards":
        out["cards"] = [{"heading": i["heading"], "text": i.get("text", ""), "icon": i.get("icon", "")} for i in items[:6]]
    elif target == "bullets":
        out["bullets"] = [{"text": (i["heading"] + (": " + i["text"] if i.get("text") else "")), "sub": []} for i in items[:6]]
    elif target == "timeline":
        out["steps"] = [{"label": i.get("label") or f"Step {n + 1}", "heading": i["heading"], "text": i.get("text", ""), "icon": i.get("icon", "")}
                        for n, i in enumerate(items[:6])]
    elif target == "process":
        out["steps"] = [{"heading": i["heading"], "text": i.get("text", ""), "icon": i.get("icon", "")} for i in items[:5]]
    elif target == "matrix":
        out["quadrants"] = [{"heading": i["heading"], "text": i.get("text", ""), "icon": i.get("icon", "")} for i in items[:4]]
    elif target == "two_column":
        half = (len(items) + 1) // 2
        out["left"] = {"heading": items[0]["heading"] if items else "", "bullets": [i.get("text") or i["heading"] for i in items[:half]]}
        out["right"] = {"heading": items[half]["heading"] if len(items) > half else "", "bullets": [i.get("text") or i["heading"] for i in items[half:]]}
    elif target == "stats":
        out["stats"] = [{"value": i.get("value", ""), "label": i["heading"], "detail": i.get("text", ""), "icon": i.get("icon", "")} for i in items[:4]]
    elif target == "funnel":
        out["stages"] = [{"label": i["heading"], "value": i.get("value", ""), "text": i.get("text", "")} for i in items[:5]]
    elif target == "diagram":
        nodes = [{"label": i["heading"], "text": i.get("text", ""), "icon": i.get("icon", "")} for i in items[:8]]
        out["nodes"] = nodes
        out["edges"] = [{"from": n, "to": n + 1} for n in range(len(nodes) - 1)]
    if base.get("image"):
        out["image"] = base["image"]
    return out


def alternatives(spec: dict) -> list[str]:
    """Layouts this slide's content can be shown as, in a pleasant cycling order."""
    t = spec.get("type")
    items = _items(spec)
    n = len(items)
    if t in ("title", "closing", "section", "quote", "chart", "table", "quiz", "template") or n < 2:
        return []
    order = ["cards", "process", "timeline", "diagram", "bullets", "two_column", "matrix", "funnel", "stats"]
    ok = []
    for target in order:
        if target == t:
            continue
        if target == "matrix" and n != 4:
            continue
        if target == "process" and not 2 <= n <= 5:
            continue
        if target == "funnel" and not 2 <= n <= 5:
            continue
        if target == "diagram" and not 2 <= n <= 8:
            continue
        if target == "stats" and not (t == "funnel" and all(i.get("value") for i in items)):
            continue
        if target == "two_column" and n < 2:
            continue
        ok.append(target)
    if t == "image":
        ok = [o for o in ok if o in ("bullets", "cards", "two_column")]
    return ok


def remix(spec: dict, target: str | None = None) -> dict | None:
    """Next alternative layout (or a specific one) for this slide."""
    alts = alternatives(spec)
    if not alts:
        return None
    if target not in alts:
        target = alts[0]
    out = _build(spec, target, _items(spec))
    out["remixed_from"] = spec["type"]
    return out
