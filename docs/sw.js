// Offline support. Every file is saved on install, so the app works offline from the
// first visit. Requests are answered from the cache straight away (fast, works offline)
// and refreshed in the background, so newly pushed chapters show up on the next open.
const CACHE = "svenska-v8";
const FILES = ["./", "index.html", "cards.json", "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(event.request, { ignoreSearch: true });
      const fresh = fetch(event.request)
        .then((resp) => { if (resp.ok) cache.put(event.request, resp.clone()); return resp; })
        .catch(() => cached);
      if (cached) {
        event.waitUntil(fresh);
        return cached;
      }
      return fresh;
    })
  );
});
