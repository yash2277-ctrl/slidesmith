"""Built-in themes. Custom uploaded templates produce the same profile shape
(see template_analyzer.py) plus layout/placeholder information."""
from __future__ import annotations

import copy

SLIDE_W = 13.333  # inches, 16:9
SLIDE_H = 7.5


def _theme(id, name, dark, colors, heading, body, title_style, heading_bold=True, style=None):
    base = {
        "id": id,
        "name": name,
        "kind": "builtin",
        "slide_w": SLIDE_W,
        "slide_h": SLIDE_H,
        "dark": dark,
        "fonts": {"heading": heading, "body": body, "heading_bold": heading_bold},
        "title_style": title_style,
        "colors": colors,
    }
    if style:
        base["style"] = style
    return base


BUILTIN_THEMES = [
    _theme(
        "midnight", "Midnight", True,
        {"bg": "#0B1020", "bg_alt": "#111A36", "text": "#F4F6FF", "muted": "#98A3C7",
         "accent": "#7C9CFF", "accent2": "#4FD1C5", "accent3": "#F6AD55", "accent4": "#F687B3",
         "surface": "#151E3D", "border": "#26315A", "on_accent": "#0B1020"},
        "Segoe UI", "Segoe UI", "orb",
    ),
    _theme(
        "clean", "Clean Corporate", False,
        {"bg": "#FFFFFF", "bg_alt": "#0F2A5F", "text": "#0F172A", "muted": "#5B6578",
         "accent": "#2563EB", "accent2": "#0EA5E9", "accent3": "#10B981", "accent4": "#F59E0B",
         "surface": "#F3F6FB", "border": "#DCE3EE", "on_accent": "#FFFFFF"},
        "Segoe UI", "Segoe UI", "split",
    ),
    _theme(
        "paper", "Editorial", False,
        {"bg": "#F6F3EC", "bg_alt": "#1E1A16", "text": "#1E1A16", "muted": "#6E6458",
         "accent": "#C2410C", "accent2": "#0F766E", "accent3": "#A16207", "accent4": "#7C3AED",
         "surface": "#ECE6DA", "border": "#D9D0C0", "on_accent": "#FFFFFF"},
        "Georgia", "Segoe UI", "bar", heading_bold=False,
    ),
    _theme(
        "aurora", "Aurora", True,
        {"bg": "#130A2A", "bg_alt": "#1E0F40", "text": "#F7F3FF", "muted": "#B3A6D6",
         "accent": "#A78BFA", "accent2": "#F472B6", "accent3": "#38BDF8", "accent4": "#FBBF24",
         "surface": "#22134A", "border": "#3A2770", "on_accent": "#130A2A"},
        "Century Gothic", "Segoe UI", "orb",
    ),
    _theme(
        "sage", "Sage", False,
        {"bg": "#F2F5F0", "bg_alt": "#1F3B2E", "text": "#15261E", "muted": "#5A6B61",
         "accent": "#2F7D5B", "accent2": "#C9A227", "accent3": "#3B82F6", "accent4": "#B45309",
         "surface": "#E4EBE1", "border": "#CDD8C9", "on_accent": "#FFFFFF"},
        "Cambria", "Calibri", "frame",
    ),
    _theme(
        "bold", "Bold Mono", False,
        {"bg": "#FFFFFF", "bg_alt": "#111111", "text": "#111111", "muted": "#666666",
         "accent": "#FF4D2E", "accent2": "#111111", "accent3": "#FFB800", "accent4": "#2E7DFF",
         "surface": "#F2F2F2", "border": "#E2E2E2", "on_accent": "#FFFFFF"},
        "Arial Black", "Arial", "bar", heading_bold=False,
    ),
    _theme(
        "slate", "Slate & Lime", True,
        {"bg": "#1C2026", "bg_alt": "#252A32", "text": "#EEF1F4", "muted": "#9AA3AE",
         "accent": "#C6F36B", "accent2": "#5EEAD4", "accent3": "#FCA5A5", "accent4": "#93C5FD",
         "surface": "#262C35", "border": "#353C47", "on_accent": "#1C2026"},
        "Trebuchet MS", "Segoe UI", "split",
    ),
]

