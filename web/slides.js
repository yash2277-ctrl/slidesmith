// Renders a server "display list" (inches/points) into HTML at 96 px per inch.
export const PX = 96;
const PT = 96 / 72;

const h = (tag, cls, style) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (style) Object.assign(n.style, style);
  return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export function rgba(hex, a = 1) {
  if (!hex) return "transparent";
  const v = hex.replace("#", "");
  const r = parseInt(v.slice(0, 2), 16), g = parseInt(v.slice(2, 4), 16), b = parseInt(v.slice(4, 6), 16);
  return a >= 1 ? `#${v.slice(0, 6)}` : `rgba(${r},${g},${b},${a})`;
}

export function fontStack(theme, kind, face) {
  const name = face || (kind === "heading" ? theme.fonts.heading : theme.fonts.body);
  const serif = /georgia|cambria|times|garamond|serif|constantia|palatino|book/i.test(name);
  return `"${name}", ${serif ? 'Georgia, "Times New Roman", serif' : '"Segoe UI", Calibri, Arial, sans-serif'}`;
}

function fillCss(fill) {
  if (!fill) return "transparent";
  if (fill.type === "solid") return rgba(fill.color, fill.alpha ?? 1);
  if (fill.type === "gradient") {
    const stops = fill.stops.map((s) => `${rgba(s.color, s.alpha ?? 1)} ${s.pos}%`).join(", ");
    return fill.radial ? `radial-gradient(circle at center, ${stops})` : `linear-gradient(${(fill.angle ?? 90) + 90}deg, ${stops})`;
  }
  if (fill.type === "image") return `url("${fill.src}") center / 100% 100% no-repeat`;
  return "transparent";
}

function box(n, it) {
  Object.assign(n.style, { left: it.x * PX + "px", top: it.y * PX + "px", width: Math.max(it.w, 0.001) * PX + "px", height: Math.max(it.h, 0.001) * PX + "px" });
  const tf = [];
  if (it.rot) tf.push(`rotate(${it.rot}deg)`);
  if (it.flipH) tf.push("scaleX(-1)");
  if (it.flipV) tf.push("scaleY(-1)");
  if (tf.length) n.style.transform = tf.join(" ");
  return n;
}

function decorNode(d, theme) {
  if (d.kind === "image") {
    const img = box(h("img", "el"), d);
    img.src = d.src;
    img.draggable = false;
    img.style.objectFit = "fill";
    return img;
  }
  if (d.kind === "line") {
    const n = box(h("div", "el"), d);
    const [x1, x2] = d.flipH ? ["100%", "0"] : ["0", "100%"];
    const [y1, y2] = d.flipV ? ["100%", "0"] : ["0", "100%"];
    n.style.transform = d.rot ? `rotate(${d.rot}deg)` : "";
    n.style.overflow = "visible";
    n.innerHTML = `<svg style="overflow:visible"><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${rgba(d.line.color, d.line.alpha ?? 1)}" stroke-width="${d.line.width * PT}"/></svg>`;
    return n;
  }
  const n = box(h("div", "el"), d);
  if (d.geom === "path") {
    const fill = d.fill && d.fill.type === "solid" ? rgba(d.fill.color, d.fill.alpha ?? 1) : d.fill?.stops ? rgba(d.fill.stops[0].color) : "none";
    const stroke = d.line ? `stroke="${rgba(d.line.color, d.line.alpha ?? 1)}" stroke-width="${d.line.width * PT}" vector-effect="non-scaling-stroke"` : "";
    n.innerHTML = `<svg viewBox="0 0 1000 1000" preserveAspectRatio="none" style="overflow:visible"><path d="${d.path}" fill="${fill}" ${stroke}/></svg>`;
  } else {
    n.style.background = fillCss(d.fill);
    if (d.line) n.style.border = `${d.line.width * PT}px solid ${rgba(d.line.color, d.line.alpha ?? 1)}`;
    if (d.geom === "ellipse") n.style.borderRadius = "50%";
    if (d.geom === "roundRect") n.style.borderRadius = Math.min(d.w, d.h) * PX * 0.16 + "px";
  }
  if (d.text) {
    const t = d.text;
    n.style.display = "flex";
    n.style.flexDirection = "column";
    n.style.justifyContent = { ctr: "center", b: "flex-end" }[t.anchor] || "flex-start";
    n.style.padding = "0.05in 0.1in";
    n.innerHTML += `<div style="font:${t.bold ? 700 : 400} ${t.size * PT}px ${fontStack(theme, "body")};color:${t.color || "inherit"};text-align:${{ ctr: "center", r: "right" }[t.align] || "left"};white-space:pre-wrap">${esc(t.text)}</div>`;
  }
  return n;
}

