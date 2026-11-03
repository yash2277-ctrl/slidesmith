"""Shared slide specs covering every slide type the app can build (used by the
Bauhaus render test and the QA check)."""
from server.slide_schema import normalize

SPECS = [
    {"type": "title", "kicker": "Form follows function", "title": "Bauhaus Design System",
     "subtitle": "Geometry, primary color and honest construction for modern decks"},
    {"type": "section", "title": "Foundations of the style", "subtitle": "Shapes, color blocking and bold typography"},
    {"type": "bullets", "title": "Core principles", "bullets": [
        {"text": "Geometric purity: only circles, squares and triangles", "sub": ["Every decoration derives from the three primary shapes"]},
        {"text": "Hard shadows, never blurred ones", "sub": ["Depth comes from layering, not soft effects"]},
        {"text": "Thick black borders define every element", "sub": ["2px on mobile, 4px on desktop compositions"]},
        {"text": "Asymmetric balance over static symmetry", "sub": []},
    ]},
    {"type": "cards", "title": "What the style gives you", "cards": [
        {"heading": "Color blocking", "text": "Whole panels in red, blue or yellow carry sections and give slides instant hierarchy."},
        {"heading": "Constructivist type", "text": "Massive uppercase headlines with tight tracking, set in the geometric Outfit face."},
        {"heading": "Mechanical motion", "text": "Fast, decisive interactions: buttons press down, cards lift, nothing drifts."},
    ]},
    {"type": "stats", "title": "The palette in numbers", "stats": [
        {"value": "1926", "label": "Workshop years", "detail": "Peak of the Dessau era"},
        {"value": "3", "label": "Primary shapes", "detail": "Circle, square, triangle"},
        {"value": "100%", "label": "Solid color", "detail": "No gradients, no blur"},
    ]},
    {"type": "timeline", "title": "How a Bauhaus page is built", "steps": [
        {"label": "01", "heading": "Block", "text": "Choose the section's solid primary color field."},
        {"label": "02", "heading": "Frame", "text": "Add the thick black border and hard shadow."},
        {"label": "03", "heading": "Place", "text": "Set type on the grid, then break it once."},
        {"label": "04", "heading": "Mark", "text": "Finish with circle, square and triangle."},
    ]},
    {"type": "process", "title": "From blank page to poster", "steps": [
        {"heading": "Sketch", "text": "Block out the composition with pure geometry before any detail."},
        {"heading": "Ink", "text": "Draw the 4px black borders and offset shadows that hold it together."},
        {"heading": "Color", "text": "Fill panels with pure primaries; keep black and white dominant."},
        {"heading": "Cut", "text": "Remove everything that does not function."},
    ]},
    {"type": "two_column", "title": "Form vs function", "left": {"heading": "Form", "bullets": [
        "Pure geometric composition", "Primary colors only", "Sharp corners or full circles"]},
     "right": {"heading": "Function", "bullets": [
        "Every element earns its place", "Type carries the hierarchy", "Decoration never lies"]}},
    {"type": "matrix", "title": "When to use Bauhaus", "quadrants": [
        {"heading": "Use it", "text": "Product launches, design talks, culture decks, poster-like covers."},
        {"heading": "Balance it", "text": "Data-heavy reviews: keep charts plain and let one slide shout."},
        {"heading": "Soften it", "text": "Sensitive topics: swap red for blue as the leading block."},
        {"heading": "Avoid it", "text": "Legal, medical and dense documentation work."}],
     "x_axis": "Expressiveness", "y_axis": "Formality"},
    {"type": "quote", "quote": "Architecture begins where two bricks are put together well.",
     "attribution": "Ludwig Mies van der Rohe"},
    {"type": "chart", "title": "Primary color usage", "chart": {"kind": "column", "unit": "%",
     "categories": ["Red", "Blue", "Yellow", "Black"], "series": [{"name": "Share", "values": [30, 28, 17, 25]}]},
     "takeaway": "Black and white hold the composition; primaries carry it (illustrative data)"},
    {"type": "table", "title": "Token sheet", "columns": ["Token", "Value", "Use"],
     "rows": [["background", "#F0F0F0", "Canvas"], ["primary-red", "#D02020", "Action"],
              ["primary-blue", "#1040C0", "Panels"], ["primary-yellow", "#F0C020", "Highlights"],
              ["foreground", "#121212", "Type & borders"]]},
    {"type": "funnel", "title": "Design review funnel", "stages": [
        {"label": "Ideas", "value": "40", "text": "Every concept starts on the wall"},
        {"label": "Compositions", "value": "12", "text": "Only constructed grids survive"},
        {"label": "Pages", "value": "4", "text": "The deck keeps what functions"}]},
    {"type": "quiz", "title": "Which shape is not primary?", "options": ["Circle", "Square", "Triangle", "Pentagon"],
     "answer": 3, "explanation": "The Bauhaus vocabulary is circle, square and triangle only."},
    {"type": "image", "title": "The workshop wall", "image": "", "side": "right",
     "bullets": [{"text": "Large shapes at 10-20% opacity sit behind content", "sub": []},
                 {"text": "Small solid marks anchor corners", "sub": []}]},
    {"type": "closing", "title": "Build the poster", "subtitle": "Form follows function - make every slide prove it",
     "contact": "slidesmith.local"},
]
