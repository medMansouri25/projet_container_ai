/* sw.js — Service Worker : cache des modèles ONNX (gros fichiers, chargés une fois).
   Stratégie : cache-first pour *.onnx, réseau pour tout le reste.
   Mise à jour : changer CACHE_NAME force un re-téléchargement des modèles. */

const CACHE_NAME = "smartcontainer-models-v1";
const ONNX_PATTERN = /\.onnx(\?|$)/;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(clients.claim()));

self.addEventListener("fetch", (e) => {
  if (!ONNX_PATTERN.test(e.request.url)) return;   // laisse passer tout le reste

  e.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(e.request);
      if (cached) return cached;

      // Première fois : télécharge ET met en cache
      const response = await fetch(e.request);
      if (response.ok) cache.put(e.request, response.clone());
      return response;
    })
  );
});
