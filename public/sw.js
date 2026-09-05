const CACHE_NAME = "blood-request-shell-v2-design";
const OFFLINE_URL = "/offline";
const SHELL_URLS = [
  "/offline",
  "/manifest.webmanifest",
  "/icon.svg",
  "/icons/icon-192",
  "/icons/icon-512",
  "/icons/icon-512-maskable",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(SHELL_URLS);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key.startsWith("blood-request-shell-") && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ).then(() => self.clients.claim());
    })
  );
});

function isShellAsset(url) {
  return !url.search && (SHELL_URLS.includes(url.pathname) || url.pathname.startsWith("/_next/static/"));
}

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }

  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request, { cache: "no-store" }).catch(async () => {
        return (await caches.match(OFFLINE_URL)) || Response.error();
      })
    );
    return;
  }

  // Default to network-only, including RSC payloads, APIs and future data routes.
  if (!isShellAsset(url) || event.request.headers.get("RSC") === "1") {
    event.respondWith(
      fetch(event.request, { cache: "no-store" }).catch(() => new Response(
        JSON.stringify({ error: "Offline", message: "Network connection is required for data operations." }),
        { status: 503, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } }
      ))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(event.request).then(async (response) => {
        if (response.ok && response.type === "basic" && !response.redirected) {
          const copy = response.clone();
          try {
            await (await caches.open(CACHE_NAME)).put(event.request, copy);
          } catch {
            // A full cache must not prevent the network response from loading.
          }
        }
        return response;
      });
    })
  );
});