function textNode(el, theme, defaultColor) {
  const n = box(h("div", "el tx"), el);
  n.style.justifyContent = { m: "center", b: "flex-end" }[el.valign] || "flex-start";
  n.style.textAlign = { c: "center", r: "right", j: "justify" }[el.align] || "left";
  if (el.rot) n.style.transform = `rotate(${el.rot}deg)`;
  n.style.tabSize = "4";
  for (const p of el.paras) {
    const para = h("p");
    const size = p.size * PT;
    para.style.font = `${p.italic ? "italic " : ""}${p.bold ? 700 : 400} ${size}px/${el.line || 1.15} ${fontStack(theme, p.font, p.face)}`;
    if (p.align) para.style.textAlign = { c: "center", r: "right", j: "justify" }[p.align] || "left";
    para.style.color = p.color || defaultColor;
    if (p.caps) para.style.textTransform = "uppercase";
    if (p.spacing) para.style.letterSpacing = p.spacing * PT + "px";
    if (p.space) para.style.marginBottom = p.space * PT + "px";
    if (p.bullet && (p.text || "").trim()) {
      para.classList.add("bul");
      if (p.level) para.classList.add("l1");
      const ind = size * 1.1;
      para.style.paddingLeft = ind + "px";
      if (p.level) para.style.marginLeft = 0.35 * PX + "px";
      para.style.setProperty("--bul", p.bullet === "tpl" ? (p.color || "currentColor") : p.bullet);
    }
    para.textContent = p.text || "​";
    n.appendChild(para);
  }
  return n;
}

function niceStep(max) {
  if (max <= 0) return 1;
  const raw = max / 4, pow = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 2.5, 5, 10]) if (raw <= m * pow) return m * pow;
  return 10 * pow;
}

function fmt(v, unit) {
  const n = Math.abs(v) >= 100 || Number.isInteger(v) ? Math.round(v).toLocaleString() : (+v.toFixed(2)).toLocaleString();
  return unit === "$" ? "$" + n : unit ? n + unit : n;
}

