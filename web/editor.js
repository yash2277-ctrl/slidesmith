// Slide editor drawer: edit content by hand (Pitch / Beautiful.ai style), switch smart layouts,
// pick photos and icons, and run one-click AI actions.
import { mountSlide } from "./slides.js";

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };

const TYPES = {
  title: "Title", section: "Section", bullets: "Bullets", image: "Photo + text", two_column: "Two columns", cards: "Cards",
  stats: "Big numbers", timeline: "Timeline", process: "Process", matrix: "2×2 matrix", funnel: "Funnel", chart: "Chart",
  table: "Table", quiz: "Quiz", quote: "Quote", closing: "Closing", template: "Template page",
  document: "Attached document", diagram: "Diagram",
};
const ITEM = {
  cards: ["cards", [["icon", "icon"], ["heading", "text", "Heading"], ["text", "area", "Text"]], 6],
  stats: ["stats", [["icon", "icon"], ["value", "text", "Value"], ["label", "text", "Label"], ["detail", "text", "Detail"]], 4],
  timeline: ["steps", [["icon", "icon"], ["label", "text", "Label (e.g. Q1)"], ["heading", "text", "Heading"], ["text", "area", "Text"]], 6],
  process: ["steps", [["icon", "icon"], ["heading", "text", "Heading"], ["text", "area", "Text"]], 5],
  matrix: ["quadrants", [["icon", "icon"], ["heading", "text", "Heading"], ["text", "area", "Text"]], 4],
  funnel: ["stages", [["label", "text", "Stage"], ["value", "text", "Value"], ["text", "text", "Description"]], 5],
  diagram: ["nodes", [["icon", "icon"], ["label", "text", "Box name"], ["text", "text", "Detail"]], 10],
};
const FIELDS = {
  title: [["kicker", "text", "Small line above the title"], ["title", "text", "Title"], ["subtitle", "area", "Subtitle"], ["image", "image", "Background photo"]],
  section: [["title", "text", "Title"], ["subtitle", "area", "Subtitle"], ["image", "image", "Background photo"]],
  closing: [["title", "text", "Title"], ["subtitle", "area", "Subtitle"], ["contact", "text", "Contact line"], ["image", "image", "Background photo"]],
  bullets: [["title", "text", "Title"], ["bullets", "bullets", "Bullets"]],
  image: [["title", "text", "Title"], ["image", "image", "Photo"], ["side", "select", "Photo side", ["right", "left"]], ["text", "area", "Intro text"], ["bullets", "bullets", "Bullets"]],
  two_column: [["title", "text", "Title"], ["left", "column", "Left column"], ["right", "column", "Right column"]],
  chart: [["title", "text", "Title"], ["chart", "chart", "Chart data"], ["takeaway", "area", "Key takeaway"]],
  table: [["title", "text", "Title"], ["table", "table", "Table (CSV, first row = header)"]],
  quiz: [["title", "text", "Question"], ["options", "lines", "Answers (one per line)"], ["answer", "answer", "Correct answer"], ["explanation", "area", "Explanation"]],
  quote: [["quote", "area", "Quote"], ["attribution", "text", "Who said it"]],
  template: [["fill", "fill", "Text on this template page"]],
  document: [["title", "text", "Title"], ["doc", "text", "Attached document (#D1)"], ["pages", "lines", "Pages to show (one per line)"], ["caption", "area", "Caption"]],
  diagram: [["title", "text", "Title"], ["caption", "area", "Caption"]],
};
const AI_ACTIONS = [
  ["Rewrite", "Rewrite this slide to be clearer and more compelling."],
  ["Shorten", "Shorten the text on this slide by about 40% while keeping the key points."],
  ["Expand", "Expand this slide with more specific detail, examples and numbers."],
  ["More visual", "Redesign this slide with a more visual layout (cards, process, timeline, matrix, stats or chart) and fitting icons."],
  ["Add photo", "Turn this slide into an 'image' slide with a fitting photo and the same key points."],
  ["Better title", "Give this slide a sharper, insight-driven title."],
  ["Speaker notes", "Write detailed speaker notes (5-7 sentences) for this slide."],
  ["Simplify", "Rewrite this slide for a non-expert audience in plain language."],
  ["Translate…", null],
];

let ctx = null; // {api, getState, onProject, sendChat, toast}
let current = null; // {pid, sid}
let saveTimer = null;

