import { mountSlide, renderSlide, PX } from "./slides.js";
import { initEditor, openEditor, closeEditor, editorOpenFor, openPicker } from "./editor.js";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) { init.body = JSON.stringify(opts.json); init.headers = { "Content-Type": "application/json" }; init.method = opts.method || "POST"; }
  const r = await fetch(path, init);
  if (!r.ok) { const e = await r.json().catch(() => ({ detail: r.statusText })); throw new Error(e.detail || r.statusText); }
  return r.json();
}

const ICON = {
  check: '<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>',
  minus: '<svg viewBox="0 0 24 24"><path d="M6 12h12"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  alert: '<svg viewBox="0 0 24 24"><path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>',
  edit: '<svg viewBox="0 0 24 24"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  copy: '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2m1 0-1 14H8L7 6"/></svg>',
  play: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
  file: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>',
  slide: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="13" rx="2"/></svg>',
  stop: '<svg viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor"/></svg>',
  send: '<svg viewBox="0 0 24 24"><path d="M12 19V5m0 0-6 6m6-6 6 6"/></svg>',
  upload: '<svg viewBox="0 0 24 24"><path d="M12 15V3m0 0-4 4m4-4 4 4M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/></svg>',
};

const EXAMPLES = [
  "Pitch deck for an AI tutoring app for high-school students",
  "Quarterly business review for a B2B SaaS company",
  "Lecture: how vaccines train the immune system",
  "Marketing plan for launching a new coffee brand",
  "Onboarding deck for new engineers joining our team",
];
const SUGGESTIONS = ["Make it more visual", "Tighten all the wording", "Add a slide comparing alternatives", "Add richer speaker notes", "Add a timeline slide"];

const CARD_W = 480, CARD_H = 270, HEAD = 34, GAP_X = 56, GAP_Y = 64;
const PHONE = matchMedia("(max-width: 760px)");
const isPhone = () => PHONE.matches;

function setTab(tab) {
  const ws = $("#workspace");
  ws.dataset.mtab = tab;
  $$("#mtabs [data-mtab]").forEach((b) => b.classList.toggle("on", b.dataset.mtab === tab));
  if (tab === "chat") { $("#mtabs .dot").hidden = true; const log = $("#chatLog"); log.scrollTop = log.scrollHeight; }
  if (tab === "slides") requestAnimationFrame(() => fitBoard(false));
}

const state = {
  status: null, themes: [], themeById: {}, homeTheme: "midnight", homeFiles: [],
  project: null, theme: null, slides: [], selected: new Set(), files: [],
  running: false, follow: true, layout: "grid", zoom: 1, pan: { x: 60, y: 60 },
  cards: new Map(), live: null, themeModalFor: "project", present: null,
};

/* ================================================================ toasts */
function toast(msg, err = false) {
  const t = el("div", "toast" + (err ? " err" : ""), esc(msg));
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), err ? 7000 : 3500);
}

/* ================================================================ status */
async function loadStatus() {
  state.status = await api("/api/status");
  paintStatus("checking");
  if (state.status.demo) return paintStatus("demo");
  try {
    const r = await api("/api/models");
    paintStatus(r.error ? "bad" : "ok", r.error, r.models);
  } catch { paintStatus("bad"); }
}
function paintStatus(kind, error, models) {
  const s = state.status;
  const text = { checking: "Checking connection…", demo: "Demo mode — add your AI endpoint", bad: "AI endpoint unreachable", ok: `Connected · ${s.model || (models && models[0]) || "auto"}` }[kind];
  for (const p of [$("#homeStatus"), $("#wsStatus")]) {
    p.className = "pill status-pill " + (kind === "checking" ? "" : kind);
    p.textContent = text;
    p.title = error || "AI connection settings";
  }
}

/* ================================================================ themes */
async function loadThemes() {
  const { themes } = await api("/api/themes");
  state.themes = themes;
  state.themeById = Object.fromEntries(themes.map((t) => [t.theme_id, t]));
  renderThemeStrip();
  paintThemeChip($("#homeTheme"), state.homeTheme);
}
function themeOf(id) { return state.themeById[id] || state.themeById.midnight || state.themes[0]; }
function paintThemeChip(btn, id) {
  const t = themeOf(id);
  if (!t) return;
  $(".swatch", btn).style.background = `linear-gradient(135deg, ${t.colors.bg} 50%, ${t.colors.accent} 50%)`;
  $(".label", btn).textContent = t.name;
}
function themeThumb(t, i = 0, width = 214) {
  const host = el("div", "thumb");
  mountSlide(host, t.previews[i], t, width);
  return host;
}
function renderThemeStrip() {
  const strip = $("#themeStrip");
  strip.innerHTML = "";
  const up = el("button", "theme-tile upload-tile", `<div class="thumb"><div>${ICON.upload}<span>Upload .pptx template</span></div></div><div class="name">Your template</div>`);
  up.onclick = () => $("#templateInput").click();
  strip.appendChild(up);
  for (const t of [...state.themes].sort((a, b) => (b.kind === "custom") - (a.kind === "custom"))) {
    const b = el("button", "theme-tile" + (t.theme_id === state.homeTheme ? " active" : ""));
    b.appendChild(themeThumb(t));
    b.appendChild(el("div", "name", `${esc(t.name)}${t.kind === "custom" ? '<span class="badge">Custom</span>' : ""}`));
    b.onclick = () => { state.homeTheme = t.theme_id; paintThemeChip($("#homeTheme"), t.theme_id); renderThemeStrip(); };
    strip.appendChild(b);
  }
}