function chartNode(el, theme) {
  const n = box(h("div", "el"), el);
  const W = el.w * PX, H = el.h * PX, ch = el.chart, cols = el.colors;
  const fs = 12 * PT, font = fontStack(theme, "body", el.face);
  const cats = ch.categories, series = ch.series;
  let s = `<svg viewBox="0 0 ${W} ${H}" style="font-family:${esc(font)};font-size:${fs}px">`;
  if (ch.kind === "pie" || ch.kind === "doughnut") {
    const vals = (series[0]?.values || []).map((v) => Math.max(0, v));
    const total = vals.reduce((a, b) => a + b, 0) || 1;
    const r = Math.min(W * 0.32, H * 0.44), cx = W * 0.38, cy = H / 2;
    let a0 = -Math.PI / 2;
    vals.forEach((v, i) => {
      const a1 = a0 + (v / total) * Math.PI * 2;
      const large = a1 - a0 > Math.PI ? 1 : 0;
      const p = (a) => `${cx + r * Math.cos(a)} ${cy + r * Math.sin(a)}`;
      const d = vals.length === 1 ? `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0` : `M${cx} ${cy}L${p(a0)}A${r} ${r} 0 ${large} 1 ${p(a1)}Z`;
      s += `<path d="${d}" fill="${cols[i % cols.length]}" stroke="${el.bg}" stroke-width="2"/>`;
      const mid = (a0 + a1) / 2, lr = ch.kind === "doughnut" ? r * 0.78 : r * 0.62;
      if (v / total > 0.04) s += `<text x="${cx + lr * Math.cos(mid)}" y="${cy + lr * Math.sin(mid)}" text-anchor="middle" dominant-baseline="middle" fill="#fff" font-weight="600">${esc(fmt(v, ch.unit))}</text>`;
      a0 = a1;
    });
    if (ch.kind === "doughnut") s += `<circle cx="${cx}" cy="${cy}" r="${r * 0.55}" fill="${el.bg}"/>`;
    const lx = W * 0.74, ly = cy - (cats.length * fs * 1.7) / 2;
    cats.forEach((c, i) => {
      s += `<rect x="${lx}" y="${ly + i * fs * 1.7}" width="${fs * 0.8}" height="${fs * 0.8}" rx="3" fill="${cols[i % cols.length]}"/>`;
      s += `<text x="${lx + fs * 1.3}" y="${ly + i * fs * 1.7 + fs * 0.72}" fill="${el.text}">${esc(c)}</text>`;
    });
    return (n.innerHTML = s + "</svg>"), n;
  }
  const all = series.flatMap((x) => x.values);
  const max = Math.max(0, ...all), min = Math.min(0, ...all);
  const step = niceStep(max - min || 1);
  const top = Math.ceil(max / step) * step || step, bottom = Math.floor(min / step) * step;
  const multi = series.length > 1;
  const pad = { l: ch.kind === "bar" ? Math.min(W * 0.28, 12 + Math.max(...cats.map((c) => c.length)) * fs * 0.55) : fs * 3.4,
    r: ch.kind === "bar" && !multi ? fs * 3.6 : 12, t: multi ? fs * 2.4 : fs * 1.2, b: ch.kind === "bar" ? fs * 1.8 : fs * 2.2 };
  const pw = W - pad.l - pad.r, ph = H - pad.t - pad.b;
  if (multi) {
    let x = pad.l;
    series.forEach((ser, i) => {
      s += `<rect x="${x}" y="${fs * 0.2}" width="${fs * 0.8}" height="${fs * 0.8}" rx="3" fill="${cols[i % cols.length]}"/><text x="${x + fs * 1.2}" y="${fs * 0.95}" fill="${el.text}">${esc(ser.name)}</text>`;
      x += fs * 2.2 + ser.name.length * fs * 0.55;
    });
  }
  const label = (v) => esc(fmt(v, ch.unit));
  const showLabels = !multi && cats.length <= 10;
  if (ch.kind === "bar") {
    const vx = (v) => pad.l + ((v - bottom) / (top - bottom)) * pw;
    for (let v = bottom; v <= top + 1e-9; v += step) s += `<line x1="${vx(v)}" x2="${vx(v)}" y1="${pad.t}" y2="${pad.t + ph}" stroke="${el.grid}"/><text x="${vx(v)}" y="${H - 4}" text-anchor="middle" fill="${el.text}" font-size="${fs * 0.9}">${label(v)}</text>`;
    const band = ph / cats.length, bw = (band * 0.7) / series.length;
    cats.forEach((c, ci) => {
      s += `<text x="${pad.l - 8}" y="${pad.t + band * ci + band / 2}" text-anchor="end" dominant-baseline="middle" fill="${el.text}">${esc(c)}</text>`;
      series.forEach((ser, si) => {
        const v = ser.values[ci] ?? 0, y = pad.t + band * ci + band * 0.15 + bw * si;
        s += `<rect x="${Math.min(vx(0), vx(v))}" y="${y}" width="${Math.abs(vx(v) - vx(0))}" height="${bw * 0.92}" rx="2" fill="${cols[si % cols.length]}"/>`;
        if (showLabels) s += `<text x="${vx(v) + 6}" y="${y + bw / 2}" dominant-baseline="middle" fill="${el.text}" font-size="${fs * 0.92}">${label(v)}</text>`;
      });
    });
    return (n.innerHTML = s + "</svg>"), n;
  }
  const vy = (v) => pad.t + ph - ((v - bottom) / (top - bottom)) * ph;
  for (let v = bottom; v <= top + 1e-9; v += step) s += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${vy(v)}" y2="${vy(v)}" stroke="${el.grid}"/><text x="${pad.l - 8}" y="${vy(v)}" text-anchor="end" dominant-baseline="middle" fill="${el.text}" font-size="${fs * 0.9}">${label(v)}</text>`;
  const band = pw / cats.length;
  cats.forEach((c, ci) => (s += `<text x="${pad.l + band * ci + band / 2}" y="${H - fs * 0.5}" text-anchor="middle" fill="${el.text}">${esc(c)}</text>`));
  if (ch.kind === "line") {
    series.forEach((ser, si) => {
      const col = cols[si % cols.length];
      const pts = ser.values.map((v, ci) => [pad.l + band * ci + band / 2, vy(v)]);
      s += `<polyline points="${pts.map((p) => p.join(",")).join(" ")}" fill="none" stroke="${col}" stroke-width="${3 * PT}" stroke-linejoin="round"/>`;
      pts.forEach(([x, y], ci) => {
        s += `<circle cx="${x}" cy="${y}" r="${4.5 * PT}" fill="${col}"/>`;
        if (showLabels) s += `<text x="${x}" y="${y - 12}" text-anchor="middle" fill="${el.text}" font-size="${fs * 0.92}">${label(ser.values[ci])}</text>`;
      });
    });
  } else {
    const bw = (band * 0.62) / series.length;
    series.forEach((ser, si) => {
      ser.values.forEach((v, ci) => {
        const x = pad.l + band * ci + band * 0.19 + bw * si;
        s += `<rect x="${x}" y="${Math.min(vy(v), vy(0))}" width="${bw * 0.94}" height="${Math.abs(vy(0) - vy(v))}" rx="2" fill="${cols[si % cols.length]}"/>`;
        if (showLabels) s += `<text x="${x + bw / 2}" y="${vy(v) - 8}" text-anchor="middle" fill="${el.text}" font-size="${fs * 0.92}">${label(v)}</text>`;
      });
    });
  }
  return (n.innerHTML = s + "</svg>"), n;
}