export function initEditor(context) { ctx = context; }

export function closeEditor() {
  document.querySelector("#editor")?.setAttribute("hidden", "");
  current = null;
}

export function editorOpenFor() { return current?.sid; }

export function openEditor(slideId, tab = "content") {
  const st = ctx.getState();
  const slide = st.slides.find((s) => s.id === slideId);
  if (!slide) return closeEditor();
  current = { pid: st.project.id, sid: slideId };
  const box = document.querySelector("#editor");
  box.removeAttribute("hidden");
  const idx = st.slides.indexOf(slide);
  box.innerHTML = `
    <div class="ed-head"><div><div class="ed-kicker">Slide ${idx + 1} · ${esc(TYPES[slide.spec.type] || slide.spec.type)}</div>
      <div class="ed-title">${esc(slide.spec.title || slide.spec.quote || "Untitled")}</div></div>
      <button class="icon-btn" data-ed="close" title="Close"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div>
    <div class="ed-tabs">${["content", "layout", "ai"].map((t) => `<button data-tab="${t}" class="${t === tab ? "on" : ""}">${{ content: "Content", layout: "Smart layouts", ai: "AI actions" }[t]}</button>`).join("")}</div>
    <div class="ed-body"></div>
    <div class="ed-foot">
      <button class="ghost-btn" data-ed="left" title="Move earlier">←</button><button class="ghost-btn" data-ed="right" title="Move later">→</button>
      <button class="ghost-btn" data-ed="dup">Duplicate</button><span class="spacer"></span><button class="ghost-btn danger" data-ed="del">Delete</button>
    </div>`;
  box.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => openEditor(slideId, b.dataset.tab)));
  box.querySelector('[data-ed="close"]').onclick = closeEditor;
  box.querySelector('[data-ed="left"]').onclick = () => move(idx - 1);
  box.querySelector('[data-ed="right"]').onclick = () => move(idx + 1);
  box.querySelector('[data-ed="dup"]').onclick = async () => ctx.onProject(await ctx.api(`/api/projects/${current.pid}/slides`, { json: { duplicate: slideId } }));
  box.querySelector('[data-ed="del"]').onclick = async () => {
    if (!confirm("Delete this slide?")) return;
    const sid = slideId;
    closeEditor();
    ctx.onProject(await ctx.api(`/api/projects/${st.project.id}/slides`, { json: { delete: [sid] } }));
  };
  const body = box.querySelector(".ed-body");
  if (tab === "content") renderForm(body, slide);
  if (tab === "layout") renderLayouts(body, slide);
  if (tab === "ai") renderAI(body, slide);
}

async function move(to) {
  if (!current) return;
  const st = ctx.getState();
  if (to < 0 || to >= st.slides.length) return;
  ctx.onProject(await ctx.api(`/api/projects/${current.pid}/slides/${current.sid}/move`, { json: { to } }));
  openEditor(current.sid);
}

/* ---------------------------------------------------------------- content form */
function renderForm(body, slide) {
  const spec = JSON.parse(JSON.stringify(slide.spec));
  const form = el("div", "ed-form");
  const typeRow = el("label", "ed-field", `<span>Layout</span>`);
  const sel = el("select");
  for (const [k, v] of Object.entries(TYPES)) if (k !== "template" || spec.type === "template") sel.add(new Option(v, k, false, k === spec.type));
  sel.onchange = () => { spec.type = sel.value; save(spec, true); };
  typeRow.appendChild(sel);
  form.appendChild(typeRow);

  const fields = FIELDS[spec.type] || (ITEM[spec.type] ? [["title", "text", "Title"]] : []);
  for (const f of fields) form.appendChild(field(spec, f));
  if (ITEM[spec.type]) form.appendChild(itemList(spec, ...ITEM[spec.type]));
  form.appendChild(field(spec, ["notes", "area", "Speaker notes", null, 5]));
  body.appendChild(form);
}

function changed(spec) {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => save(spec), 650);
}

async function save(spec, reopen = false) {
  if (!current) return;
  const { pid, sid } = current;
  try {
    const view = await ctx.api(`/api/projects/${pid}/slides/${sid}`, { method: "PUT", json: { spec } });
    ctx.onProject(view, sid);
    if (reopen) openEditor(sid);
  } catch (e) { ctx.toast(e.message, true); }
}