function openThemeModal(forWhat) {
  state.themeModalFor = forWhat;
  renderThemeGrid();
  $("#inspector").hidden = true;
  $("#themeModal").hidden = false;
}
function renderThemeGrid() {
  const grid = $("#themeGrid");
  grid.innerHTML = "";
  const current = state.themeModalFor === "home" ? state.homeTheme : state.project?.theme_id;
  const brand = el("div", "theme-option brand-tile");
  brand.innerHTML = `<div class="drop"><div><b>Create a brand kit</b><br>Your colors, fonts &amp; logo — or import them from your website</div></div><div class="name">Brand kit</div>`;
  $(".drop", brand).onclick = () => openBrand();
  grid.appendChild(brand);
  const drop = el("div", "theme-option");
  drop.innerHTML = `<div class="drop">${ICON.upload}<div><b>Upload your template</b><br>Drop a .pptx / .potx here or click</div></div><div class="name">Your own design</div>`;
  const zone = $(".drop", drop);
  zone.onclick = () => $("#templateInput").click();
  zone.ondragover = (e) => { e.preventDefault(); zone.classList.add("over"); };
  zone.ondragleave = () => zone.classList.remove("over");
  zone.ondrop = (e) => { e.preventDefault(); zone.classList.remove("over"); if (e.dataTransfer.files[0]) uploadTemplate(e.dataTransfer.files[0]); };
  grid.appendChild(drop);
  for (const t of [...state.themes].sort((a, b) => (b.kind === "custom") - (a.kind === "custom"))) {
    const b = el("div", "theme-option" + (t.theme_id === current ? " active" : ""));
    const pair = el("div", "pair");
    const tw = isPhone() ? Math.floor((innerWidth - 56) / 2) : 232;
    pair.appendChild(themeThumb(t, 0, tw));
    pair.appendChild(themeThumb(t, 1, tw));
    b.appendChild(pair);
    b.appendChild(el("div", "name", `${esc(t.name)}${t.kind === "custom" ? '<span class="badge">Custom</span>' : ""}`));
    if (t.brand === true) {
      const del = el("button", "icon-btn del", ICON.trash);
      del.title = "Delete brand kit";
      del.onclick = async (e) => { e.stopPropagation(); if (!confirm(`Delete brand kit "${t.name}"?`)) return; await api(`/api/brands/${t.id}`, { method: "DELETE" }); await loadThemes(); renderThemeGrid(); };
      b.appendChild(del);
    }
    if (t.kind === "custom") {
      const del = el("button", "icon-btn del", ICON.trash);
      del.title = "Delete template";
      del.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm(`Delete template "${t.name}"?`)) return;
        await api(`/api/templates/${t.id}`, { method: "DELETE" });
        await loadThemes();
        renderThemeGrid();
      };
      b.appendChild(del);
    }
    pair.style.cursor = "pointer";
    pair.onclick = () => chooseTheme(t.theme_id);
    if (t.kind === "custom") b.querySelector(".name").onclick = () => showInspector(t);
    grid.appendChild(b);
  }
}
async function chooseTheme(themeId) {
  if (state.themeModalFor === "home") {
    state.homeTheme = themeId;
    paintThemeChip($("#homeTheme"), themeId);
    renderThemeStrip();
  } else if (state.project) {
    const view = await api(`/api/projects/${state.project.id}`, { method: "PATCH", json: { theme_id: themeId } });
    applyProject(view, true);
    toast(`Applied “${themeOf(themeId).name}” to every slide`);
  }
  $("#themeModal").hidden = true;
}