function tplTableNode(el, theme) {
  const n = box(h("div", "el"), el);
  const total = el.cols.reduce((a, b) => a + b, 0) || 1;
  let s = `<table style="height:auto">` + `<colgroup>${el.cols.map((c) => `<col style="width:${(c / total) * 100}%">`).join("")}</colgroup>`;
  for (const row of el.rows) {
    s += `<tr style="height:${row.h * PX}px">`;
    for (const cell of row.cells) {
      const p = cell.paras[0] || { size: 14, color: "#000", bold: false };
      s += `<td style="border:1px solid rgba(0,0,0,.35);background:${cell.fill || "transparent"};font:${p.bold ? 700 : 400} ${p.size * PT}px ${esc(fontStack(theme, "body", p.face))};color:${p.color || "#000"};text-align:${{ c: "center", r: "right" }[p.align] || "left"}">${esc(cell.text)}</td>`;
    }
    s += "</tr>";
  }
  n.innerHTML = s + "</table>";
  return n;
}

function tableNode(el, theme) {
  const n = box(h("div", "el"), el);
  const fs = el.size * PT, font = fontStack(theme, "body", el.face);
  let s = `<table style="font:${fs}px ${esc(font)}"><tr>`;
  s += el.columns.map((c) => `<th style="background:${el.header_fill};color:${el.header_text};font-weight:700">${esc(c)}</th>`).join("") + "</tr>";
  el.rows.forEach((r, i) => {
    s += `<tr>` + r.map((c) => `<td style="background:${i % 2 ? el.fill_b : el.fill_a};color:${el.text};border-bottom:1px solid ${el.border}">${esc(c)}</td>`).join("") + "</tr>";
  });
  n.innerHTML = s + "</table>";
  return n;
}

