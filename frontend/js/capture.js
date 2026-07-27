/* capture.js — écran de capture multi-source.
   MODE FICHIER  : image → OCR direct serveur | vidéo → preview + capture manuelle.
   MODE CAMÉRA   : ANPR continu — YOLO tourne en boucle, chaque bonne détection
                   déclenche un OCR silencieux en arrière-plan, la caméra ne s'arrête
                   jamais. Les résultats s'accumulent dans le log de détections. */

import { loadSession, detect, MODELS } from "./webdetect.js";

const el = (id) => document.getElementById(id);
const overlay = el("overlay");
const octx    = overlay.getContext("2d");
const video   = el("video");
const photo   = el("photo");

const state = {
  target:       "conteneur",
  sessions:     {},
  stream:       null,
  rafId:        null,
  goodStreak:   0,
  captured:     null,        // {source, w, h}
  detectedBox:  null,        // meilleure boîte YOLO du dernier frame
  videoMode:    false,
  previewOnly:  false,
  cameraMode:   false,       // true = flux caméra continu (ANPR)
  cooldownUntil: 0,          // ms : auto-capture inhibée jusqu'à ce timestamp
  ocrPending:   0,           // nb de requêtes OCR en vol
  dossierId:    null,        // dossier de passage courant (Mission 6)
};

const OCR = {
  conteneur: { endpoint: "/api/scan",        cropEndpoint: "/api/ocr-crop",         field: "bic",    label: "Code ISO (BIC)" },
  plaque:    { endpoint: "/api/scan-plaque", cropEndpoint: "/api/ocr-plaque-crop",  field: "plaque", label: "Immatriculation" },
};

const CLASS_NAMES = {
  conteneur: ["code bic"],
  plaque:    ["Plaque"],
};
// Couleur par cible : jaune pour BIC, bleu pour plaque
const BOX_COLORS = {
  conteneur: ["#FFD700"],
  plaque:    ["#3b82f6"],
};

const showError  = (m) => { const a = el("error-alert"); a.textContent = m; a.hidden = false; };
const clearError = ()  => { el("error-alert").hidden = true; };
const T = (k) => (window.i18n ? window.i18n.t(k) : k);

function setGuide(s) {
  const g = el("guide");
  g.className = "g-" + s;
  const MAP = { aucun: "aucun objet", trop_loin: "trop loin — approchez",
                trop_pres: "trop près — reculez", bon: "bien cadré ✓" };
  g.textContent = MAP[s] || s;
}

/* ── Sélecteur d'entité ── */
el("target-seg").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  state.target = b.dataset.target;
  el("target-seg").querySelectorAll("[data-target]").forEach((c) =>
    c.setAttribute("aria-pressed", String(c === b)));
  reset();
});

/* ── Modèle (lazy, par cible) ── */
async function session() {
  if (!state.sessions[state.target]) {
    const url    = MODELS[state.target].url;
    const cached = await modelIsCached(url);
    let sizeLabel = "";
    if (!cached) {
      try {
        const head = await fetch(url, { method: "HEAD" });
        const bytes = parseInt(head.headers.get("content-length") || "0", 10);
        if (bytes > 0) sizeLabel = ` (~${(bytes / 1_048_576).toFixed(1)} Mo)`;
      } catch { /* taille inconnue, pas bloquant */ }
    }
    el("model-status").textContent = cached
      ? "chargement depuis le cache…"
      : `1er téléchargement YOLO${sizeLabel} — une seule fois…`;
    state.sessions[state.target] = await loadSession(MODELS[state.target].url);
    el("model-status").textContent = "";
  }
  return state.sessions[state.target];
}

async function modelIsCached(url) {
  if (!("caches" in window)) return false;
  try {
    const abs = new URL(url, location.href).href;
    return !!(await caches.match(abs));
  } catch { return false; }
}
const numClasses = () => MODELS[state.target].numClasses;