function showInspector(t, steps) {
  const box = $("#inspector");
  box.hidden = false;
  const roles = { title: "Title slides", section: "Section dividers", bullets: "Bullet slides", two_column: "Two columns", visual: "Charts, cards, stats…", blank: "Quotes" };
  const nameOf = (key) => (t.layouts || []).find((l) => l.key === key)?.name || "—";
  const colors = Object.values(t.scheme || {}).slice(0, 12);
  box.innerHTML = `
    <h4>${esc(t.name)} <span class="badge">Custom</span></h4>
    ${steps ? `<div class="analysis">${steps}</div>` : ""}
    <div class="muted" style="font-size:13px">Theme colors</div>
    <div class="swatches">${colors.map((c) => `<span style="background:${c}" title="${c}"></span>`).join("")}</div>
    <div class="muted" style="font-size:13px;margin-bottom:6px">Fonts: <b style="color:var(--text)">${esc(t.fonts.heading)}</b> / <b style="color:var(--text)">${esc(t.fonts.body)}</b> · ${(t.layouts || []).length} layouts · ${t.slide_w.toFixed(2)}×${t.slide_h.toFixed(2)} in</div>
    ${(t.pages || []).length ? `<div class="muted" style="font-size:13px;margin-top:4px">What the AI learned from your ${t.pages.length} template pages — it reuses them and keeps your design:</div><div class="pages" id="learnedPages"></div>` :
      `<div class="layout-map">${Object.entries(roles).map(([k, v]) => `<div>${v} → <b>${esc(nameOf(t.mapping?.[k]))}</b></div>`).join("")}</div>`}
    <div class="form-actions" style="margin-top:16px"><button class="primary-btn" id="useTpl">Use this template</button></div>`;
  $("#useTpl").onclick = () => chooseTheme(t.theme_id);
  const ROLE = { cover: "Cover — kept the same", toc: "Contents — list updated", content: "Content page — reused for slides", closing: "Closing — kept", guide: "Instructions — followed, not shown", section: "Section page", other: "Page" };
  for (const pg of t.pages || []) {
    const cell = el("div", "pg" + (pg.role === "guide" ? " guide" : ""));
    const th = el("div", "thumb");
    cell.appendChild(th);
    cell.appendChild(el("div", "cap", `<b>${esc(pg.id)}</b> · ${esc(ROLE[pg.role] || pg.role)}`));
    $("#learnedPages").appendChild(cell);
    requestAnimationFrame(() => mountSlide(th, pg.layout, t, th.clientWidth || 170));
  }
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function uploadTemplate(file) {
  if (!/\.(pptx|potx)$/i.test(file.name)) return toast("Please choose a .pptx or .potx file", true);
  if ($("#themeModal").hidden) openThemeModal(state.project && !$("#workspace").hidden ? "project" : "home");
  const box = $("#inspector");
  box.hidden = false;
  const labels = ["Uploading template", "Reading slide masters & layouts", "Extracting theme colors & fonts", "Mapping layouts to slide types", "Ready"];
  const paint = (n, err) => {
    box.innerHTML = `<h4>${esc(file.name)}</h4><div class="analysis">${labels.map((l, i) =>
      `<div class="act ${i < n ? "done" : i === n ? (err ? "error" : "running") : ""}" style="${i > n ? "opacity:.35" : ""}"><span class="ico">${i < n ? ICON.check : i === n ? (err ? ICON.x : '<span class="spinner"></span>') : ""}</span><span class="label">${l}</span></div>`).join("")}</div>${err ? `<p class="form-msg err">${esc(err)}</p>` : ""}`;
  };
  paint(0);
  const fd = new FormData();
  fd.append("file", file);
  let card;
  try {
    const req = api("/api/templates", { method: "POST", body: fd });
    setTimeout(() => paint(1), 350);
    card = await req;
  } catch (e) { return paint(1, e.message); }
  for (const n of [2, 3, 4]) { paint(n); await new Promise((r) => setTimeout(r, 380)); }
  await loadThemes();
  renderThemeGrid();
  const t = themeOf(card.theme_id);
  showInspector(t, labels.map((l, i) => `<div class="act done"><span class="ico">${ICON.check}</span><span class="label">${i === 3 ? `Mapped ${(t.layouts || []).length} layouts to slide types` : l}</span></div>`).join(""));
}

/* ================================================================ home */
async function loadRecent() {
  const { projects } = await api("/api/projects");
  const grid = $("#recentGrid");
  grid.innerHTML = "";
  $("#recentSection").hidden = !projects.length;
  for (const p of projects) {
    const card = el("button", "recent-card");
    const thumb = el("div", "thumb");
    if (p.cover) mountSlide(thumb, p.cover, themeOf(p.theme_id), 260);
    card.appendChild(thumb);
    const ago = timeAgo(p.updated);
    card.appendChild(el("div", "meta", `<span>${esc(p.name)}</span><span>${p.slide_count} slides · ${ago}</span>`));
    const del = el("span", "icon-btn del", ICON.trash);
    del.title = "Delete deck";
    del.onclick = async (e) => { e.stopPropagation(); if (confirm(`Delete “${p.name}”?`)) { await api(`/api/projects/${p.id}`, { method: "DELETE" }); loadRecent(); } };
    card.appendChild(del);
    card.onclick = () => openProject(p.id);
    grid.appendChild(card);
    requestAnimationFrame(() => { if (p.cover) mountSlide(thumb, p.cover, themeOf(p.theme_id), thumb.clientWidth || 260); });
  }
}
function timeAgo(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
function renderFileChips(host, files, onRemove) {
  host.innerHTML = "";
  files.forEach((f, i) => {
    const chip = el("span", "tag", `${ICON.file}${esc(f.name)}`);
    const x = el("button", "", ICON.x);
    x.type = "button";
    x.onclick = () => onRemove(i);
    chip.appendChild(x);
    host.appendChild(chip);
  });
}
function showHome() {
  $("#workspace").hidden = true;
  $("#home").hidden = false;
  state.project = null;
  history.replaceState(null, "", "/");
  loadRecent();
  renderThemeStrip();
}

/* ================================================================ workspace */
async function openProject(id, firstMessage, files) {
  const view = await api(`/api/projects/${id}`);
  $("#home").hidden = true;
  $("#workspace").hidden = false;
  history.replaceState(null, "", `/?p=${id}`);
  state.selected.clear();
  state.files = files || [];
  renderFileChips($("#ctxChips"), state.files, () => {});
  state.cards.forEach((c) => c.remove());
  state.cards.clear();
  applyProject(view, true);
  renderChat();
  setTab(view.slides.length && !firstMessage ? "slides" : "chat");
  fitBoard(false);
  if (firstMessage) send(firstMessage);
}

function applyProject(view, full) {
  state.project = view;
  state.theme = view.theme;
  state.slides = view.slides;
  $("#projectName").value = view.name;
  paintThemeChip($("#wsTheme"), view.theme_id);
  const valid = new Set(view.slides.map((s) => s.id));
  for (const id of [...state.selected]) if (!valid.has(id)) state.selected.delete(id);
  if (full) state.cards.forEach((c) => (c.dataset.sig = ""));
  renderBoard();
  renderCtxChips();
  $("#undoBtn").disabled = !view.can_undo;
  $$("#transSeg button").forEach((b) => b.classList.toggle("on", b.dataset.trans === ((view.settings || {}).transition || "fade")));
  $("#buildsChk").checked = (view.settings || {}).builds !== false;
}

/* ---------------- chat ---------------- */
function renderChat() {
  const log = $("#chatLog");
  log.innerHTML = "";
  if (!state.project.chat.length) {
    log.appendChild(el("div", "msg ai", `<div class="avatar"><span class="spark"></span></div><div class="body"><p class="ai-text">Hi! Tell me what your presentation is about — audience, goal, number of slides — and I'll design it live on the canvas. You can attach documents to build from, and pick or upload a template with the button at the top.</p></div>`));
  }
  for (const m of state.project.chat) {
    if (m.role === "user") log.appendChild(userMsg(m.text, m.selected || [], m.attachments || []));
    else {
      const live = assistantMsg();
      for (const it of m.items || []) it.kind === "text" ? live.setText(it.id, it.text) : live.activity(it);
      live.finish();
      log.appendChild(live.node);
    }
  }
  renderSuggestions();
  log.scrollTop = log.scrollHeight;
}
function userMsg(text, selected, attachments) {
  const n = el("div", "msg user");
  const tags = el("div", "tags");
  const idx = (id) => state.slides.findIndex((s) => s.id === id);
  for (const id of selected) if (idx(id) >= 0) tags.appendChild(el("span", "tag", `${ICON.slide}Slide ${idx(id) + 1}`));
  for (const a of attachments) tags.appendChild(el("span", "tag", `${ICON.file}${esc(a)}`));
  if (tags.children.length) n.appendChild(tags);
  n.appendChild(el("div", "bubble", esc(text)));
  return n;
}
function assistantMsg() {
  const node = el("div", "msg ai", `<div class="avatar"><span class="spark"></span></div><div class="body"></div>`);
  const body = $(".body", node);
  const nodes = new Map();
  let timeline = null;
  const ensureTimeline = () => { if (!timeline || timeline !== body.lastElementChild) { timeline = el("div", "timeline"); body.appendChild(timeline); } return timeline; };
  const api_ = {
    node,
    setText(id, text) {
      let p = nodes.get(id);
      if (!p) { p = el("p", "ai-text"); body.appendChild(p); nodes.set(id, p); timeline = null; }
      p.textContent = text;
    },
    appendText(id, delta) {
      let p = nodes.get(id);
      if (!p) { p = el("p", "ai-text"); body.appendChild(p); nodes.set(id, p); timeline = null; }
      p.textContent += delta;
    },
    activity(it) {
      let row = nodes.get(it.id);
      if (!row) { row = el("div", "act"); ensureTimeline().appendChild(row); nodes.set(it.id, row); }
      row.className = `act ${it.status}${it.slide_id ? " clickable" : ""}`;
      const ico = it.status === "running" ? '<span class="spinner"></span>' : it.status === "error" ? ICON.alert : it.status === "stopped" ? ICON.minus : ICON.check;
      const open = row.querySelector(".detail")?.dataset.open === "1";
      row.innerHTML = `<span class="ico">${ico}</span><span class="label">${esc(it.label || "…")}${it.detail ? `<span class="detail" data-open="${open ? 1 : 0}" ${open || it.status === "running" ? "" : "hidden"}>${esc(it.detail)}</span>` : ""}</span>`;
      if (it.type === "think") row.onclick = () => { const d = row.querySelector(".detail"); if (d) { d.hidden = !d.hidden; d.dataset.open = d.hidden ? "0" : "1"; } };
      if (it.slide_id) row.onclick = () => { selectOnly(it.slide_id); focusCard(it.slide_id, true); };
    },
    finish() { node.classList.remove("live"); },
  };
  return api_;
}
function renderSuggestions() {
  const box = $("#suggestions");
  box.innerHTML = "";
  if (state.running || !state.slides.length) return;
  for (const s of SUGGESTIONS) {
    const b = el("button", "", esc(s));
    b.onclick = () => { $("#prompt").value = s; $("#prompt").focus(); autosize(); };
    box.appendChild(b);
  }
}
function renderCtxChips() {
  const host = $("#ctxChips");
  host.innerHTML = "";
  const idx = (id) => state.slides.findIndex((s) => s.id === id);
  for (const id of [...state.selected].sort((a, b) => idx(a) - idx(b))) {
    const s = state.slides[idx(id)];
    const chip = el("span", "tag", `${ICON.slide}Slide ${idx(id) + 1} · ${esc((s?.spec.title || s?.spec.quote || "").slice(0, 26))}`);
    const x = el("button", "", ICON.x);
    x.type = "button";
    x.onclick = () => { state.selected.delete(id); paintSelection(); };
    chip.appendChild(x);
    host.appendChild(chip);
  }
  state.files.forEach((f, i) => {
    const chip = el("span", "tag", `${ICON.file}${esc(f.name)}`);
    const x = el("button", "", ICON.x);
    x.type = "button";
    x.onclick = () => { state.files.splice(i, 1); renderCtxChips(); };
    chip.appendChild(x);
    host.appendChild(chip);
  });
  $("#prompt").placeholder = state.selected.size ? `What should change on ${state.selected.size === 1 ? "this slide" : "these slides"}?` : state.slides.length ? "Describe a change, or select slides on the canvas…" : "Describe the presentation you want…";
}
function setRunning(on) {
  state.running = on;
  const btn = $("#sendBtn");
  btn.classList.toggle("stop", on);
  btn.innerHTML = on ? ICON.stop : ICON.send;
  btn.title = on ? "Stop" : "Send";
  $("#buildPill").hidden = !on;
  if (on) $("#buildText").textContent = "Thinking…";
  renderSuggestions();
}

async function send(text) {
  text = (text || "").trim();
  if (!text || state.running || !state.project) return;
  const pid = state.project.id;
  const fd = new FormData();
  fd.append("text", text);
  fd.append("selected", JSON.stringify([...state.selected]));
  for (const f of state.files) fd.append("files", f);
  const log = $("#chatLog");
  if (!state.project.chat.length) log.innerHTML = "";
  log.appendChild(userMsg(text, [...state.selected], state.files.map((f) => f.name)));
  state.project.chat.push({ role: "user", text });
  state.files = [];
  $("#prompt").value = "";
  autosize();
  renderCtxChips();
  const live = assistantMsg();
  live.node.classList.add("live");
  log.appendChild(live.node);
  log.scrollTop = log.scrollHeight;
  state.live = live;
  setRunning(true);
  try {
    const res = await fetch(`/api/projects/${pid}/chat`, { method: "POST", body: fd });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || res.statusText); }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i);
        buf = buf.slice(i + 2);
        for (const line of chunk.split("\n")) if (line.startsWith("data: ")) handleEvent(JSON.parse(line.slice(6)), live);
      }
    }
  } catch (e) {
    toast(e.message, true);
    live.activity({ id: "err" + Date.now(), status: "error", label: e.message });
  } finally {
    live.finish();
    setRunning(false);
    state.live = null;
  }
}