function field(spec, [key, kind, label, options, rows]) {
  const wrap = el("label", "ed-field", `<span>${esc(label)}</span>`);
  if (kind === "text" || kind === "area") {
    const input = kind === "area" ? el("textarea") : el("input");
    if (kind === "area") input.rows = rows || 2;
    input.value = spec[key] || "";
    input.oninput = () => { spec[key] = input.value; changed(spec); };
    wrap.appendChild(input);
  } else if (kind === "select") {
    const s = el("select");
    for (const o of options) s.add(new Option(o, o, false, (spec[key] || options[0]) === o));
    s.onchange = () => { spec[key] = s.value; changed(spec); };
    wrap.appendChild(s);
  } else if (kind === "bullets") {
    const t = el("textarea");
    t.rows = 7;
    t.placeholder = "One bullet per line. Start a line with \"- \" for a sub-point.";
    t.value = (spec.bullets || []).map((b) => [b.text, ...(b.sub || []).map((x) => "- " + x)].join("\n")).join("\n");
    t.oninput = () => {
      const out = [];
      for (const line of t.value.split("\n")) {
        if (!line.trim()) continue;
        if (/^\s*-\s+/.test(line) && out.length) out[out.length - 1].sub.push(line.replace(/^\s*-\s+/, ""));
        else out.push({ text: line.trim(), sub: [] });
      }
      spec.bullets = out;
      changed(spec);
    };
    wrap.appendChild(t);
  } else if (kind === "column") {
    const col = spec[key] || { heading: "", bullets: [] };
    const h = el("input");
    h.placeholder = "Heading";
    h.value = col.heading || "";
    const t = el("textarea");
    t.rows = 5;
    t.placeholder = "One point per line";
    t.value = (col.bullets || []).join("\n");
    const upd = () => { spec[key] = { heading: h.value, bullets: t.value.split("\n").filter((x) => x.trim()) }; changed(spec); };
    h.oninput = t.oninput = upd;
    wrap.append(h, t);
  } else if (kind === "lines") {
    const t = el("textarea");
    t.rows = 5;
    t.value = (spec[key] || []).join("\n");
    t.oninput = () => { spec[key] = t.value.split("\n").filter((x) => x.trim()); changed(spec); };
    wrap.appendChild(t);
  } else if (kind === "answer") {
    const s = el("select");
    (spec.options || []).forEach((o, i) => s.add(new Option(`${"ABCDE"[i]}) ${o}`, i, false, i === spec.answer)));
    s.onchange = () => { spec.answer = Number(s.value); changed(spec); };
    wrap.appendChild(s);
  } else if (kind === "image") {
    wrap.appendChild(imageField(spec));
  } else if (kind === "chart") {
    const ch = spec.chart || { kind: "column", categories: [], series: [] };
    const s = el("select");
    for (const k of ["column", "bar", "line", "pie", "doughnut"]) s.add(new Option(k, k, false, ch.kind === k));
    const unit = el("input");
    unit.placeholder = "Unit (%, $, ms…)";
    unit.value = ch.unit || "";
    const t = el("textarea");
    t.rows = 6;
    t.placeholder = "Category, Series 1, Series 2\nQ1, 10, 12\nQ2, 14, 15";
    t.value = [["Category", ...ch.series.map((x) => x.name)].join(", "), ...ch.categories.map((c, i) => [c, ...ch.series.map((x) => x.values[i] ?? "")].join(", "))].join("\n");
    const upd = () => {
      const rows = t.value.split("\n").map((r) => r.split(",").map((x) => x.trim())).filter((r) => r.length > 1 && r[0]);
      if (rows.length < 2) return;
      const names = rows[0].slice(1);
      spec.chart = { kind: s.value, unit: unit.value, categories: rows.slice(1).map((r) => r[0]),
        series: names.map((n, k) => ({ name: n || `Series ${k + 1}`, values: rows.slice(1).map((r) => parseFloat(String(r[k + 1]).replace(/[^0-9.-]/g, "")) || 0) })) };
      changed(spec);
    };
    s.onchange = unit.oninput = t.oninput = upd;
    const row = el("div", "ed-row");
    row.append(s, unit);
    wrap.append(row, t);
  } else if (kind === "table") {
    const t = el("textarea");
    t.rows = 7;
    t.value = [spec.columns || [], ...(spec.rows || [])].map((r) => r.join(", ")).join("\n");
    t.oninput = () => {
      const rows = t.value.split("\n").filter((r) => r.trim()).map((r) => r.split(",").map((x) => x.trim()));
      spec.columns = rows[0] || [];
      spec.rows = rows.slice(1);
      changed(spec);
    };
    wrap.appendChild(t);
  } else if (kind === "fill") {
    const fill = spec.fill || {};
    if (!Object.keys(fill).length) wrap.appendChild(el("div", "ed-hint", "This page is kept exactly as in your template. Ask the AI to change its text, or switch layout."));
    for (const [k, v] of Object.entries(fill)) {
      const t = el("textarea");
      t.rows = Array.isArray(v) ? Math.min(10, v.length + 1) : 2;
      t.value = Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : (x.level ? "- " : "") + x.text)).join("\n") : v;
      t.oninput = () => {
        fill[k] = Array.isArray(v) || t.value.includes("\n")
          ? t.value.split("\n").map((line) => (/^-\s+/.test(line) ? { text: line.replace(/^-\s+/, ""), level: 1 } : line))
          : t.value;
        spec.fill = fill;
        changed(spec);
      };
      const lab = el("div", "ed-hint", `Text box ${esc(k)}`);
      wrap.append(lab, t);
    }
  }
  return wrap;
}