/* ── Dessin ── */
function drawFrame(source, w, h, boxes = []) {
  if (!w || !h) return;
  overlay.width  = w;
  overlay.height = h;
  octx.drawImage(source, 0, 0, w, h);

  const names = CLASS_NAMES[state.target] || [];
  const lw    = Math.max(2, w / 200);
  const fs    = Math.max(13, Math.round(w / 42));

  const palette = BOX_COLORS[state.target] || ["#FFD700"];
  for (const box of (Array.isArray(boxes) ? boxes : [])) {
    const color = palette[(box.cls || 0) % palette.length];
    const label = names[box.cls || 0] || "?";

    // Boîte arrondie
    const r = lw * 3;
    octx.strokeStyle = color; octx.lineWidth = lw;
    octx.beginPath();
    octx.moveTo(box.x + r, box.y);
    octx.lineTo(box.x + box.w - r, box.y);
    octx.quadraticCurveTo(box.x + box.w, box.y, box.x + box.w, box.y + r);
    octx.lineTo(box.x + box.w, box.y + box.h - r);
    octx.quadraticCurveTo(box.x + box.w, box.y + box.h, box.x + box.w - r, box.y + box.h);
    octx.lineTo(box.x + r, box.y + box.h);
    octx.quadraticCurveTo(box.x, box.y + box.h, box.x, box.y + box.h - r);
    octx.lineTo(box.x, box.y + r);
    octx.quadraticCurveTo(box.x, box.y, box.x + r, box.y);
    octx.closePath();
    octx.stroke();

    // Label (fond couleur + texte noir)
    octx.font = `bold ${fs}px monospace`;
    const tw  = octx.measureText(label).width;
    const lh  = fs + 6;
    const lx  = box.x;
    const ly  = box.y > lh + 4 ? box.y - lh - 2 : box.y + box.h + 2;
    octx.fillStyle = color;
    octx.beginPath();
    octx.roundRect(lx, ly, tw + 10, lh, 4);
    octx.fill();
    octx.fillStyle = "#000";
    octx.fillText(label, lx + 5, ly + fs - 1);
  }
}

/* Flash blanc : signal visuel d'une capture automatique. */
function flashCapture() {
  const W = overlay.width, H = overlay.height;
  octx.fillStyle = "rgba(255,255,255,0.45)";
  octx.fillRect(0, 0, W, H);
}

function showActions() { el("action-row").hidden = false; }

/* ── Crop plaque détectée → OCR serveur sur la zone limitée ── */
async function cropAndOcrPlaque(img, box) {
  const pad = 0.06;
  const W = img.naturalWidth, H = img.naturalHeight;
  const cx = Math.max(0, box.x - box.w * pad);
  const cy = Math.max(0, box.y - box.h * pad);
  const cw = Math.min(W - cx, box.w * (1 + 2 * pad));
  const ch = Math.min(H - cy, box.h * (1 + 2 * pad));

  const cv = document.createElement("canvas");
  cv.width = Math.round(cw); cv.height = Math.round(ch);
  cv.getContext("2d").drawImage(img, cx, cy, cw, ch, 0, 0, cv.width, cv.height);

  return new Promise((resolve) => {
    cv.toBlob(async blob => {
      try {
        const fd = new FormData();
        fd.append("image", new File([blob], "plate_crop.jpg", { type: "image/jpeg" }));
        const r = await fetch(`${await window.apiBase()}/api/ocr-plaque-crop`,
          { method: "POST", body: fd });
        const data = await r.json();
        resolve(r.ok && data.plaque ? data : null);
      } catch { resolve(null); }
    }, "image/jpeg", 0.92);
  });
}

/* ── MODE 1 : Importer un fichier ── */
el("mode-import").addEventListener("click", () => el("file-input").click());

el("file-input").addEventListener("change", (e) => {
  const file = e.target.files[0]; if (!file) return;
  e.target.value = "";
  clearError(); reset();
  if (file.type.startsWith("video/"))      handleVideo(file);
  else if (file.type.startsWith("image/")) handlePhoto(file);
  else showError("Type de fichier non supporté : " + file.type);
});

async function handlePhoto(file) {
  showActions();
  photo.src = URL.createObjectURL(file);
  await photo.decode();
  drawFrame(photo, photo.naturalWidth, photo.naturalHeight, []);
  setGuide("aucun");

  // Détection YOLO locale : dessine les boîtes avant l'OCR
  try {
    const s = await session();
    const conf = state.target === "plaque" ? 0.15 : 0.25;
    const { box, boxes } = await detect(s, photo, photo.naturalWidth, photo.naturalHeight,
      { numClasses: numClasses(), conf });
    if (boxes.length) {
      drawFrame(photo, photo.naturalWidth, photo.naturalHeight, boxes);
      setGuide("bon");
    }
    // Plaque : crop de la zone détectée → OCR sur le crop uniquement
    if (state.target === "plaque" && box) {
      el("model-status").textContent = "lecture OCR sur la zone plaque…";
      const cropResult = await cropAndOcrPlaque(photo, box);
      el("model-status").textContent = "";
      if (cropResult) { showProposal(cropResult); return; }
    }
  } catch (e) {
    console.warn("[capture] YOLO local indisponible :", e.message);
  }

  await runOcr(file);
}