export function renderSlide(layout, theme) {
  const W = layout.w * PX, H = layout.h * PX;
  const root = h("div", "slide", { width: W + "px", height: H + "px" });
  let defaultColor = theme.colors?.text || "#111";
  const tplLayout = theme.kind === "custom" && layout.layout_key ? (theme.layouts || []).find((l) => l.key === layout.layout_key) : null;
  if (tplLayout) {
    const bg = layout.bg || tplLayout.background;
    root.style.background = bg ? fillCss(bg) : tplLayout.bg_color;
    if (bg?.type !== "solid") root.style.backgroundColor = tplLayout.bg_color;
    if (!layout.hide_master) for (const d of tplLayout.decor || []) { const dn = decorNode(d, theme); dn.dataset.static = "1"; root.appendChild(dn); }
  } else {
    root.style.background = layout.bg ? fillCss(layout.bg) : theme.colors?.bg || "#fff";
  }
  for (const el of layout.elements || []) {
    let node = null;
    if (el.t === "text") node = textNode(el, theme, defaultColor);
    else if (el.t === "rect" || el.t === "ellipse") {
      node = box(h("div", "el"), el);
      node.style.background = el.fill ? rgba(el.fill, el.alpha ?? 1) : "transparent";
      if (el.t === "ellipse") node.style.borderRadius = "50%";
      else if (el.radius) node.style.borderRadius = el.radius * PX + "px";
      if (el.line) node.style.border = `${el.line.width * PT}px solid ${el.line.color}`;
    } else if (el.t === "chart") node = chartNode(el, theme);
    else if (el.t === "table") node = tableNode(el, theme);
    else if (el.t === "triangle") {
      node = box(h("div", "el"), el);
      const stroke = el.line ? ` stroke="${el.line.color}" stroke-width="${el.line.width * PT}" vector-effect="non-scaling-stroke"` : "";
      node.innerHTML = `<svg viewBox="0 0 ${el.w * PX} ${el.h * PX}" preserveAspectRatio="none" style="overflow:visible"><polygon points="0,${el.h * PX} ${el.w * PX},${el.h * PX} ${el.w * PX / 2},0" fill="${el.fill ? rgba(el.fill, el.alpha ?? 1) : "none"}"${stroke}/></svg>`;
    }
    else if (el.t === "decor") node = decorNode(el.d, theme);
    else if (el.t === "image") {
      node = box(h("img", "el"), el);
      node.src = el.src;
      node.alt = "";
      node.draggable = false;
      node.style.objectFit = el.fit === "contain" ? "contain" : "cover";
      if (el.radius) node.style.borderRadius = el.radius * PX + "px";
    } else if (el.t === "shape") {
      node = box(h("div", "el"), el);
      const d = Math.min(50, ((el.h * 0.5) / el.w) * 100);
      const W = el.w * PX, H = el.h * PX;
      const poly = el.geom === "homePlate"
        ? `0,0 ${W * (1 - d / 100)},0 ${W},${H / 2} ${W * (1 - d / 100)},${H} 0,${H}`
        : `0,0 ${W * (1 - d / 100)},0 ${W},${H / 2} ${W * (1 - d / 100)},${H} 0,${H} ${W * d / 100},${H / 2}`;
      const strokeAttr = el.line ? ` stroke="${el.line.color}" stroke-width="${el.line.width * PT}" vector-effect="non-scaling-stroke"` : "";
      node.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="overflow:visible"><polygon points="${poly}" fill="${el.fill || "transparent"}"${strokeAttr}/></svg>`;
    }
    else if (el.t === "tpltable") node = tplTableNode(el, theme);
    else if (el.t === "connector") {
      // an arrow between two points; drawn as SVG so the head and dash match the PNG
      const x1 = el.x1 * PX, y1 = el.y1 * PX, x2 = el.x2 * PX, y2 = el.y2 * PX;
      const wpx = Math.max(1, el.width * PT);
      const ang = Math.atan2(y2 - y1, x2 - x1);
      const head = Math.max(6 * PT, wpx * 3.4);
      const p1 = `${x2},${y2}`;
      const p2 = `${x2 - head * Math.cos(ang - 0.42)},${y2 - head * Math.sin(ang - 0.42)}`;
      const p3 = `${x2 - head * Math.cos(ang + 0.42)},${y2 - head * Math.sin(ang + 0.42)}`;
      const dash = el.dash ? ` stroke-dasharray="${wpx * 3.2} ${wpx * 2.2}"` : "";
      node = h("div", "el");
      node.style.left = "0"; node.style.top = "0"; node.style.width = "0"; node.style.height = "0";
      node.innerHTML = `<svg viewBox="0 0 ${layout.w * PX} ${layout.h * PX}" style="position:absolute;left:0;top:0;width:${layout.w * PX}px;height:${layout.h * PX}px;overflow:visible;pointer-events:none">
        <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${el.color}" stroke-width="${wpx}"${dash}/>
        ${el.arrow ? `<polygon points="${p1} ${p2} ${p3}" fill="${el.color}"/>` : ""}
      </svg>`;
    }
    if (node && el.quiz) { node.dataset.quiz = el.quiz.i; node.dataset.correct = el.quiz.correct ? "1" : "0"; node.classList.add("quiz-opt"); }
    if (node && el.quiz_explain) node.classList.add("quiz-explain");
    if (node && (el.static || el.t === "decor")) node.dataset.static = "1";
    if (node) root.appendChild(node);
  }
  return root;
}

// Render a slide scaled to fit a given pixel width inside `host`.
export function mountSlide(host, layout, theme, width) {
  host.innerHTML = "";
  const s = renderSlide(layout, theme);
  const wrap = h("div", "slide-host");
  wrap.style.transform = `scale(${width / (layout.w * PX)})`;
  wrap.appendChild(s);
  host.appendChild(wrap);
  host.style.height = (width * layout.h) / layout.w + "px";
  return wrap;
}
