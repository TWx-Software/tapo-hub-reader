const CACHE_NAME = "tapo-hub-reader-shell-v1";
const APP_SHELL = [
  "/",
  "/static/manifest.webmanifest",
  "/static/style.css",
  "/static/app.js",
  "/static/app-icon.svg",
  "/static/app-icon-192.png",
  "/static/app-icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys();
      await Promise.all(
        cacheNames
          .filter((name) => name.startsWith("tapo-hub-reader-shell-") && name !== CACHE_NAME)
          .map((name) => caches.delete(name)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // Never cache measurements: they are private and should always be fresh.
  if (url.pathname === "/api/devices") {
    event.respondWith(
      fetch(request, { cache: "no-store" }).catch(
        () =>
          new Response(JSON.stringify({ error: "Offline: live sensor data is unavailable." }), {
            status: 503,
            headers: {
              "Content-Type": "application/json",
              "Cache-Control": "no-store",
            },
          }),
      ),
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            return caches.open(CACHE_NAME).then((cache) => {
              cache.put("/", response.clone());
              return response;
            });
          }
          return response;
        })
        .catch(async () => (await caches.match("/")) || Response.error()),
    );
    return;
  }

  event.respondWith(
    (async () => {
      const cached = await caches.match(request);
      try {
        const response = await fetch(request);
        if (response.ok) {
          await caches.open(CACHE_NAME).then((cache) =>
            cache.put(request, response.clone()),
          );
        }
        return response;
      } catch {
        return cached || Response.error();
      }
    })(),
  );
});
