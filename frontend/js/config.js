/* Configuration du front statique (Vercel).
   L'URL du backend (quick tunnel Cloudflare) change a chaque redemarrage
   du VPS : elle est publiee automatiquement dans api_base.txt sur GitHub
   par le service tunnel du VPS. Le front la resout au chargement. */

const API_BASE_SOURCE =
  "https://raw.githubusercontent.com/medMansouri25/ProjetContainer_AI/main/api_base.txt";
const API_BASE_FALLBACK = "https://sympathy-recently-roles-cellular.trycloudflare.com";

let _apiBase = null;

async function apiBase() {
  if (_apiBase) return _apiBase;
  try {
    const r = await fetch(`${API_BASE_SOURCE}?t=${Date.now()}`, { cache: "no-store" });
    if (r.ok) {
      const url = (await r.text()).trim().replace(/\/$/, "");
      if (url.startsWith("https://")) _apiBase = url;
    }
  } catch (e) { /* GitHub inaccessible : fallback */ }
  if (!_apiBase) _apiBase = API_BASE_FALLBACK;
  return _apiBase;
}
