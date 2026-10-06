// Keeps the app opening without a network (it then says the server is offline).
// Pages and scripts: network first, so a new version shows at once.
// The Supabase library from the CDN: cache first. API calls are never cached.
const CACHE = "walksafe-v3";
const SHELL = [
  "./", "index.html", "manifest.webmanifest", "css/app.css",
  "js/app.js", "js/config.js", "js/supabase.js", "js/ui.js", "js/server.js",
  "js/speech.js", "js/guide.js", "js/admin.js", "js/charts.js",
  "icons/icon-192.png", "icons/icon-512.png", "icons/logo.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (url.hostname === "cdn.jsdelivr.net") {
    e.respondWith(caches.match(req).then((hit) => hit || fetchAndKeep(req)));
    return;
  }
  if (url.origin !== self.location.origin || url.pathname.includes("/api/")) return;
  e.respondWith(fetchAndKeep(req).catch(() => caches.match(req, { ignoreSearch: true })));
});

async function fetchAndKeep(req) {
  const res = await fetch(req);
  if (res.ok) {
    const copy = res.clone();
    caches.open(CACHE).then((c) => c.put(req, copy));
  }
  return res;
}