async function handleVideo(file) {
  showActions();
  state.videoMode = true;
  video.src = URL.createObjectURL(file);
  await new Promise((r) => video.addEventListener("loadeddata", r, { once: true }));
  el("capture-btn").hidden = false;
  el("stop-btn").hidden    = false;
  video.play();
  loopVideoPreview();
}

function loopVideoPreview() {
  const tick = () => {
    if (!state.videoMode || video.ended || video.paused) {
      el("stop-btn").hidden = true; return;
    }
    if (video.videoWidth && video.videoHeight) {
      drawFrame(video, video.videoWidth, video.videoHeight, []);
      state.captured = { source: video, w: video.videoWidth, h: video.videoHeight };
    }
    state.rafId = requestAnimationFrame(tick);
  };
  tick();
}

/* ── MODE 3 : Caméra temps réel (ANPR continu) ── */
el("mode-realtime").addEventListener("click", async () => {
  clearError(); reset(); showActions();
  state.cameraMode = true;

  // Bouton : "Forcer la capture" au lieu de "Capturer cette image"
  el("capture-btn-label").textContent = "Forcer la capture";

  // Afficher le panneau de log dès maintenant (vide)
  el("detection-log").hidden = false;
  el("det-count").textContent = "0";

  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 } },
    });
    video.srcObject = state.stream;
    await video.play();
    el("capture-btn").hidden = false;
    el("stop-btn").hidden    = false;

    startCameraPreview();

    const s = await session();
    el("model-status").textContent = "modèle prêt ✓";
    setTimeout(() => {
      if (!state.ocrPending) el("model-status").textContent = "";
    }, 2000);
    state.previewOnly = false;
    loopWebcam(s);
  } catch (err) { showError("Caméra inaccessible : " + err.message); }
});

function startCameraPreview() {
  state.previewOnly = true;
  const tick = () => {
    if (!state.stream || !state.previewOnly) return;
    if (video.videoWidth && video.videoHeight) {
      overlay.width  = video.videoWidth;
      overlay.height = video.videoHeight;
      octx.drawImage(video, 0, 0);
      state.captured = { source: video, w: video.videoWidth, h: video.videoHeight };
    }
    requestAnimationFrame(tick);
  };
  tick();
}

/* Boucle YOLO caméra — ne s'arrête jamais sur détection réussie (mode ANPR). */
async function loopWebcam(s) {
  const tick = async () => {
    if (!state.stream) return;
    if (!video.videoWidth || !video.videoHeight) {
      state.rafId = requestAnimationFrame(tick); return;
    }
    const conf = state.target === "plaque" ? 0.15 : 0.25;
    const res = await detect(s, video, video.videoWidth, video.videoHeight,
                             { numClasses: numClasses(), conf });
    drawFrame(video, video.videoWidth, video.videoHeight, res.boxes);
    setGuide(res.guide.state);
    state.captured    = { source: video, w: video.videoWidth, h: video.videoHeight };
    state.detectedBox = res.box;
    state.goodStreak = res.guide.capture ? state.goodStreak + 1 : 0;
    if (state.goodStreak >= 5) {
      state.goodStreak = 0;
      autoCapture();   // pas de await : la caméra continue sans attendre l'OCR
    }
    state.rafId = requestAnimationFrame(tick);
  };
  tick();
}

/* ── Auto-capture ANPR : snapshot silencieux → OCR en arrière-plan ── */
async function autoCapture() {
  if (!state.captured) return;
  if (Date.now() < state.cooldownUntil) return;   // évite de recapturer le même objet
  state.cooldownUntil = Date.now() + 3500;         // cooldown 3,5 s

  flashCapture();

  const { source, w, h } = state.captured;
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  c.getContext("2d").drawImage(source, 0, 0, w, h);

  const cfg = OCR[state.target];
  const box = state.detectedBox;

  // Crop de la zone détectée si une boîte YOLO est disponible
  let blob;
  let endpoint = cfg.endpoint;
  if (box) {
    const pad = 0.06;
    const cx = Math.max(0, box.x - box.w * pad);
    const cy = Math.max(0, box.y - box.h * pad);
    const cw = Math.min(w - cx, box.w * (1 + 2 * pad));
    const ch = Math.min(h - cy, box.h * (1 + 2 * pad));
    const cc = document.createElement("canvas");
    cc.width = Math.round(cw); cc.height = Math.round(ch);
    cc.getContext("2d").drawImage(c, cx, cy, cw, ch, 0, 0, cc.width, cc.height);
    blob     = await new Promise((r) => cc.toBlob(r, "image/jpeg", 0.92));
    endpoint = cfg.cropEndpoint;
  } else {
    blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.92));
  }

  state.ocrPending++;
  el("ocr-status").textContent = `OCR en cours… (${state.ocrPending})`;

  try {
    const fd = new FormData();
    fd.append("image", blob, "capture.jpg");
    const r    = await fetch(`${await window.apiBase()}${endpoint}`, { method: "POST", body: fd });
    const data = await r.json();
    if (r.ok && data[cfg.field]) addToLog(data);
  } catch { /* échec silencieux — la caméra continue */ }

  state.ocrPending--;
  el("ocr-status").textContent = state.ocrPending > 0 ? `OCR en cours… (${state.ocrPending})` : "";
}

