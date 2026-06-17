// Minimal app-shell cache so Claudia installs and opens instantly. Network-first for /config,
// /voices, /health (always fresh state); cache-first for the static shell.
const CACHE = "claudia-v1";
const SHELL = ["/", "/manifest.webmanifest", "/icon-180.png", "/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;                 // never cache POSTs
  if (/\/(config|voices|health|ws)/.test(url.pathname)) return;  // always live
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