BUILTIN_THEMES += [
    _theme(
        "ocean", "Deep Ocean", True,
        {"bg": "#062A33", "bg_alt": "#0A3B47", "text": "#EAF7F9", "muted": "#8FB8C0",
         "accent": "#2DD4BF", "accent2": "#38BDF8", "accent3": "#FBBF24", "accent4": "#F472B6",
         "surface": "#0B3944", "border": "#155160", "on_accent": "#062A33"},
        "Segoe UI", "Segoe UI", "orb",
    ),
    _theme(
        "sunset", "Sunset", True,
        {"bg": "#1E1022", "bg_alt": "#3A1631", "text": "#FFF3EC", "muted": "#C9A9B8",
         "accent": "#FB7185", "accent2": "#FDBA74", "accent3": "#C084FC", "accent4": "#67E8F9",
         "surface": "#2C1830", "border": "#4A2846", "on_accent": "#1E1022"},
        "Century Gothic", "Segoe UI", "orb",
    ),
    _theme(
        "minimal", "Minimal", False,
        {"bg": "#FFFFFF", "bg_alt": "#F4F4F5", "text": "#18181B", "muted": "#71717A",
         "accent": "#18181B", "accent2": "#3F3F46", "accent3": "#A1A1AA", "accent4": "#52525B",
         "surface": "#F4F4F5", "border": "#E4E4E7", "on_accent": "#FFFFFF"},
        "Segoe UI", "Segoe UI", "frame",
    ),
    _theme(
        "coral", "Coral Pop", False,
        {"bg": "#FFF8F5", "bg_alt": "#FF6B57", "text": "#2A1A17", "muted": "#7A5F59",
         "accent": "#FF6B57", "accent2": "#2A9D8F", "accent3": "#E9C46A", "accent4": "#264653",
         "surface": "#FFEDE7", "border": "#F6D6CC", "on_accent": "#FFFFFF"},
        "Trebuchet MS", "Segoe UI", "split",
    ),
    _theme(
        "royal", "Royal", True,
        {"bg": "#0E1A3A", "bg_alt": "#15244D", "text": "#F5F1E6", "muted": "#AAB1C7",
         "accent": "#D4AF37", "accent2": "#7DA2FF", "accent3": "#E58FA0", "accent4": "#8BD3C7",
         "surface": "#172654", "border": "#26366B", "on_accent": "#0E1A3A"},
        "Georgia", "Segoe UI", "frame", heading_bold=False,
    ),
    _theme(
        "neon", "Neon Night", True,
        {"bg": "#09090B", "bg_alt": "#111114", "text": "#FAFAFA", "muted": "#A1A1AA",
         "accent": "#A3FF12", "accent2": "#FF2E93", "accent3": "#22D3EE", "accent4": "#FACC15",
         "surface": "#161618", "border": "#27272A", "on_accent": "#09090B"},
        "Arial Black", "Segoe UI", "bar", heading_bold=False,
    ),
    _theme(
        "bauhaus", "Bauhaus", False,
        {"bg": "#F0F0F0", "bg_alt": "#121212", "text": "#121212", "muted": "#555555",
         "accent": "#D02020", "accent2": "#1040C0", "accent3": "#F0C020", "accent4": "#121212",
         "surface": "#FFFFFF", "border": "#121212", "on_accent": "#FFFFFF"},
        "Outfit", "Outfit", "bauhaus", style="bauhaus",
    ),
    _theme(
        "sketch", "Sketchbook", False,
        {"bg": "#FBF7EE", "bg_alt": "#F3ECDC", "text": "#23304A", "muted": "#6B7280",
         "accent": "#2B5DA8", "accent2": "#C0392B", "accent3": "#1E8A5A", "accent4": "#B77818",
         "surface": "#FFFDF6", "border": "#23304A", "on_accent": "#FFFFFF"},
        "Segoe Print", "Ink Free", "bar", heading_bold=False,
    ),
]

_BY_ID = {t["id"]: t for t in BUILTIN_THEMES}
DEFAULT_THEME_ID = "midnight"


def get_builtin(theme_id: str) -> dict | None:
    t = _BY_ID.get(theme_id)
    return copy.deepcopy(t) if t else None


def builtin_summaries() -> list[dict]:
    return [
        {"id": t["id"], "name": t["name"], "kind": "builtin", "dark": t["dark"],
         "colors": t["colors"], "fonts": t["fonts"]}
        for t in BUILTIN_THEMES
    ]