function handleEvent(ev, live) {
  const log = $("#chatLog");
  const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
  switch (ev.type) {
    case "text":
      live.appendText(ev.id, ev.delta);
      if (isPhone() && $("#workspace").dataset.mtab === "slides") $("#mtabs .dot").hidden = false;
      break;
    case "activity":
      live.activity(ev.item);
      if (ev.item.status === "running" && ev.item.label) $("#buildText").textContent = ev.item.label + progressSuffix();
      if (ev.item.type === "plan" && ev.item.status === "done" && state.follow) fitBoard(true);
      break;
    case "slide":
      upsertSlide(ev.slide);
      if (isPhone() && $("#workspace").dataset.mtab !== "slides" && ev.slide.status !== "done") setTab("slides");
      break;
    case "order": reorder(ev.order, ev.name); break;
    case "project": applyProject(ev.project, true); break;
    case "error": toast(ev.message, true); break;
    case "done":
      applyProject(ev.project, false);
      state.project.chat = ev.project.chat;
      if (editorOpenFor()) openEditor(editorOpenFor());
      if (state.follow && state.slides.length) setTimeout(() => fitBoard(true), 400);
      break;
  }
  if (atBottom) log.scrollTop = log.scrollHeight;
}
function progressSuffix() {
  const total = state.slides.length;
  const done = state.slides.filter((s) => s.status === "done").length;
  return total ? `  ·  ${done}/${total}` : "";
}

