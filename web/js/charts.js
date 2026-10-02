// Small charts for the admin dashboard: horizontal bars and one line.
// Colours come from CSS tokens (--series-1, --status-*), so light and dark
// mode each use their own steps.
import { el, pretty } from "./ui.js";

const SVG = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}) => {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

// ── Tooltip (one, shared) ────────────────────────────────────────────────────

function tip(html, x, y) {
  const t = document.getElementById("tooltip");
  t.replaceChildren(...html);
  t.hidden = false;
  const r = t.getBoundingClientRect();
  const left = Math.min(x + 14, innerWidth - r.width - 8);
  const top = y - r.height - 12 < 8 ? y + 16 : y - r.height - 12;
  t.style.left = `${Math.max(8, left)}px`;
  t.style.top = `${top}px`;
}
const untip = () => { document.getElementById("tooltip").hidden = true; };

// ── Bars ─────────────────────────────────────────────────────────────────────
// items: [{ label, count }]. status: map label -> { color var, icon } for risk levels.

const RISK = {
  critical: { color: "var(--status-critical)", icon: "‼" },
  high:     { color: "var(--status-serious)",  icon: "!" },
  moderate: { color: "var(--status-warning)",  icon: "•" },
  low:      { color: "var(--status-good)",     icon: "✓" },
};

export function barChart(host, items, { status = false } = {}) {
  host.replaceChildren();
  const rows = (items || []).filter((i) => i.count > 0);
  if (!rows.length) {
    host.append(el("p", { class: "empty" }, "No data yet"));
    return;
  }
  const total = rows.reduce((s, i) => s + i.count, 0);
  const max = Math.max(...rows.map((i) => i.count));
  const list = el("div", { class: "bars", role: "list" });
  for (const item of rows) {
    const s = status ? RISK[item.label] : null;
    const pct = (item.count / total) * 100;
    const bar = el("div", { class: "bar" });
    bar.style.width = `${Math.max(1, (item.count / max) * 100)}%`;
    bar.style.background = s?.color ?? "var(--series-1)";
    const label = pretty(item.label);
    const row = el("div", { class: "bar-row", role: "listitem", "aria-label": `${label}: ${item.count}` },
      el("span", { class: "bar-label" }, s ? el("span", { class: "bar-icon", "aria-hidden": "true" }, s.icon) : null, label),
      el("span", { class: "bar-track" }, bar, el("span", { class: "bar-value" }, item.count.toLocaleString())),
    );
    row.addEventListener("pointermove", (e) => tip([
      el("b", {}, label), el("br"), `${item.count.toLocaleString()} (${pct.toFixed(1)}%)`,
    ], e.clientX, e.clientY));
    row.addEventListener("pointerleave", untip);
    list.append(row);
  }
  host.append(list);
}

// ── Line ─────────────────────────────────────────────────────────────────────
// points: [{ x, y, label }] with x increasing. Crosshair + tooltip on hover.

export function lineChart(host, points, { yUnit = "", xName = "Frame" } = {}) {
  host.replaceChildren();
  const pts = (points || []).filter((p) => p.y != null && Number.isFinite(p.y));
  if (pts.length < 2) {
    host.append(el("p", { class: "empty" }, "Not enough frames to draw"));
    return;
  }
  const W = 720, H = 220, L = 44, R = 16, T = 14, B = 28;
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const yMax = niceMax(Math.max(...ys, 0.1));
  const sx = (x) => L + ((x - x0) / (x1 - x0 || 1)) * (W - L - R);
  const sy = (y) => T + (1 - y / yMax) * (H - T - B);

  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "line-chart", role: "img",
    "aria-label": `Line chart, ${pts.length} points, highest ${Math.max(...ys).toFixed(2)} ${yUnit}` });

  for (let i = 0; i <= 4; i++) {
    const v = (yMax * i) / 4, y = sy(v);
    root.append(svg("line", { x1: L, x2: W - R, y1: y, y2: y, class: i ? "grid" : "axis" }));
    const t = svg("text", { x: L - 6, y: y + 4, class: "tick", "text-anchor": "end" });
    t.textContent = v.toFixed(v < 1 ? 2 : 1);
    root.append(t);
  }
  for (const v of [x0, Math.round((x0 + x1) / 2), x1]) {
    const t = svg("text", { x: sx(v), y: H - 8, class: "tick", "text-anchor": "middle" });
    t.textContent = v;
    root.append(t);
  }

  const d = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join("");
  root.append(svg("path", { d: `${d}L${sx(x1)},${sy(0)}L${sx(x0)},${sy(0)}Z`, class: "area" }));
  root.append(svg("path", { d, class: "line" }));
  const last = pts.at(-1);
  root.append(svg("circle", { cx: sx(last.x), cy: sy(last.y), r: 4, class: "dot" }));

  const cross = svg("line", { y1: T, y2: H - B, class: "crosshair", visibility: "hidden" });
  const hover = svg("circle", { r: 4, class: "dot", visibility: "hidden" });
  root.append(cross, hover);

  root.addEventListener("pointermove", (e) => {
    const box = root.getBoundingClientRect();
    const x = ((e.clientX - box.left) / box.width) * W;
    let best = pts[0];
    for (const p of pts) if (Math.abs(sx(p.x) - x) < Math.abs(sx(best.x) - x)) best = p;
    cross.setAttribute("x1", sx(best.x));
    cross.setAttribute("x2", sx(best.x));
    hover.setAttribute("cx", sx(best.x));
    hover.setAttribute("cy", sy(best.y));
    cross.setAttribute("visibility", "visible");
    hover.setAttribute("visibility", "visible");
    tip([el("b", {}, `${best.y.toFixed(2)} ${yUnit}`), el("br"), `${xName} ${best.x}`,
      best.label ? el("br") : null, best.label ? pretty(best.label) : null].filter(Boolean), e.clientX, e.clientY);
  });
  root.addEventListener("pointerleave", () => {
    cross.setAttribute("visibility", "hidden");
    hover.setAttribute("visibility", "hidden");
    untip();
  });
  host.append(root);
}

function niceMax(v) {
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

// ── Stat tiles ───────────────────────────────────────────────────────────────

export function tiles(host, list) {
  host.replaceChildren(...list.map(([label, value]) =>
    el("div", { class: "tile" }, el("div", { class: "tile-label" }, label), el("div", { class: "tile-value" }, value))));
}
