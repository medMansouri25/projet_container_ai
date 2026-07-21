/* Configuration du front statique (Vercel).
   Le backend (Flask + YOLO + OCR) tourne sur le VPS, expose en HTTPS
   par Caddy sur le domaine fixe ci-dessous. */

const API_BASE = "https://api.containerai-marsa-maroc.online";

async function apiBase() {
  return API_BASE;
}

/* Service Worker — cache les modèles ONNX (77 MB + 37 MB) après le premier
   téléchargement. Les visites suivantes chargent depuis le disque local. */
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