/* ---------------- canvas ---------------- */
function upsertSlide(view) {
  const i = state.slides.findIndex((s) => s.id === view.id);
  const wasGenerating = i >= 0 && state.slides[i].status === "generating";
  if (i >= 0) state.slides[i] = view; else state.slides.push(view);
  state.slides.forEach((s, k) => (s.index = k));
  renderBoard();
  if (view.status === "generating" && state.follow && !wasGenerating) followCard(view.id);
}
function reorder(order, name) {
  const by = new Map(state.slides.map((s) => [s.id, s]));
  state.slides = order.filter((id) => by.has(id)).map((id) => by.get(id));
  state.slides.forEach((s, k) => (s.index = k));
  if (name && state.project) { state.project.name = name; $("#projectName").value = name; }
  renderBoard();
}
// Stitch-style camera: zoom in on the slide the AI is designing right now.
function followCard(id) {
  const i = state.slides.findIndex((s) => s.id === id);
  if (i < 0) return;
  if (isPhone()) return focusCard(id, true);
  const c = $("#canvas").getBoundingClientRect();
  const comfy = Math.min(1, (c.width - 100) / (CARD_W * 1.3), (c.height - 100) / ((CARD_H + HEAD) * 1.4));
  if (Math.abs(state.zoom - comfy) > 0.02) state.zoom = Math.max(0.2, comfy);
  focusCard(id, true);
}
function cardPos(i) {
  if (isPhone()) return { x: 0, y: i * (CARD_H + HEAD + 26) };
  if (state.layout === "row") return { x: i * (CARD_W + GAP_X), y: 0 };
  const cols = 3;
  return { x: (i % cols) * (CARD_W + GAP_X), y: Math.floor(i / cols) * (CARD_H + HEAD + GAP_Y) };
}
function renderBoard() {
  const board = $("#board");
  $("#canvasEmpty").hidden = state.slides.length > 0;
  const alive = new Set();
  state.slides.forEach((s, i) => {
    alive.add(s.id);
    let card = state.cards.get(s.id);
    if (!card) { card = makeCard(s.id); state.cards.set(s.id, card); board.appendChild(card); }
    const pos = cardPos(i);
    card.style.left = pos.x + "px";
    card.style.top = pos.y + "px";
    const sig = s.status + JSON.stringify(s.layout) + i + state.theme?.id;
    if (card.dataset.sig !== sig) { card.dataset.sig = sig; paintCard(card, s, i); }
  });
  for (const [id, card] of state.cards) if (!alive.has(id)) { card.remove(); state.cards.delete(id); }
  paintSelection();
  const count = $("#mtabCount");
  if (count) count.textContent = state.slides.length || "";
  if (isPhone()) sizeSpacer();
}
function sizeSpacer() {
  let sp = $("#boardSpacer");
  if (!sp) { sp = el("div"); sp.id = "boardSpacer"; sp.style.cssText = "position:absolute;left:0;top:0;width:1px;pointer-events:none"; $("#canvas").appendChild(sp); }
  sp.style.height = isPhone() ? (state.slides.length * (CARD_H + HEAD + 26) * state.zoom + 90) + "px" : "0px";
}
function makeCard(id) {
  const card = el("div", "card");
  card.dataset.id = id;
  card.innerHTML = `<div class="card-head"><span class="num"></span><span class="ttl"></span><span class="state"></span></div><div class="frame"><div class="host"></div><div class="shimmer"></div></div>
    <div class="card-tools"><button data-t="edit" title="Edit with AI">${ICON.edit}</button><button data-t="dup" title="Duplicate">${ICON.copy}</button><button data-t="play" title="Present from here">${ICON.play}</button><button data-t="del" title="Delete">${ICON.trash}</button></div>`;
  const frame = $(".frame", card);
  frame.addEventListener("click", (e) => {
    if (e.shiftKey || e.ctrlKey || e.metaKey) { state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id); paintSelection(); }
    else { selectOnly(id); if (!state.running) openEditor(id); }
  });
  frame.addEventListener("dblclick", () => startPresent(state.slides.findIndex((s) => s.id === id)));
  $(".card-tools", card).addEventListener("click", async (e) => {
    const t = e.target.closest("button")?.dataset.t;
    if (!t) return;
    if (t === "edit") { selectOnly(id); $("#prompt").focus(); }
    if (t === "play") startPresent(state.slides.findIndex((s) => s.id === id));
    if (t === "dup" || t === "del") {
      if (state.running) return toast("Wait for the AI to finish first");
      const view = await api(`/api/projects/${state.project.id}/slides`, { json: t === "del" ? { delete: [id] } : { duplicate: id } });
      applyProject(view, false);
    }
  });
  return card;
}
function paintCard(card, s, i) {
  card.classList.toggle("generating", s.status === "generating");
  card.classList.toggle("planned", s.status === "planned");
  $(".num", card).textContent = String(i + 1).padStart(2, "0");
  $(".ttl", card).textContent = s.spec.title || s.spec.quote || (s.status === "done" ? "Untitled" : "…");
  $(".state", card).textContent = s.status === "generating" ? "Designing…" : s.status === "planned" ? "Queued" : s.spec.type === "template" ? `your page ${s.spec.source}` : s.spec.type.replace("_", " ");
  const host = $(".host", card);
  mountSlide(host, s.layout, state.theme, CARD_W);
  host.style.height = "";
  $(".skeleton", card)?.remove();
  if (s.status === "planned") {
    const sk = el("div", "skeleton", `<span class="plan-type">${esc(s.spec.type.replace("_", " "))}</span><span class="plan-title">${esc(s.spec.title || "")}</span><i style="width:72%"></i><i style="width:58%"></i><i style="width:64%"></i>`);
    sk.querySelector("i").remove();
    $(".frame", card).appendChild(sk);
  }
}
function selectOnly(id) { state.selected = new Set([id]); paintSelection(); }
function paintSelection() {
  for (const [id, card] of state.cards) card.classList.toggle("selected", state.selected.has(id));
  renderCtxChips();
}

/* pan & zoom */
function applyTransform(animate) {
  const board = $("#board");
  $("#canvas").classList.toggle("native", isPhone());
  if (isPhone()) animate = false;
  board.classList.toggle("animate", !!animate);
  board.style.transform = `translate(${state.pan.x}px, ${state.pan.y}px) scale(${state.zoom})`;
  $("#zoomLabel").textContent = Math.round(state.zoom * 100) + "%";
  if (animate) setTimeout(() => board.classList.remove("animate"), 600);
}
function boardSize() {
  const n = Math.max(state.slides.length, 1);
  if (state.layout === "row") return { w: n * (CARD_W + GAP_X) - GAP_X, h: CARD_H + HEAD };
  const cols = Math.min(3, n), rows = Math.ceil(n / 3);
  return { w: cols * (CARD_W + GAP_X) - GAP_X, h: rows * (CARD_H + HEAD + GAP_Y) - GAP_Y };
}
function fitBoard(animate) {
  const c = $("#canvas").getBoundingClientRect();
  if (isPhone()) {
    if (!c.width) return;
    state.zoom = (c.width - 24) / CARD_W;
    state.pan = { x: 12, y: 12 };
    applyTransform(false);
    sizeSpacer();
    return;
  }
  const b = boardSize();
  const pad = 70;
  state.zoom = Math.max(0.15, Math.min(1, (c.width - pad * 2) / b.w, (c.height - pad * 2) / b.h));
  if (state.layout === "row") state.zoom = Math.max(0.4, Math.min(1, (c.height - pad * 2) / b.h * 0.6));
  state.pan.x = Math.max(pad, (c.width - b.w * state.zoom) / 2);
  state.pan.y = state.layout === "row" ? (c.height - b.h * state.zoom) / 2 : Math.max(pad, (c.height - b.h * state.zoom) / 2);
  applyTransform(animate);
}
function focusCard(id, force) {
  const i = state.slides.findIndex((s) => s.id === id);
  if (i < 0) return;
  if (isPhone()) {
    const canvas = $("#canvas");
    const top = state.pan.y + cardPos(i).y * state.zoom - 50;
    if (force || top < canvas.scrollTop || top + (CARD_H + HEAD) * state.zoom > canvas.scrollTop + canvas.clientHeight) canvas.scrollTo({ top, behavior: "smooth" });
    return;
  }
  const c = $("#canvas").getBoundingClientRect();
  const p = cardPos(i), z = state.zoom;
  const x0 = state.pan.x + p.x * z, y0 = state.pan.y + p.y * z, x1 = x0 + CARD_W * z, y1 = y0 + (CARD_H + HEAD) * z;
  const visible = x0 >= 20 && y0 >= 20 && x1 <= c.width - 20 && y1 <= c.height - 20;
  if (visible && !force) return;
  state.pan.x = c.width / 2 - (p.x + CARD_W / 2) * z;
  state.pan.y = c.height / 2 - (p.y + (CARD_H + HEAD) / 2) * z;
  applyTransform(true);
}
function zoomAt(factor, cx, cy) {
  const nz = Math.max(0.1, Math.min(2.5, state.zoom * factor));
  state.pan.x = cx - ((cx - state.pan.x) * nz) / state.zoom;
  state.pan.y = cy - ((cy - state.pan.y) * nz) / state.zoom;
  state.zoom = nz;
  applyTransform(false);
}
function initCanvas() {
  const canvas = $("#canvas");
  let drag = null;
  canvas.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".card")) return;
    if (isPhone()) { drag = { x: e.clientX, y: e.clientY, px: 0, py: 0, moved: false, native: true }; return; }
    drag = { x: e.clientX, y: e.clientY, px: state.pan.x, py: state.pan.y, moved: false };
    canvas.setPointerCapture(e.pointerId);
    canvas.classList.add("dragging");
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    if (drag.native) return;
    state.pan.x = drag.px + dx;
    state.pan.y = drag.py + dy;
    applyTransform(false);
  });
  canvas.addEventListener("pointerup", () => {
    if (drag && !drag.moved && state.selected.size) { state.selected.clear(); paintSelection(); closeEditor(); }
    drag = null;
    canvas.classList.remove("dragging");
  });
  canvas.addEventListener("wheel", (e) => {
    if (isPhone()) return;
    e.preventDefault();
    const r = canvas.getBoundingClientRect();
    if (e.ctrlKey || e.metaKey) zoomAt(Math.exp(-e.deltaY * 0.0022), e.clientX - r.left, e.clientY - r.top);
    else { state.pan.x -= e.deltaX; state.pan.y -= e.deltaY; applyTransform(false); }
  }, { passive: false });
  window.addEventListener("resize", () => { if (!$("#workspace").hidden) applyTransform(false); });
  canvas.addEventListener("pointercancel", () => { drag = null; });
  PHONE.addEventListener("change", () => {
    if ($("#workspace").hidden) return;
    state.cards.forEach((c) => (c.dataset.sig = ""));
    renderBoard();
    fitBoard(false);
    if (!isPhone()) delete $("#workspace").dataset.mtab; else setTab("chat");
  });
}