function itemList(spec, key, defs, max) {
  const wrap = el("div", "ed-field");
  wrap.appendChild(el("span", "", key === "quadrants" ? "Quadrants" : "Items"));
  const items = spec[key] || (spec[key] = []);
  const list = el("div", "ed-items");
  const draw = () => {
    list.innerHTML = "";
    items.forEach((it, i) => {
      const card = el("div", "ed-item");
      const head = el("div", "ed-item-head", `<b>${i + 1}</b>`);
      if (key !== "quadrants") {
        const rm = el("button", "link-btn", "Remove");
        rm.type = "button";
        rm.onclick = () => { items.splice(i, 1); draw(); changed(spec); };
        head.appendChild(rm);
      }
      card.appendChild(head);
      for (const [k, kind, label] of defs) {
        if (kind === "icon") {
          const row = el("div", "ed-icon");
          const prev = el("img");
          const show = () => { prev.src = it.icon && it.icon.includes(":") ? `/media/icon/${it.icon}/6B7280.png` : "data:image/gif;base64,R0lGODlhAQABAAAAACw="; };
          show();
          const inp = el("input");
          inp.placeholder = "Icon keyword (e.g. rocket)";
          inp.value = it.icon && it.icon.includes(":") ? it.icon.split(":")[1].replace(/-/g, " ") : it.icon || "";
          inp.onchange = () => { it.icon = inp.value.trim(); changed(spec); };
          row.append(prev, inp);
          card.appendChild(row);
          continue;
        }
        const input = kind === "area" ? el("textarea") : el("input");
        if (kind === "area") input.rows = 2;
        input.placeholder = label;
        input.value = it[k] || "";
        input.oninput = () => { it[k] = input.value; changed(spec); };
        card.appendChild(input);
      }
      list.appendChild(card);
    });
    if (items.length < max) {
      const add = el("button", "ghost-btn", "+ Add item");
      add.type = "button";
      add.onclick = () => { items.push(Object.fromEntries(defs.map(([k]) => [k, ""]))); draw(); };
      list.appendChild(add);
    }
  };
  draw();
  wrap.appendChild(list);
  return wrap;
}

function imageField(spec) {
  const box = el("div", "ed-image");
  const img = spec.image && typeof spec.image === "object" && spec.image.src ? spec.image : null;
  box.innerHTML = img ? `<img src="${esc(img.src)}"><div class="ed-hint">${esc(img.credit || "Your image")}</div>` : `<div class="ed-hint">No photo yet</div>`;
  const row = el("div", "ed-row");
  const pick = el("button", "ghost-btn", img ? "Change photo" : "Add photo");
  pick.type = "button";
  pick.onclick = () => openPicker(typeof spec.image === "string" ? spec.image : spec.image?.query || spec.title || "", (chosen) => { spec.image = chosen; save(spec, true); });
  row.appendChild(pick);
  if (img) {
    const rm = el("button", "ghost-btn", "Remove");
    rm.type = "button";
    rm.onclick = () => { delete spec.image; save(spec, true); };
    row.appendChild(rm);
  }
  box.appendChild(row);
  return box;
}

