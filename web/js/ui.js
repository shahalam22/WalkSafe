export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// el("button", { class: "btn", onclick: fn }, "Text")
export function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid != null && kid !== false) node.append(kid instanceof Node ? kid : String(kid));
  }
  return node;
}

export function showScreen(id) {
  for (const s of $$("[data-screen]")) s.hidden = s.id !== id;
}

// For screen readers: text put here is read out.
export function announce(text) {
  const live = $("#live");
  live.textContent = "";
  setTimeout(() => { live.textContent = text; }, 50);
}

// Per-phone settings.
export const prefs = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem(`walksafe-${key}`);
      return v === null ? fallback : JSON.parse(v);
    } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`walksafe-${key}`, JSON.stringify(value)); } catch { /* private mode */ }
  },
};

// Chrome's "install app" prompt, kept until the helper asks for it.
let installEvent = null;
addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  installEvent = e;
  document.dispatchEvent(new Event("walksafe-installable"));
});
export const canInstall = () => installEvent !== null;
export async function install() {
  if (!installEvent) return false;
  installEvent.prompt();
  const { outcome } = await installEvent.userChoice;
  installEvent = null;
  return outcome === "accepted";
}

export const fmtDateTime = (iso) => iso
  ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";

export function fmtDuration(startIso, endIso) {
  if (!startIso || !endIso) return "—";
  const s = Math.max(0, (new Date(endIso) - new Date(startIso)) / 1000);
  if (s < 60) return `${Math.round(s)} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
  return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
}

export const fmtNum = (n) => (n == null ? "—" : Number(n).toLocaleString());
export const pretty = (s) => (s ?? "—").toString().replaceAll("_", " ");