/* ================================================================ present */
function startPresent(index = 0, presenter = false) {
  const done = state.slides.filter((s) => s.status === "done");
  if (!done.length) return toast("No finished slides yet");
  const start = Math.max(0, done.indexOf(state.slides[index]));
  const url = `/present/${state.project.id}?start=${start}${presenter ? "&presenter=1" : ""}`;
  window.open(url, presenter ? "slidesmith-presenter" : "slidesmith-present", presenter ? "width=1200,height=760" : "");
  return;
  const target = state.slides[index];
  state.present = { list: done, i: Math.max(0, done.indexOf(target)) };
  $("#present").hidden = false;
  document.documentElement.requestFullscreen?.().catch(() => {});
  paintPresent();
}
function paintPresent() {
  const { list, i } = state.present;
  const s = list[i];
  const stage = $("#presentStage");
  const W = s.layout.w * PX, H = s.layout.h * PX;
  const scale = Math.min(innerWidth / W, innerHeight / H);
  stage.innerHTML = "";
  stage.style.width = W * scale + "px";
  stage.style.height = H * scale + "px";
  const wrap = el("div", "slide-host");
  wrap.style.transform = `scale(${scale})`;
  wrap.style.transformOrigin = "0 0";
  wrap.appendChild(renderSlide(s.layout, state.theme));
  stage.appendChild(wrap);
  $("#presentCount").textContent = `${i + 1} / ${list.length}`;
  $("#presentNotes").textContent = s.spec.notes || "No speaker notes for this slide.";
}
function stopPresent() {
  state.present = null;
  $("#present").hidden = true;
  if (document.fullscreenElement) document.exitFullscreen?.();
}

/* ================================================================ export */
async function exportDeck() {
  if (!state.project) return;
  try {
    const r = await fetch(`/api/projects/${state.project.id}/export`);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Export failed");
    const blob = await r.blob();
    const name = /filename\*?=(?:UTF-8'')?"?([^";]+)/i.exec(r.headers.get("content-disposition") || "")?.[1] || "presentation.pptx";
    const a = el("a");
    a.href = URL.createObjectURL(blob);
    a.download = decodeURIComponent(name);
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    toast("Exported " + decodeURIComponent(name));
  } catch (e) { toast(e.message, true); }
}

/* ================================================================ settings */
async function openSettings() {
  const s = await api("/api/settings");
  const f = $("#settingsForm");
  f.base_url.value = s.base_url || "";
  f.api_key.value = "";
  f.api_key.placeholder = s.api_key_hint ? `Current key ${s.api_key_hint} — leave blank to keep` : "Paste your API key";
  f.model.value = s.model || "";
  f.review.checked = !!s.review;
  f.review_model.value = s.review_model || "";
  $("#settingsMsg").textContent = "";
  $("#settingsModal").hidden = false;
}
async function fetchModels() {
  const msg = $("#settingsMsg");
  const f = $("#settingsForm");
  msg.className = "form-msg";
  msg.textContent = "Saving & contacting the endpoint…";
  await api("/api/settings", { json: { base_url: f.base_url.value, api_key: f.api_key.value || null, model: f.model.value, review: f.review.checked, review_model: f.review_model.value } });
  const r = await api("/api/models");
  if (r.error) { msg.className = "form-msg err"; msg.textContent = r.error; return; }
  $("#modelList").innerHTML = r.models.map((m) => `<option value="${esc(m)}">`).join("");
  msg.className = "form-msg ok";
  msg.textContent = `Connected — ${r.models.length} model(s): ${r.models.slice(0, 6).join(", ")}${r.models.length > 6 ? "…" : ""}`;
  if (!f.model.value && r.models[0]) f.model.value = r.models[0];
}

