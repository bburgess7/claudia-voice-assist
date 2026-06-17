// PWA shell cache. Network-first for the HTML document and API (always fresh), cache-first only for
// truly static assets (icons/manifest). This avoids serving a stale index.html after updates.
const CACHE = "claudia-v2";
const STATIC = ["/manifest.webmanifest", "/icon-180.png", "/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;                                   // never cache mutations
  const url = new URL(req.url);
  if (/\/(config|voices|health|ws|speak|say|stop)/.test(url.pathname)) return;  // always live
  // HTML document: network-first, fall back to cache offline.
  if (req.mode === "navigate" || url.pathname === "/" || url.pathname.endsWith(".html")) {
    e.respondWith(fetch(req).then(r => {
      const copy = r.clone(); caches.open(CACHE).then(c => c.put("/", copy)); return r;
    }).catch(() => caches.match("/")));
    return;
  }
  // static assets: cache-first.
  e.respondWith(caches.match(req).then(r => r || fetch(req)));
});
