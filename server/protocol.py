"""Incremental parser for the tag protocol the model writes.

The model streams plain text containing tags such as:
    <say>…</say>  <step>…</step>  <plan title="…">[…]</plan>
    <slide ref="s3">{…json…}</slide>  <delete ref="s3"/>  <move ref="s3" after="s7"/>  <theme id="aurora"/>
Using text tags instead of function calling keeps this working with any
OpenAI-compatible endpoint, and lets us render slides while their JSON is still streaming.
"""
from __future__ import annotations

import re

import jiter

TAGS = {"say", "step", "plan", "slide", "delete", "move", "theme", "think", "ok"}
TEXT_TAGS = {"say", "step", "think"}
OPEN_RE = re.compile(r'<([a-z_]+)((?:\s+[a-z_]+\s*=\s*"[^"]*")*)\s*(/?)>', re.I)
ATTR_RE = re.compile(r'([a-z_]+)\s*=\s*"([^"]*)"', re.I)
MAYBE_TAG_RE = re.compile(r'^</?[a-z_]*(\s+[a-z_]*(\s*=\s*("[^"]*"?)?)?)*\s*/?$', re.I)
FENCE_RE = re.compile(r"```[a-zA-Z]*\n?")


def parse_partial_json(text: str):
    """Best-effort parse of an incomplete JSON value (object or array)."""
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        return None
    body = text[start:].strip()
    body = re.sub(r"```\s*$", "", body)
    try:
        return jiter.from_json(body.encode("utf-8"), partial_mode="trailing-strings")
    except ValueError:
        # trailing junk after a complete value: cut at the last closing bracket
        for end in range(len(body), 0, -1):
            if body[end - 1] in "}]":
                try:
                    return jiter.from_json(body[:end].encode("utf-8"), partial_mode="trailing-strings")
                except ValueError:
                    continue
        return None


def complete_json(text: str):
    """The first *complete* JSON object in text (ignoring trailing junk), or None if it was cut off."""
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    import json
                    return json.loads(text[start:i + 1])
                except ValueError:
                    return None
    return None


class StreamParser:
    def __init__(self):
        self.buf = ""
        self.pos = 0
        self.open: dict | None = None  # {"tag", "attrs", "start", "emitted"}

    def feed(self, chunk: str) -> list[tuple]:
        self.buf += chunk
        return self._scan(final=False)

    def finish(self) -> list[tuple]:
        events = self._scan(final=True)
        if self.open:  # unterminated tag at end of stream: close it with what we have
            o = self.open
            content = self.buf[o["start"]:]
            if o["tag"] in TEXT_TAGS and len(content) > o["emitted"]:
                events.append(("text_delta", o["tag"], o["attrs"], content[o["emitted"]:]))
            events.append(("close", o["tag"], o["attrs"], content))
            self.open = None
        return events

    def _scan(self, final: bool) -> list[tuple]:
        ev: list[tuple] = []
        while True:
            if self.open:
                o = self.open
                closing = f"</{o['tag']}>"
                idx = self.buf.find(closing, o["start"])
                if idx < 0:
                    idx_ci = self.buf.lower().find(closing.lower(), o["start"])
                    idx = idx_ci
                if idx >= 0:
                    content = self.buf[o["start"]:idx]
                    if o["tag"] in TEXT_TAGS and len(content) > o["emitted"]:
                        ev.append(("text_delta", o["tag"], o["attrs"], content[o["emitted"]:]))
                    ev.append(("close", o["tag"], o["attrs"], content))
                    self.pos = idx + len(closing)
                    self.open = None
                    continue
                content = self.buf[o["start"]:]
                if o["tag"] in TEXT_TAGS:
                    safe = len(content)
                    lt = content.rfind("<")
                    if lt >= 0 and len(content) - lt < len(closing):
                        safe = lt
                    if safe > o["emitted"]:
                        ev.append(("text_delta", o["tag"], o["attrs"], content[o["emitted"]:safe]))
                        o["emitted"] = safe
                else:
                    ev.append(("partial", o["tag"], o["attrs"], content))
                return ev

            lt = self.buf.find("<", self.pos)
            if lt < 0:
                self._outside(ev, self.buf[self.pos:])
                self.pos = len(self.buf)
                return ev
            if lt > self.pos:
                self._outside(ev, self.buf[self.pos:lt])
                self.pos = lt
            m = OPEN_RE.match(self.buf, lt)
            if m and m.group(1).lower() in TAGS:
                tag = m.group(1).lower()
                attrs = {k.lower(): v for k, v in ATTR_RE.findall(m.group(2) or "")}
                self.pos = m.end()
                if m.group(3) == "/":
                    ev.append(("selfclose", tag, attrs, ""))
                else:
                    self.open = {"tag": tag, "attrs": attrs, "start": m.end(), "emitted": 0}
                    ev.append(("open", tag, attrs, ""))
                continue
            rest = self.buf[lt:]
            if not final and "\n" not in rest and len(rest) < 200 and MAYBE_TAG_RE.match(rest):
                return ev  # possibly an incomplete tag; wait for more text
            # stray closing tag of a known kind or a plain '<' in prose
            close_m = re.match(r"</([a-z_]+)>", rest, re.I)
            if close_m and close_m.group(1).lower() in TAGS:
                self.pos = lt + close_m.end()
                continue
            self._outside(ev, "<")
            self.pos = lt + 1

    @staticmethod
    def _outside(ev: list, text: str):
        text = FENCE_RE.sub("", text)
        if text:
            ev.append(("text_delta", "say", {}, text))