/* ================================================================ wiring */
function autosize() {
  const t = $("#prompt");
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight, 180) + "px";
}
function bind() {
  document.addEventListener("click", async (e) => {
    const a = e.target.closest("[data-action]")?.dataset.action;
    if (!a) return;
    if (a === "settings") openSettings();
    if (a === "close-modal") e.target.closest(".modal").hidden = true;
    if (a === "pick-theme") openThemeModal("project");
    if (a === "pick-theme-home") openThemeModal("home");
    if (a === "upload-template") $("#templateInput").click();
    if (a === "home") showHome();
    if (a === "present") { const i = state.slides.findIndex((x) => state.selected.has(x.id)); startPresent(Math.max(0, i)); }
    if (a === "presenter") startPresent(0, true);
    if (a === "export") { closeMenus(); exportDeck(); }
    if (a === "export-pdf") { closeMenus(); if (state.project) window.open(`/present/${state.project.id}?print=1`, "_blank"); }
    if (a === "export-html") { closeMenus(); downloadFile(`/api/projects/${state.project.id}/export.html`, "Web presentation"); }
    if (a === "export-png") {
      closeMenus();
      const sid = [...state.selected][0] || state.slides[0]?.id;
      if (sid) downloadFile(`/api/projects/${state.project.id}/slides/${sid}.png`, "Slide image", `slide.png`);
    }
    if (a === "menu") { const m = document.getElementById(e.target.closest("[data-menu]").dataset.menu); const open = m.hidden; closeMenus(); m.hidden = !open; e.stopPropagation(); }
    if (a === "undo") undo();
    if (a === "history") openHistory();
    if (a === "add-slide") addSlide();
    if (a === "brand") openBrand();
    if (a === "phone") openPhone();
    if (a === "shuffle") shuffleDesign();
    if (a === "zoom-in") { const r = $("#canvas").getBoundingClientRect(); zoomAt(1.2, r.width / 2, r.height / 2); }
    if (a === "zoom-out") { const r = $("#canvas").getBoundingClientRect(); zoomAt(1 / 1.2, r.width / 2, r.height / 2); }
    if (a === "zoom-fit") fitBoard(true);
    if (a === "toggle-follow") { state.follow = !state.follow; $("#followBtn").classList.toggle("on", state.follow); toast(state.follow ? "Camera follows the AI while it builds" : "Follow mode off"); }
    if (a === "toggle-layout") { state.layout = state.layout === "grid" ? "row" : "grid"; renderBoard(); fitBoard(true); }
    if (a === "fetch-models") fetchModels().catch((err) => { $("#settingsMsg").className = "form-msg err"; $("#settingsMsg").textContent = err.message; });
  });
  $$(".modal").forEach((m) => m.addEventListener("click", (e) => { if (e.target === m) m.hidden = true; }));
  document.addEventListener("click", (e) => { if (!e.target.closest(".menu-wrap")) closeMenus(); });
  $$("#transSeg button").forEach((b) => (b.onclick = async () => {
    $$("#transSeg button").forEach((x) => x.classList.toggle("on", x === b));
    await api(`/api/projects/${state.project.id}/settings`, { method: "PATCH", json: { transition: b.dataset.trans } });
    toast(`Transition: ${b.textContent} (also saved into the .pptx)`);
  }));
  $("#buildsChk").onchange = (e) => api(`/api/projects/${state.project.id}/settings`, { method: "PATCH", json: { builds: e.target.checked } });
  $("#brandForm").addEventListener("submit", submitBrand);
  $$("#mtabs [data-mtab]").forEach((b) => (b.onclick = () => setTab(b.dataset.mtab)));
  $("#brandImport").onclick = importBrand;

  $("#homeForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("#homePrompt").value.trim();
    if (!text) return $("#homePrompt").focus();
    $("#homeGo").disabled = true;
    try {
      const p = await api("/api/projects", { json: { name: "", theme_id: state.homeTheme } });
      $("#homePrompt").value = "";
      const files = state.homeFiles;
      state.homeFiles = [];
      renderFileChips($("#homeFiles"), [], () => {});
      await openProject(p.id, text, files);
    } catch (err) { toast(err.message, true); }
    $("#homeGo").disabled = false;
  });
  $("#homePrompt").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#homeForm").requestSubmit(); } });
  $("#homeAttach").addEventListener("change", (e) => {
    state.homeFiles.push(...e.target.files);
    e.target.value = "";
    const paint = () => renderFileChips($("#homeFiles"), state.homeFiles, (i) => { state.homeFiles.splice(i, 1); paint(); });
    paint();
  });
  $("#examples").append(...EXAMPLES.map((x) => { const b = el("button", "", esc(x)); b.type = "button"; b.onclick = () => { $("#homePrompt").value = x; $("#homePrompt").focus(); }; return b; }));

  $("#composer").addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.running) { fetch(`/api/projects/${state.project.id}/stop`, { method: "POST" }); $("#buildText").textContent = "Stopping…"; return; }
    send($("#prompt").value);
  });
  $("#prompt").addEventListener("input", autosize);
  $("#prompt").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!state.running) send($("#prompt").value); } });
  $("#attach").addEventListener("change", (e) => { state.files.push(...e.target.files); e.target.value = ""; renderCtxChips(); });
  $("#templateInput").addEventListener("change", (e) => { if (e.target.files[0]) uploadTemplate(e.target.files[0]); e.target.value = ""; });
  $("#projectName").addEventListener("change", async (e) => {
    if (!state.project) return;
    const view = await api(`/api/projects/${state.project.id}`, { method: "PATCH", json: { name: e.target.value } });
    state.project.name = view.name;
  });
  $("#settingsForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    await api("/api/settings", { json: { base_url: f.base_url.value, api_key: f.api_key.value || null, model: f.model.value, review: f.review.checked, review_model: f.review_model.value } });
    $("#settingsModal").hidden = true;
    toast("Settings saved");
    loadStatus();
  });
  document.addEventListener("keydown", (e) => {
    if (state.present) {
      if (["ArrowRight", "PageDown", " ", "Enter"].includes(e.key)) { state.present.i = Math.min(state.present.list.length - 1, state.present.i + 1); paintPresent(); }
      else if (["ArrowLeft", "PageUp", "Backspace"].includes(e.key)) { state.present.i = Math.max(0, state.present.i - 1); paintPresent(); }
      else if (e.key === "Escape") stopPresent();
      else if (e.key.toLowerCase() === "n") $("#presentNotes").hidden = !$("#presentNotes").hidden;
      return;
    }
    if (e.key === "Escape") { $$(".modal").forEach((m) => (m.hidden = true)); closeMenus(); }
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "");
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !typing && !$("#workspace").hidden) { e.preventDefault(); undo(); }
  });
  $("#present").addEventListener("click", (e) => { if (state.present && !e.target.closest(".present-notes")) { state.present.i = Math.min(state.present.list.length - 1, state.present.i + 1); paintPresent(); } });
  document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement && state.present) stopPresent(); });
  window.addEventListener("resize", () => { if (state.present) paintPresent(); });
  $("#followBtn").classList.add("on");
}

/* ================================================================ menus, history, undo, add slide, downloads */
function closeMenus() { $$(".menu").forEach((m) => (m.hidden = true)); }

