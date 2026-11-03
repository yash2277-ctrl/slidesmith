"""Offline demo model: streams protocol text like a real model would, so the
whole live-building experience can be tried before the AI endpoint is reachable."""
from __future__ import annotations

import asyncio
import json
import re


def _topic(user_text: str) -> str:
    text = re.sub(r"(?i)^(make|create|build|generate|design)\s+(me\s+)?(a\s+|an\s+)?(\d+[- ]slide\s+)?(ppt|deck|presentation|slides?)\s*(on|about|for)?\s*", "", user_text.strip())
    text = text.strip(" .!?") or "Your Topic"
    return text[:60][0].upper() + text[:60][1:]


def _deck(topic: str) -> list[dict]:
    t = topic
    return [
        {"type": "title", "kicker": "Demo deck", "title": t, "subtitle": "An overview built live in SlideSmith", "notes": f"Welcome everyone. Today we look at {t}."},
        {"type": "cards", "title": "What we'll cover", "cards": [
            {"heading": "Context", "text": f"Why {t} matters right now and what is changing."},
            {"heading": "Opportunity", "text": "Where the biggest gains are and who benefits."},
            {"heading": "Plan", "text": "A phased roadmap with clear milestones."}], "notes": "Three parts: context, opportunity, plan."},
        {"type": "bullets", "title": "Why this matters now", "bullets": [
            "Expectations are rising faster than current solutions",
            {"text": "New tools make change cheaper than ever", "sub": ["Lower cost to experiment", "Faster feedback loops"]},
            "Early movers set the standard for everyone else"], "notes": "Set up the urgency."},
        {"type": "stats", "title": "The opportunity at a glance", "stats": [
            {"value": "3x", "label": "Faster delivery", "detail": "Illustrative example figure"},
            {"value": "40%", "label": "Lower cost", "detail": "Illustrative example figure"},
            {"value": "90%", "label": "Satisfaction", "detail": "Illustrative example figure"}], "notes": "These numbers are illustrative placeholders."},
        {"type": "two_column", "title": "Today vs. tomorrow", "left": {"heading": "Today", "bullets": ["Manual, slow processes", "Siloed information", "Reactive decisions"]},
         "right": {"heading": "Tomorrow", "bullets": ["Automated workflows", "One shared source of truth", "Proactive, data-led choices"]}, "notes": "Contrast the current and future state."},
        {"type": "chart", "title": "Adoption is accelerating", "chart": {"kind": "column", "categories": ["2022", "2023", "2024", "2025"],
         "series": [{"name": "Adoption", "values": [12, 21, 34, 48]}], "unit": "%"}, "takeaway": "Adoption roughly quadrupled in three years (illustrative data).", "notes": "Illustrative trend."},
        {"type": "timeline", "title": "Roadmap", "steps": [
            {"label": "Phase 1", "heading": "Discover", "text": "Map needs and pick a pilot"},
            {"label": "Phase 2", "heading": "Pilot", "text": "Launch with one team"},
            {"label": "Phase 3", "heading": "Scale", "text": "Roll out across the org"},
            {"label": "Phase 4", "heading": "Optimize", "text": "Measure and improve"}], "notes": "Walk through the phases."},
        {"type": "diagram", "title": "How it fits together", "nodes": [
            {"label": "Client", "text": "Web & mobile apps"},
            {"label": "Gateway", "text": "Auth, rate limits"},
            {"label": "Services", "text": "Domain logic"},
            {"label": "Data", "text": "Store & search"}],
         "edges": [{"from": 0, "to": 1, "label": "HTTPS"}, {"from": 1, "to": 2}, {"from": 2, "to": 3, "dash": True}],
         "caption": "A simple request path - each layer scales independently.", "notes": "Walk left to right."},
        {"type": "quote", "quote": "The best way to predict the future is to create it.", "attribution": "Peter Drucker", "notes": "Pause here."},
        {"type": "closing", "title": "Thank you", "subtitle": "Questions & discussion", "contact": "hello@example.com", "notes": "Open the floor."},
    ]


async def stream(messages: list[dict]):
    last = messages[-1]["content"] if messages else ""
    m = re.search(r"User request:\s*(.*)\Z", last, re.S)
    request = (m.group(1) if m else last).strip()
    has_deck = "Slides (in order):\n(none)" not in last

    yield "reasoning", "Reading the request and deciding on a structure for the deck. "
    await asyncio.sleep(0.4)

    if has_deck:
        out = ('<say>Demo mode: connect your AI endpoint in Settings for real edits. Here is a sample change — '
               'I added a next-steps slide.</say><step>Adding a next-steps slide</step><slide>'
               + json.dumps({"type": "cards", "title": "Next steps", "cards": [
                   {"heading": "Decide", "text": "Agree on scope and owners this week."},
                   {"heading": "Pilot", "text": "Run a 4-week pilot with one team."},
                   {"heading": "Review", "text": "Share results and plan the rollout."}], "notes": "Close with concrete actions."})
               + "</slide><say>Done. Select a slide on the canvas to target your next request.</say>")
    else:
        topic = _topic(request)
        deck = _deck(topic)
        plan = [{"type": s["type"], "title": s.get("title") or s.get("quote", "")[:40]} for s in deck]
        out = f'<say>Demo mode (no AI endpoint configured): building a sample deck about "{topic}" so you can see the live builder.</say>'
        out += f'<step>Planning the outline</step><plan title="{topic}">' + json.dumps(plan) + "</plan>"
        for i, s in enumerate(deck):
            if i in (0, 3, 6):
                out += "<step>" + ["Designing the opening", "Building the data slides", "Laying out the roadmap"][i // 3] + "</step>"
            out += "<slide>" + json.dumps(s, ensure_ascii=False) + "</slide>"
        out += "<say>Your demo deck is ready. Add your AI endpoint in Settings to generate real content.</say>"

    i = 0
    while i < len(out):
        step = 14
        yield "content", out[i:i + step]
        i += step
        await asyncio.sleep(0.012)