/* ── Log de détections ANPR ── */
function addToLog(data) {
  const cfg   = OCR[state.target];
  const value = data[cfg.field] || "";
  if (!value) return;

  const ts = new Date().toLocaleTimeString("fr-FR",
    { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  const list  = el("log-list");
  const count = list.children.length + 1;
  el("det-count").textContent = count;

  const card = document.createElement("div");
  card.className = `det-card ${data.valid ? "det-ok" : "det-warn"}`;
  const badges = [
    data.valid
      ? `<span class="badge badge-ok">${T("badge.valid")}</span>`
      : `<span class="badge badge-warn">${T("badge.check")}</span>`,
    data.corrected ? `<span class="badge badge-warn">${T("badge.recalc")}</span>` : "",
  ].join("");
  card.innerHTML =
    `<span class="det-time">${ts}</span>` +
    `<span class="det-val">${value}</span>` +
    `<span class="det-badges">${badges}</span>` +
    `<button class="btn btn-sm det-confirm" data-value="${value}">Confirmer</button>`;

  list.prepend(card);

  // Mettre à jour aussi la section résultat (dernière détection)
  el("value-label").textContent = cfg.label;
  el("value-input").value       = value;
  el("result-raw").textContent  = data.raw_text ? "OCR brut : " + data.raw_text : "";
  el("result-badges").innerHTML = badges;
  el("result-section").hidden   = false;
}

/* Confirmer depuis une carte du log. */
el("log-list") && el("log-list").addEventListener("click", (e) => {
  const btn = e.target.closest(".det-confirm"); if (!btn) return;
  el("value-input").value = btn.dataset.value;
  doConfirm();
});

/* ── Bouton Capturer (dual-mode) ── */
el("capture-btn").addEventListener("click", () => {
  if (state.cameraMode) {
    // Mode ANPR : force une capture immédiate (bypass cooldown)
    state.cooldownUntil = 0;
    autoCapture();
  } else {
    doCapture();
  }
});

el("stop-btn").addEventListener("click", reset);

/* ── Capture manuelle (fichier/vidéo) → OCR serveur ── */
async function doCapture() {
  if (!state.captured) return;
  stopLive();
  const { source, w, h } = state.captured;
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  c.getContext("2d").drawImage(source, 0, 0, w, h);
  const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.92));
  await runOcr(blob);
}