async function downloadFile(url, label, fallbackName = "download") {
  try {
    toast(`Preparing ${label}…`);
    const r = await fetch(url);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${label} failed`);
    const blob = await r.blob();
    const name = /filename\*?=(?:UTF-8'')?"?([^";]+)/i.exec(r.headers.get("content-disposition") || "")?.[1] || fallbackName;
    const a = el("a");
    a.href = URL.createObjectURL(blob);
    a.download = decodeURIComponent(name);
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  } catch (e) { toast(e.message, true); }
}

async function shuffleDesign() {
  if (!state.project || state.running) return;
  if (!state.slides.length) return toast("Create some slides first");
  const btn = $("#shuffleBtn");
  btn.disabled = true;
  btn.classList.add("spinning");
  try {
    applyProject(await api(`/api/projects/${state.project.id}/shuffle`, { method: "POST" }), true);
    if (editorOpenFor()) openEditor(editorOpenFor());
    toast("New design: layouts, color emphasis, icons and decoration changed. Shuffle again or Undo to go back.");
  } catch (e) { toast(e.message, true); }
  btn.disabled = false;
  btn.classList.remove("spinning");
}

async function undo() {
  if (!state.project || state.running) return;
  try {
    applyProject(await api(`/api/projects/${state.project.id}/undo`, { method: "POST" }), true);
    if (editorOpenFor()) openEditor(editorOpenFor());
    toast("Undone");
  } catch (e) { toast(e.message, true); }
}

async function openHistory() {
  const { history } = await api(`/api/projects/${state.project.id}/history`);
  const list = $("#historyList");
  list.innerHTML = history.length ? "" : `<p class="muted">No earlier versions yet.</p>`;
  for (const h of history) {
    const row = el("div", "h-row", `<div><b>${esc(h.label)}</b><small>${new Date(h.t * 1000).toLocaleString()} · ${h.slides} slides</small></div>`);
    const b = el("button", "ghost-btn", "Restore");
    b.onclick = async () => {
      applyProject(await api(`/api/projects/${state.project.id}/history/${h.i}/restore`, { method: "POST" }), true);
      $("#historyModal").hidden = true;
      closeEditor();
      toast("Restored that version");
    };
    row.appendChild(b);
    list.appendChild(row);
  }
  $("#historyModal").hidden = false;
}

async function addSlide() {
  if (!state.project) return;
  const after = [...state.selected][0] || state.slides[state.slides.length - 1]?.id;
  const view = await api(`/api/projects/${state.project.id}/slides/add`, { json: { after, spec: { type: "bullets", title: "New slide", bullets: ["Click to edit this slide"] } } });
  applyProject(view, false);
  const added = view.slides[(view.slides.findIndex((x) => x.id === after) + 1) || view.slides.length - 1];
  if (added) { selectOnly(added.id); openEditor(added.id); focusCard(added.id, true); }
}

/* ================================================================ open on phone */
async function openPhone() {
  const net = await api("/api/network");
  const body = $("#phoneBody");
  if (net.lan && net.url) {
    body.innerHTML = `<img alt="QR code" src="/api/network/qr.png?url=${encodeURIComponent(net.url)}"><div class="url">${esc(net.url)}</div>
      <ol><li>Connect your phone to the <b>same Wi-Fi</b> as this PC.</li><li>Scan the code with the camera, or type the address in the phone's browser.</li>
      <li>If it doesn't load, allow Python through Windows Firewall (private networks) when Windows asks.</li></ol>
      ${net.public ? `<p class="form-msg err" style="font-size:12.5px">This PC has a public network address (common on college/office networks). When Windows asks, allow access on <b>Private networks only</b> — never "Public" — or anyone on the internet could reach SlideSmith and use your AI key. If your phone can't connect, the network may block device-to-device traffic: use your phone's hotspot or home Wi-Fi instead.</p>` : ""}
      ${net.others && net.others.length ? `<p class="muted" style="font-size:12.5px">Not loading? Your PC has other network addresses — try: ${net.others.map((u) => `<b>${esc(u)}</b>`).join(", ")}</p>` : ""}`;
  } else {
    body.innerHTML = `<ol><li>Close this SlideSmith window (the black one).</li>
      <li>Double-click <b>Start SlideSmith (phone access).bat</b> in the SlideSmith folder.</li>
      <li>Open this dialog again — a QR code for your phone will appear here.</li></ol>
      <p class="muted" style="font-size:12.5px">Phone access lets devices on your Wi-Fi use SlideSmith (and your AI key). Use it on networks you trust.</p>`;
  }
  $("#phoneModal").hidden = false;
}

/* ================================================================ brand kit */
async function openBrand() {
  const { fonts } = await api("/api/brands/fonts");
  $$("#brandForm .font-select").forEach((s) => { s.innerHTML = fonts.map((f) => `<option>${esc(f)}</option>`).join(""); });
  $("#brandForm").reset();
  $("#brandMsg").textContent = "";
  $("#themeModal").hidden = true;
  $("#brandModal").hidden = false;
}
async function importBrand() {
  const f = $("#brandForm");
  const msg = $("#brandMsg");
  msg.className = "form-msg";
  msg.textContent = "Reading the website…";
  try {
    const r = await api("/api/brands/import", { json: { url: f.url.value } });
    if (r.name) f.name.value = r.name;
    if (r.primary) f.primary.value = r.primary;
    if (r.secondary) f.secondary.value = r.secondary;
    f.logo_url.value = r.logo_url || "";
    msg.className = "form-msg ok";
    msg.textContent = `Found colors ${r.primary || ""} ${r.secondary || ""}${r.logo_url ? " and a logo" : ""}. Adjust anything, then create the theme.`;
  } catch (e) { msg.className = "form-msg err"; msg.textContent = e.message; }
}
async function submitBrand(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  fd.delete("url");
  if (!e.target.logo.files[0]) fd.delete("logo");
  try {
    const { theme_id } = await api("/api/brands", { method: "POST", body: fd });
    $("#brandModal").hidden = true;
    await loadThemes();
    state.themeModalFor = state.project && !$("#workspace").hidden ? "project" : "home";
    await chooseTheme(theme_id);
    toast("Brand theme created and applied");
  } catch (err) { $("#brandMsg").className = "form-msg err"; $("#brandMsg").textContent = err.message; }
}

async function init() {
  bind();
  initEditor({
    api, toast, getState: () => state,
    onProject: (view) => applyProject(view, false),
    sendChat: (text, ids) => { state.selected = new Set(ids); paintSelection(); send(text); },
  });
  initCanvas();
  await loadThemes();
  loadStatus();
  const pid = new URLSearchParams(location.search).get("p");
  if (pid) { try { return await openProject(pid); } catch { /* fall through to home */ } }
  showHome();
}
init();
