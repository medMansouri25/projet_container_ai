// backend-api.js — unique point d'appel vers le backend Flask local.
// Aucun autre fichier de l'extension n'appelle fetch() directement : toute
// la connaissance des routes /api/labo/* est concentrée ici. Le backend
// Python reste le seul moteur YOLO/OCR — ce module ne fait que relayer.

export class BackendApi {
  constructor(baseUrl) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  /** Sert aussi de "health check" : /api/labo/models répond 200 dès que le
   * backend est up, pas besoin d'un endpoint dédié pour ça. */
  async health() {
    const r = await fetch(`${this.baseUrl}/api/labo/models`);
    if (!r.ok) throw new Error(`backend indisponible (HTTP ${r.status})`);
    return true;
  }

  async models() {
    const r = await fetch(`${this.baseUrl}/api/labo/models`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json(); // { models, ocr_engines }
  }

  async rtspConnect(url) {
    const fd = new FormData();
    fd.append("url", url);
    const r = await fetch(`${this.baseUrl}/api/labo/rtsp/connect`, { method: "POST", body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    return d; // { session, connected, resolution, fps }
  }

  async rtspStatus(session) {
    const r = await fetch(`${this.baseUrl}/api/labo/rtsp/status/${session}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    return d; // { connected, error, resolution, fps, recording }
  }

  /** Pas de fetch ici : l'URL est utilisée directement en src= d'une <img>
   * (flux MJPEG multipart, le navigateur le consomme nativement). */
  rtspPreviewUrl(session) {
    return `${this.baseUrl}/api/labo/rtsp/preview/${session}?t=${Date.now()}`;
  }

  async rtspRecordStart(session) {
    const fd = new FormData();
    fd.append("session", session);
    const r = await fetch(`${this.baseUrl}/api/labo/rtsp/record/start`, { method: "POST", body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    return d; // { recording }
  }

  async rtspRecordStop(session) {
    const fd = new FormData();
    fd.append("session", session);
    const r = await fetch(`${this.baseUrl}/api/labo/rtsp/record/stop`, { method: "POST", body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    return d; // { recording, seconds, frames }
  }

  async rtspDisconnect(session) {
    const fd = new FormData();
    fd.append("session", session);
    await fetch(`${this.baseUrl}/api/labo/rtsp/disconnect`, { method: "POST", body: fd });
  }

  /** Analyse vidéo (pipeline existant, réutilisé tel quel — Phase E).
   * onEvent(evt) est appelé pour chaque ligne NDJSON reçue
   * ({type:"meta"|"progress"|"done"|"error", ...}). */
  async detectVideo({ recording, modelId, ocrEngine }, onEvent) {
    const fd = new FormData();
    fd.append("recording", recording);
    fd.append("model_id", modelId);
    fd.append("ocr_engine", ocrEngine || "easyocr");
    const r = await fetch(`${this.baseUrl}/api/labo/detect-video`, { method: "POST", body: fd });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      throw new Error(d.error || `HTTP ${r.status}`);
    }
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) onEvent(JSON.parse(line));
      }
    }
  }
}
