# SlideSmith — AI presentation builder

Chat with an AI and watch it design your deck live on a canvas, Google-Stitch style:
it plans the outline, writes **each slide in its own detailed pass**, renders the slide to an image,
**looks at it**, and fixes anything that's off. Upload your own PowerPoint template and the AI learns its
pages and builds the deck inside them.

## Run it

**Double-click `Start SlideSmith.bat`.** The first time it installs the required packages; then it starts the app
and opens http://127.0.0.1:8000 in your browser. Close the black window to stop SlideSmith. Clicking it again while
the app is running just opens the page. Tip: right-click the file → *Send to* → *Desktop (create shortcut)*.

**On your phone or tablet:** double-click `Start SlideSmith (phone access).bat` instead, then tap the phone icon in
SlideSmith on your PC and scan the QR code (phone and PC on the same Wi-Fi). If Windows asks, allow Python on
private networks. On a phone the app switches to a mobile layout: Chat and Slides tabs, a swipeable slide list,
a bottom-sheet editor, and tap/swipe presenting. Only use phone access on networks you trust: anyone on that
Wi-Fi could open SlideSmith and use your AI key.

Manual start, if you prefer:

```bash
pip install -r requirements.txt
```

```bash
python app.py
```

## Where the AI API is configured / called

| What | Where |
|---|---|
| Endpoint, key, model | `.env` in this folder (`AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`) — or the ⚙ Settings dialog in the app |
| The single place the API is called | [`server/ai_client.py`](server/ai_client.py) → `stream_chat()` sends `POST {AI_BASE_URL}/chat/completions` (streaming) |
| Model list | `GET {AI_BASE_URL}/models` (Settings → *Fetch models*) |

Any OpenAI-compatible endpoint works. Optional settings:

- `AI_REVIEW=1` — the AI reviews each rendered slide and fixes it (slower, better). `0` turns it off.
- `AI_REVIEW_MODEL` — model that looks at slide images; empty = auto-pick one with "vision" in its name (e.g. `auto/best-vision`).
- `AI_MODEL=demo` — offline demo mode (no endpoint needed).

## How a deck gets built

1. **Plan** — the outline appears on the canvas as queued slide cards (your template's real pages are previewed).
2. **Write** — every slide is written separately with the full outline, earlier slides and your documents as context.
3. **Look & fix** — the slide is rendered to PNG ([`server/raster.py`](server/raster.py)) with automatic checks
   (text overflow, leftover sample text, sparse content); the AI sees the image and either approves it or rewrites it.
   The same image is available at `GET /api/projects/{id}/slides/{slide_id}.png` for any other tool.

If the endpoint drops mid-build, finished slides are kept — just say **"continue"**.

## Your own template (.pptx / .potx)

Upload it from the home page or the theme picker. SlideSmith learns:

- every **sample page** (cover, contents, content page, closing page) with its text boxes, tables and logos;
- **instruction pages** (e.g. "Guideline for PPTs: heading 28pt Times New Roman…") — followed, never output;
- theme colors, fonts, brand colors from the decoration, and all slide layouts.

When building, the AI reuses those pages: the **cover stays exactly the same** (only `<placeholder>` fields you gave
details for are filled), the contents page list is updated, the content page is reused for text slides, and charts,
cards, timelines and tables are drawn *inside* your content page's frame. Export produces a real `.pptx` made from your file.

## Bauhaus

The **Bauhaus** built-in theme turns a deck into a 1920s constructivist poster: pure primaries
(red `#D02020`, blue `#1040C0`, yellow `#F0C020`) on off-white with stark black, white cards with thick
black borders and hard offset shadows, colour-blocked covers and section pages, and decorations built only
from circles, squares and triangles. Every slide type has its own Bauhaus layout — cover, section,
bullets, cards, stats, timeline, chevrons, two-column, matrix, quote, chart, table, funnel, quiz,
image and closing — so the exported `.pptx` is real editable PowerPoint shapes, not a picture.

Its typeface is **Outfit** (free, Google Fonts). The two files SlideSmith needs are bundled in
`server/fonts/`, so previews always render in Outfit. PowerPoint on your machine only uses Outfit if the
font is installed there — install it once from Google Fonts, or PowerPoint will substitute another
sans-serif in the exported file.

Two scripts keep the theme honest after edits: `python _bh_check.py` renders all 16 slide types and
checks geometry, text fit against the real font metrics, palette purity and the `.pptx` structure;
`python _bh_stress.py` repeats it with long text and full slides (6 cards, 8 bullets, 8×5 tables).

## Other features

- Select slides on the canvas (Shift-click for several) and ask for changes to just those.
- Attach PDFs, Word, PowerPoint or text files as source material.
- Present mode (double-click a slide), drag to pan, Ctrl+scroll to zoom.
- Built-in themes: Midnight, Clean Corporate, Editorial, Aurora, Sage, Bold Mono, Slate & Lime, Bauhaus (see below).