/* ---------------------------------------------------------------- photo picker (Openverse search + upload) */
export function openPicker(query, onPick) {
  const modal = document.querySelector("#pickerModal");
  modal.hidden = false;
  const input = modal.querySelector("#pickQuery");
  const grid = modal.querySelector("#pickGrid");
  input.value = query || "";
  const search = async () => {
    const q = input.value.trim();
    if (!q) return;
    grid.innerHTML = `<div class="ed-hint">Searching free Creative Commons photos…</div>`;
    const { results } = await ctx.api(`/api/media/photos?q=${encodeURIComponent(q)}`);
    grid.innerHTML = results.length ? "" : `<div class="ed-hint">No photos found - try other words.</div>`;
    for (const r of results) {
      const b = el("button", "pick");
      b.type = "button";
      b.innerHTML = `<img src="${esc(r.thumb)}" loading="lazy"><span>${esc(r.credit)}</span>`;
      b.onclick = async () => {
        b.classList.add("busy");
        try {
          const got = await ctx.api("/api/media/photos/fetch", { json: r });
          modal.hidden = true;
          onPick({ ...got, query: q });
        } catch (e) { ctx.toast(e.message, true); b.classList.remove("busy"); }
      };
      grid.appendChild(b);
    }
  };
  modal.querySelector("#pickGo").onclick = search;
  input.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); search(); } };
  const up = modal.querySelector("#pickUpload");
  up.value = "";
  up.onchange = async () => {
    const f = up.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const got = await ctx.api("/api/media/upload", { method: "POST", body: fd });
      modal.hidden = true;
      onPick(got);
    } catch (e) { ctx.toast(e.message, true); }
  };
  if (query) search();
  input.focus();
}

/* ---------------------------------------------------------------- smart layouts */
async function renderLayouts(body, slide) {
  body.innerHTML = `<div class="ed-hint">Same content, different layout - click to apply instantly. (No AI needed.)</div>`;
  const { alternatives } = await ctx.api(`/api/projects/${current.pid}/slides/${slide.id}/alternatives`);
  if (!alternatives.length) {
    body.appendChild(el("div", "ed-hint", "This slide type has a fixed layout. Use AI actions → More visual to redesign it."));
    return;
  }
  const grid = el("div", "ed-layouts");
  const theme = ctx.getState().theme;
  for (const alt of alternatives) {
    const b = el("button", "ed-layout");
    b.type = "button";
    const th = el("div", "thumb");
    b.appendChild(th);
    b.appendChild(el("span", "", esc(TYPES[alt.type] || alt.type)));
    b.onclick = async () => {
      const view = await ctx.api(`/api/projects/${current.pid}/slides/${slide.id}/remix`, { json: { type: alt.type } });
      ctx.onProject(view, slide.id);
      openEditor(slide.id, "layout");
    };
    grid.appendChild(b);
    requestAnimationFrame(() => mountSlide(th, alt.layout, theme, th.clientWidth || 300));
  }
  body.appendChild(grid);
}

/* ---------------------------------------------------------------- AI actions */
function renderAI(body, slide) {
  body.appendChild(el("div", "ed-hint", "One click - the AI edits just this slide, then reviews how it looks."));
  const grid = el("div", "ed-actions");
  for (const [label, prompt] of AI_ACTIONS) {
    const b = el("button", "ghost-btn", esc(label));
    b.type = "button";
    b.onclick = () => {
      let p = prompt;
      if (!p) {
        const lang = window.prompt("Translate this slide into which language?", "Hindi");
        if (!lang) return;
        p = `Translate this slide into ${lang}.`;
      }
      ctx.sendChat(p, [slide.id]);
    };
    grid.appendChild(b);
  }
  body.appendChild(grid);
  const custom = el("div", "ed-field", `<span>Or describe a change</span>`);
  const t = el("textarea");
  t.rows = 3;
  t.placeholder = "e.g. add a comparison with last year";
  const go = el("button", "primary-btn", "Apply with AI");
  go.type = "button";
  go.onclick = () => t.value.trim() && ctx.sendChat(t.value.trim(), [slide.id]);
  custom.append(t, go);
  body.appendChild(custom);
}