async function runOcr(blob) {
  const cfg = OCR[state.target];
  el("model-status").textContent = "lecture OCR (serveur)…";
  try {
    const fd = new FormData();
    fd.append("image", blob, "capture.jpg");
    const r    = await fetch(`${await window.apiBase()}${cfg.endpoint}`, { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Erreur serveur");
    showProposal(data);
  } catch (err) {
    showError("Lecture impossible : " + err.message + " (le backend est-il joignable ?)");
  } finally {
    el("model-status").textContent = "";
  }
}

function showProposal(data) {
  const cfg = OCR[state.target];
  el("result-section").hidden   = false;
  el("value-label").textContent = cfg.label;
  el("value-input").value       = data[cfg.field] || "";
  el("result-raw").textContent  = data.raw_text ? "OCR brut : " + data.raw_text : "";
  const badges = [];
  badges.push(data.valid
    ? `<span class="badge badge-ok">${T("badge.valid")}</span>`
    : `<span class="badge badge-warn">${T("badge.check")}</span>`);
  if (data.corrected) badges.push(`<span class="badge badge-warn">${T("badge.recalc")}</span>`);
  el("result-badges").innerHTML = badges.join(" ");
}

/* ── Confirmer → rattacher au dossier de passage ── */
el("confirm-btn").addEventListener("click", doConfirm);

async function doConfirm() {
  const value = el("value-input").value.trim();
  if (!value) return;
  clearError();
  el("confirm-btn").disabled = true;
  try {
    const r = await fetch(`${await window.apiBase()}/api/passage/confirmer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target:     state.target,
        valeur:     value,
        dossier_id: state.dossierId || undefined,
      }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Erreur serveur");
    state.dossierId = data.dossier_id;
    renderDossier(data.dossier);
  } catch (err) {
    showError("Rattachement impossible : " + err.message);
  } finally {
    el("confirm-btn").disabled = false;
  }
}

/* ── Dossier de passage (Mission 6) ── */

function renderDossier(dossier) {
  const d = el("dossier-section");
  d.hidden = false;

  const conteneur = dossier.conteneur;
  const camion    = dossier.camion;
  const hasEntity = !!(conteneur || camion);
  const valide    = dossier.statut === "valide";

  el("dossier-ref").textContent  = `#${dossier.id}`;
  el("dossier-badge").textContent = valide ? "validé" : "en attente";
  el("dossier-badge").className   = "badge " + (valide ? "badge-ok" : "badge-warn");
  el("dossier-vide").hidden       = hasEntity;

  el("entity-conteneur").hidden = !conteneur;
  el("entity-camion").hidden    = !camion;
  if (conteneur) el("entity-bic").textContent   = conteneur.code_iso;
  if (camion)    el("entity-plaque").textContent = camion.immatriculation;

  el("valider-passage-btn").hidden  = valide || !hasEntity;
  el("attente-btn").hidden          = valide;
  el("abandon-btn").hidden          = valide;
  el("nouveau-passage-btn").hidden  = false;
  el("dossier-msg").textContent     = valide
    ? `Passage #${dossier.id} enregistré.` : "";
}

el("valider-passage-btn").addEventListener("click", async () => {
  if (!state.dossierId) return;
  try {
    const r = await fetch(
      `${await window.apiBase()}/api/dossiers/${state.dossierId}/validate`,
      { method: "POST" });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error);
    el("dossier-badge").textContent = "validé";
    el("dossier-badge").className   = "badge badge-ok";
    el("valider-passage-btn").hidden = true;
    el("attente-btn").hidden         = true;
    el("abandon-btn").hidden         = true;
    el("dossier-msg").textContent    = `Passage #${state.dossierId} enregistré.`;
    state.dossierId = null;   // prochain Confirmer = nouveau dossier
  } catch (err) { showError("Validation impossible : " + err.message); }
});

el("attente-btn").addEventListener("click", () => {
  // Le dossier reste en base (en_attente) — l'agent le retrouvera dans l'historique.
  state.dossierId = null;
  el("dossier-section").hidden = true;
});

el("abandon-btn").addEventListener("click", async () => {
  if (!state.dossierId) { el("dossier-section").hidden = true; return; }
  try {
    await fetch(
      `${await window.apiBase()}/api/dossiers/${state.dossierId}/abandon`,
      { method: "POST" });
  } catch { /* abandon best-effort */ }
  state.dossierId = null;
  el("dossier-section").hidden = true;
});

el("nouveau-passage-btn").addEventListener("click", () => {
  state.dossierId = null;
  el("dossier-section").hidden = true;
  el("dossier-msg").textContent = "";
});

el("again-btn").addEventListener("click", reset);

/* ── Utilitaires ── */
function stopLive() {
  if (state.rafId) { cancelAnimationFrame(state.rafId); state.rafId = null; }
  if (state.stream) { state.stream.getTracks().forEach((t) => t.stop()); state.stream = null; }
  if (state.videoMode) { video.pause(); video.src = ""; state.videoMode = false; }
  el("stop-btn").hidden = true;
}

function reset() {
  stopLive();
  state.captured      = null;
  state.detectedBox   = null;
  state.goodStreak    = 0;
  state.previewOnly   = false;
  state.cameraMode    = false;
  state.cooldownUntil = 0;
  state.ocrPending    = 0;
  el("result-section").hidden  = true;
  el("detection-log").hidden   = true;
  el("capture-btn").hidden     = true;
  el("action-row").hidden      = true;
  el("log-list").innerHTML     = "";
  el("det-count").textContent  = "0";
  el("ocr-status").textContent = "";
  el("capture-btn-label").textContent = "Capturer cette image";
  octx.clearRect(0, 0, overlay.width, overlay.height);
  setGuide("aucun");
}

reset();

/* ── Reprise d'un dossier existant via ?dossier_id=X ── */
(async () => {
  const id = new URLSearchParams(window.location.search).get("dossier_id");
  if (!id) return;
  try {
    const r = await fetch(`${await window.apiBase()}/api/dossiers/${id}`);
    if (!r.ok) return;
    const data = await r.json();
    state.dossierId = data.id;
    renderDossier(data);
  } catch { /* reprise silencieuse si le dossier est inaccessible */ }
})();
