"""Design DNA: every deck gets its own random-but-consistent design identity.

Two decks on the same topic with the same template should still look different:
the DNA picks component variants, color emphasis, icon family, decoration, title
treatment and the AI's creative angle. Within a deck, repeated slide types also
rotate through variants so the deck itself never looks repetitive.
"""
from __future__ import annotations

import hashlib
import random

CARD = ["soft", "list", "numeral", "centered", "outline", "left_bar", "filled", "top_bar"]
BULLETS = ["dot", "rows", "numbered"]
TIMELINE = ["line", "vertical", "grid"]
STATS = ["cards", "dividers", "rings"]
PROCESS = ["chevrons", "circles"]
TWO_COL = ["panels", "divider"]
MATRIX = ["tinted", "outline"]
TITLE = ["bar", "kicker", "side", "plain"]
DECO = ["none", "corner", "band", "dots", "blob"]
HERO = ["orb", "split", "bar", "frame"]
ICON_SETS = ["mdi", "ph", "tabler", "lucide"]
ICON_STYLE = ["tile", "circle", "plain"]

STRUCTURES = [
    "open with the single most impressive result, then explain how you got there",
    "use one running example or case throughout the deck",
    "include a 'challenges faced and how I solved them' slide",
    "include a 'what I would do differently' or 'lessons learned' slide",
    "end with three crisp key takeaways before the closing slide",
    "include a before/after comparison of the situation",
    "include one slide that explains a concept with a simple analogy",
    "include a short 'by the numbers' slide with honest figures",
    "frame the deck around three guiding questions",
    "include a real-world application or impact slide",
]
ANGLES = [
    "story-led: open with a real-world scenario or hook, then build the argument around it",
    "data-led: lead with the strongest numbers and evidence, then explain what they mean",
    "problem -> solution: frame a clear problem first, then walk through how it was solved",
    "journey: tell it chronologically as a timeline of steps, decisions and lessons",
    "insight-led: every slide title states a takeaway, and the slide proves it",
    "comparison-led: contrast before/after, options or approaches to make the point",
    "skills-led: organize around the skills learned and the evidence for each",
    "impact-led: start from who benefited and measure the impact",
    "process-led: show the workflow end to end, then zoom into the hardest part",
    "reflective: personal, first-person narrative of growth with concrete moments",
]
VISUALS = [
    "favor icons and diagrams (process, matrix, cards with icons)",
    "favor numbers and charts (stats, charts, tables) where honest data exists",
    "favor photos and image slides to make it vivid",
    "favor timelines and step-by-step flows",
    "favor comparisons (two columns, matrices, tables)",
    "favor a balanced mix, never the same layout twice in a row",
]
VOICES = [
    "short, bold statement titles",
    "titles phrased as questions the slide answers",
    "titles that name the specific result or number",
    "plain, precise academic titles",
    "titles in the form 'Topic: key point'",
    "action-verb titles (Built…, Reduced…, Learned…)",
]


def seed_for(project: dict) -> int:
    seed = project.get("design_seed")
    if isinstance(seed, int) and seed:
        return seed
    return int(hashlib.md5(project["id"].encode()).hexdigest()[:8], 16)


def new_seed() -> int:
    return random.SystemRandom().randint(1, 2**31 - 1)


def dna(seed: int) -> dict:
    rnd = random.Random(seed)
    return {
        "seed": seed,
        "card": rnd.choice(CARD),
        "bullets": rnd.choice(BULLETS),
        "timeline": rnd.choice(TIMELINE),
        "stats": rnd.choice(STATS),
        "process": rnd.choice(PROCESS),
        "two_col": rnd.choice(TWO_COL),
        "matrix": rnd.choice(MATRIX),
        "title": rnd.choice(TITLE),
        "deco": rnd.choice(DECO),
        "hero": rnd.choice(HERO),
        "icon_set": rnd.choice(ICON_SETS),
        "icon_style": rnd.choice(ICON_STYLE),
        "radius": rnd.choice([0.0, 0.06, 0.12, 0.2]),
        "palette": rnd.randint(0, 3),
        "photo_pick": rnd.randint(0, 4),
        "angle": rnd.choice(ANGLES),
        "visual": rnd.choice(VISUALS),
        "voice": rnd.choice(VOICES),
        "structure": rnd.choice(STRUCTURES),
    }


SIGNATURE = ("card", "stats", "timeline", "process", "two_col", "matrix", "bullets", "title", "deco", "hero",
             "icon_set", "icon_style", "radius", "palette", "angle", "visual", "voice", "structure")


def distinct_seed(existing: list[dict], tries: int = 80) -> int:
    """A seed whose design differs as much as possible from decks that already exist (same template/theme).
    With hundreds of students on one template, each new deck still gets a design nobody else has."""
    if not existing:
        return new_seed()
    best, best_score = new_seed(), -1.0
    for _ in range(tries):
        seed = new_seed()
        d = dna(seed)
        diffs = sorted(sum(d[k] != e.get(k) for k in SIGNATURE) for e in existing)
        # maximize the closest match's difference, then the average difference
        score = diffs[0] * 100 + sum(diffs) / len(diffs)
        if score > best_score:
            best, best_score = seed, score
    return best


def pick(d: dict, kind: str, options: list[str], occurrence: int) -> str:
    """The deck's variant for this kind, rotated for each repeat of the same slide type."""
    base = options.index(d[kind]) if d.get(kind) in options else 0
    return options[(base + occurrence) % len(options)]


def direction(d: dict) -> str:
    """Creative brief for the AI so decks on the same topic come out different."""
    return (f"Creative direction for THIS deck (hundreds of people may make a deck on the same topic with the same template - "
            f"make this one distinctive): angle: {d['angle']}; visuals: {d['visual']}; slide titles: {d['voice']}; "
            f"structure idea: {d.get('structure', '')}. "
            "Use original, specific slide titles (never generic ones like 'Introduction' or 'Overview' unless the template or the user requires them), "
            "a concrete example or angle of your own, and an order and mix of layouts that suits this direction. "
            "The user's own instructions ALWAYS win over this direction - it only fills in what the user did not specify.")
