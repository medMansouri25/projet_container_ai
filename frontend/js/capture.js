/* capture.js — écran de capture multi-source.
   MODE FICHIER  : image → OCR direct serveur | vidéo → preview + capture manuelle.
   MODE CAMÉRA   : ANPR continu — YOLO tourne en boucle, chaque bonne détection
                   déclenche un OCR silencieux en arrière-plan, la caméra ne s'arrête
                   jamais. Les résultats s'accumulent dans le log de détections. */

import { loadSession, loadSessionWithProgress, detect, MODELS } from "./webdetect.js";

const el = (id) => document.getElementById(id);
const overlay = el("overlay");
const octx    = overlay.getContext("2d");
const video   = el("video");
const photo   = el("photo");

const state = {
  target:        "conteneur",
  sessions:      {},
  stream:        null,
  rafId:         null,
  goodStreak:    0,
  captured:      null,        // {source, w, h}
  detectedBox:   null,        // meilleure boîte YOLO du dernier frame
  videoMode:     false,
  previewOnly:   false,
  cameraMode:    false,       // true = flux caméra continu (ANPR)
  cooldownUntil: 0,           // ms : auto-capture inhibée jusqu'à ce timestamp
  ocrPending:    0,           // nb de requêtes OCR en vol
  dossierId:     null,        // dossier de passage courant (Mission 6)
  allBoxes:      {},          // { conteneur: box|null, plaque: box|null } — dernier frame
  lastFrameBoxes: [],         // toutes les boîtes annotées du dernier frame (re-dessin sur freeze)
  annotatedUrl:  null,        // data URL du canvas annoté après import photo
};

const OCR = {
  conteneur: { endpoint: "/api/scan",        cropEndpoint: "/api/ocr-crop",         field: "bic",    label: "Code ISO (BIC)" },
  plaque:    { endpoint: "/api/scan-plaque", cropEndpoint: "/api/ocr-plaque-crop",  field: "plaque", label: "Immatriculation" },
};

const CLASS_NAMES = {
  conteneur: ["Conteneur"],
  plaque:    ["Plaque"],
};
// Couleur par cible/modèle
const BOX_COLORS = {
  conteneur: ["#f97316"],   // orange — zone conteneur
  plaque:    ["#3b82f6"],   // bleu   — zone plaque
};

// Config de tous les modèles de détection disponibles
// conteneur.onnx = détecteur de la caisse conteneur (zone orange)
// bic.onnx       = détecteur de la zone NumeroBIC  (zone jaune)
// plaque.onnx    = détecteur de la plaque           (zone bleue)
const DETECT_CFG = {
  conteneur: { numClasses: MODELS.conteneur.numClasses, label: "Conteneur", color: "#f97316", conf: 0.25 },
  bic:       { numClasses: MODELS.bic.numClasses,       label: "code bic",  color: "#FFD700", conf: 0.15 },
  plaque:    { numClasses: MODELS.plaque.numClasses,     label: "Plaque",    color: "#3b82f6", conf: 0.15 },
};

// Sessions secondaires (non-cible) chargées en arrière-plan
const extraSessions = {};
function loadExtraSessions() {
  Object.keys(DETECT_CFG).forEach(key => {
    if (key === state.target || extraSessions[key]) return;
    loadSession(MODELS[key].url)
      .then(s  => { extraSessions[key] = s; console.log(`[capture] +${key} chargé`); })
      .catch(() => {});
  });
}

const showError  = (m) => { const a = el("error-alert"); a.textContent = m; a.hidden = false; };
const clearError = ()  => { el("error-alert").hidden = true; };
const T = (k) => (window.i18n ? window.i18n.t(k) : k);

function setGuide(s) {
  const g = el("guide");
  g.className = "g-" + s;
  const MAP = { trop_loin: "trop loin — approchez",
                trop_pres: "trop près — reculez", bon: "bien cadré ✓" };
  g.textContent   = MAP[s] || "";
  g.style.display = s === "aucun" ? "none" : "";
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
    el("model-status").textContent = cached ? "chargement depuis le cache…" : "";
    showModelProgress(cached ? "Chargement du modèle IA…" : "Téléchargement du modèle IA…");
    try {
      state.sessions[state.target] = await loadSessionWithProgress(url, updateModelProgress);
    } catch (e) {
      hideModelProgress();
      el("model-status").textContent = "";
      showError(`Modèle « ${state.target} » indisponible (${e.message}). `
        + "Le fichier ONNX est-il présent et servi par le serveur ?");
      throw e;
    } finally {
      hideModelProgress();
      el("model-status").textContent = "";
    }
  }
  return state.sessions[state.target];
}

/* ── Barre de progression du téléchargement de modèle ── */
function showModelProgress(label) {
  const box = el("model-progress");
  if (!box) return;
  box.hidden = false;
  el("model-progress-label").textContent = label;
  el("model-progress-pct").textContent   = "0 %";
  const bar = el("model-progress-bar");
  bar.style.width = "0%";
  bar.classList.add("indeterminate");
}
function updateModelProgress(p) {
  const bar = el("model-progress-bar");
  if (!bar) return;
  if (p.indeterminate) {
    bar.classList.add("indeterminate");
    el("model-progress-pct").textContent = "…";
  } else {
    bar.classList.remove("indeterminate");
    bar.style.width = p.pct + "%";
    const mb = p.total ? ` (${(p.loaded / 1_048_576).toFixed(1)}/${(p.total / 1_048_576).toFixed(1)} Mo)` : "";
    el("model-progress-pct").textContent = p.pct + " %";
    el("model-progress-label").textContent = "Téléchargement du modèle IA…" + mb;
  }
}
function hideModelProgress() {
  const box = el("model-progress");
  if (box) box.hidden = true;
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
    const color = box.boxColor ?? palette[(box.cls || 0) % palette.length];
    const label = box.className ?? names[box.cls || 0] ?? "?";

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

/* ── Crop générique depuis un canvas → OCR serveur ── */
async function cropAndOcr(srcCanvas, box, endpoint) {
  const pad = 0.06;
  const W = srcCanvas.width, H = srcCanvas.height;
  const cx = Math.max(0, box.x - box.w * pad);
  const cy = Math.max(0, box.y - box.h * pad);
  const cw = Math.min(W - cx, box.w * (1 + 2 * pad));
  const ch = Math.min(H - cy, box.h * (1 + 2 * pad));
  const cc = document.createElement("canvas");
  cc.width  = Math.round(cw);
  cc.height = Math.round(ch);
  cc.getContext("2d").drawImage(srcCanvas, cx, cy, cw, ch, 0, 0, cc.width, cc.height);
  return new Promise(resolve => {
    cc.toBlob(async blob => {
      try {
        const fd = new FormData();
        fd.append("image", new File([blob], "crop.jpg", { type: "image/jpeg" }));
        const r = await fetch(`${await window.apiBase()}${endpoint}`, { method: "POST", body: fd });
        const data = await r.json();
        resolve(r.ok ? data : null);
      } catch { resolve(null); }
    }, "image/jpeg", 0.92);
  });
}

/* ── OCR sur plusieurs zones (multi-conteneurs) → liste de propositions ──
   Traite chaque boîte en parallèle (concurrence limitée) et affiche une carte
   par code lu dans le log de détections. Retourne le nombre de codes trouvés. */
async function ocrAllBoxes(srcCanvas, boxes, endpoint, field) {
  const MAX_BOXES = 20;           // garde-fou : au plus 20 zones OCR par image
  const CONCURRENCY = 4;          // 4 requêtes OCR simultanées max
  const sorted = [...boxes].sort((a, b) => (b.score || 0) - (a.score || 0)).slice(0, MAX_BOXES);

  // Préparer le log (multi-cartes)
  el("log-list").innerHTML = "";
  el("det-count").textContent = "0";
  el("detection-log").hidden = false;
  document.querySelector("#detection-log h2").textContent = "Codes détectés";

  let found = 0;
  const seen = new Set();          // évite les doublons de code
  let idx = 0;
  el("ocr-status").textContent = `OCR en cours… (0/${sorted.length})`;

  async function worker() {
    while (idx < sorted.length) {
      const my = idx++;
      const data = await cropAndOcr(srcCanvas, sorted[my], endpoint);
      const value = data && data[field];
      if (value && !seen.has(value)) {
        seen.add(value);
        found++;
        addProposalCard(value, data);
      }
      el("ocr-status").textContent = `OCR en cours… (${my + 1}/${sorted.length})`;
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  el("ocr-status").textContent = found
    ? `${found} code(s) détecté(s)` : "Aucun code lisible";
  return found;
}

/* Ajoute une carte « code détecté » dans le log, avec bouton Confirmer. */
function addProposalCard(value, data) {
  const list  = el("log-list");
  const count = list.children.length + 1;
  el("det-count").textContent = count;
  const badges = [
    data.valid
      ? `<span class="badge badge-ok">${T("badge.valid")}</span>`
      : `<span class="badge badge-warn">${T("badge.check")}</span>`,
    data.corrected ? `<span class="badge badge-warn">${T("badge.recalc")}</span>` : "",
  ].join("");
  const card = document.createElement("div");
  card.className = `det-card ${data.valid ? "det-ok" : "det-warn"}`;
  card.innerHTML =
    `<span class="det-val">${value}</span>` +
    `<span class="det-badges">${badges}</span>` +
    `<button class="btn btn-sm det-confirm" data-value="${value}">Confirmer</button>`;
  list.prepend(card);
}

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

  // Détection YOLO locale : dessine toutes les boîtes sur la même image
  // Pour la cible conteneur : conteneur.onnx (orange) + bic.onnx (jaune) simultanément
  const W = photo.naturalWidth, H = photo.naturalHeight;
  try {
    const s = await session();  // modèle cible
    const cfg = DETECT_CFG[state.target];
    const { box, boxes } = await detect(s, photo, W, H,
      { numClasses: cfg.numClasses, conf: 0.15 });

    // Boîtes du modèle cible taguées avec sa couleur/label
    let allTagged = boxes.map(b => ({ ...b, boxColor: cfg.color, className: cfg.label }));
    let bicBox = null;
    let bicBoxes = [];   // TOUTES les zones code bic détectées (multi-conteneurs)

    if (state.target === "conteneur") {
      const bicCfg = DETECT_CFG.bic;
      try {
        if (!state.sessions.bic) {
          state.sessions.bic = await loadSession(MODELS.bic.url);
        }
        const br = await detect(state.sessions.bic, photo, W, H,
          { numClasses: bicCfg.numClasses, conf: 0.15 });
        bicBox   = br.box;
        bicBoxes = br.boxes;
        const bicTagged = br.boxes.map(b => ({ ...b, boxColor: bicCfg.color, className: bicCfg.label }));
        if (bicTagged.length) allTagged = [...allTagged, ...bicTagged];
      } catch { /* bic.onnx non disponible */ }
      // Toujours recolorer les boîtes sans label "code bic" en jaune
      allTagged = allTagged.map(b =>
        b.className === bicCfg.label ? b : { ...b, boxColor: bicCfg.color, className: bicCfg.label }
      );
      // Fallback : si bic.onnx n'a rien trouvé, utiliser les boîtes du modèle cible
      if (!bicBoxes.length) bicBoxes = boxes;
    }

    if (allTagged.length) {
      drawFrame(photo, W, H, allTagged);
      setGuide("bon");
      state.annotatedUrl = overlay.toDataURL("image/jpeg", 0.92);
    }

    // Plaque : crop zone → OCR serveur sur la zone uniquement
    if (state.target === "plaque" && box) {
      el("model-status").textContent = "lecture OCR sur la zone plaque…";
      const cropResult = await cropAndOcrPlaque(photo, box);
      el("model-status").textContent = "";
      if (cropResult) { showProposal(cropResult); return; }
    }

    // Conteneur : OCR sur CHAQUE zone code bic détectée → liste de propositions
    if (state.target === "conteneur" && bicBoxes.length) {
      const clean = document.createElement("canvas");
      clean.width = W; clean.height = H;
      clean.getContext("2d").drawImage(photo, 0, 0);
      const found = await ocrAllBoxes(clean, bicBoxes, "/api/ocr-crop", "bic");
      if (found > 0) return;
      // aucun code lisible : repli sur l'OCR de la meilleure zone
      if (bicBox) {
        const cropResult = await cropAndOcr(clean, bicBox, "/api/ocr-crop");
        if (cropResult?.bic) { showProposal(cropResult); return; }
      }
    }
  } catch (e) {
    console.warn("[capture] YOLO local indisponible :", e.message);
  }

  await runOcr(file);
}

async function handleVideo(file) {
  showActions();
  state.videoMode = true;
  video.srcObject = null;
  video.src = URL.createObjectURL(file);
  video.muted = true;
  video.loop  = true;
  await new Promise((r) => video.addEventListener("loadeddata", r, { once: true }));
  el("capture-btn").hidden = false;
  el("stop-btn").hidden    = false;
  el("scan-btn").hidden    = false;
  el("scan-btn").disabled  = true;
  el("detection-log").hidden = false;
  el("det-count").textContent = "0";

  // Démarrer l'aperçu tout de suite ; le modèle se charge en arrière-plan
  video.play();
  loopVideoDetect();

  // Chargement du modèle cible sans bloquer la boucle vidéo
  session()
    .then(() => {
      el("model-status").textContent = "modèle prêt ✓";
      setTimeout(() => { if (!state.ocrPending) el("model-status").textContent = ""; }, 2000);
      loadExtraSessions();
    })
    .catch((e) => {
      el("model-status").textContent = "";
      console.warn("[capture] YOLO local indisponible sur vidéo :", e.message);
    });
}

/* Boucle de détection sur vidéo importée — même logique que la caméra
   (multi-classes + auto-capture ANPR), mais la source est le <video> fichier.
   Lit la session cible depuis state.sessions à chaque frame : dès que le
   modèle est chargé en arrière-plan, la détection démarre automatiquement. */
async function loopVideoDetect() {
  const tick = async () => {
    if (!state.videoMode) { el("stop-btn").hidden = true; return; }
    if (!video.videoWidth || !video.videoHeight) {
      state.rafId = requestAnimationFrame(tick); return;
    }
    const W = video.videoWidth, H = video.videoHeight;
    const s = state.sessions[state.target];

    if (!s) {   // modèle pas encore prêt : simple aperçu
      drawFrame(video, W, H, []);
      state.captured = { source: video, w: W, h: H };
      state.rafId = requestAnimationFrame(tick);
      return;
    }

    try {
      const cfg = DETECT_CFG[state.target];
      const primary = await detect(s, video, W, H, { numClasses: cfg.numClasses, conf: cfg.conf });
      const primaryBoxes = primary.boxes.map(b => ({ ...b, boxColor: cfg.color, className: cfg.label }));
      state.allBoxes[state.target] = primary.box;

      const extraBoxes = [];
      for (const [key, sess] of Object.entries(extraSessions)) {
        if (!sess) continue;
        const m = DETECT_CFG[key];
        try {
          const r = await detect(sess, video, W, H, { numClasses: m.numClasses, conf: m.conf });
          r.boxes.forEach(b => extraBoxes.push({ ...b, boxColor: m.color, className: m.label }));
          state.allBoxes[key] = r.box;
        } catch { state.allBoxes[key] = null; }
      }

      state.lastFrameBoxes = [...primaryBoxes, ...extraBoxes];
      drawFrame(video, W, H, state.lastFrameBoxes);
      updateScanBtn();
      setGuide(primary.guide.state);
      state.captured    = { source: video, w: W, h: H };
      state.detectedBox = primary.box;
      state.goodStreak  = primary.guide.capture ? state.goodStreak + 1 : 0;
      if (state.goodStreak >= 5) { state.goodStreak = 0; autoCapture(); }
    } catch (e) {
      // erreur d'inférence ponctuelle : garder l'aperçu, ne pas casser la boucle
      drawFrame(video, W, H, []);
    }
    state.rafId = requestAnimationFrame(tick);
  };
  tick();
}

/* ── MODE 3 : Caméra temps réel (ANPR continu) ── */
el("mode-realtime").addEventListener("click", async () => {
  clearError(); reset(); showActions();
  await startCameraMode();
});

async function startCameraMode() {
  state.cameraMode = true;
  el("capture-btn-label").textContent = "Forcer la capture";
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
    el("scan-btn").hidden    = false;
    el("scan-btn").disabled  = true;
    startCameraPreview();
    const s = await session();
    el("model-status").textContent = "modèle prêt ✓";
    setTimeout(() => {
      if (!state.ocrPending) el("model-status").textContent = "";
    }, 2000);
    state.previewOnly = false;
    loadExtraSessions();
    loopWebcam(s);
  } catch (err) { showError("Caméra inaccessible : " + err.message); }
}

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

/* Boucle YOLO caméra — tous les modèles chargés tournent en parallèle.
   Le modèle cible pilote le guide et l'auto-capture ; les autres enrichissent
   l'affichage (boîtes colorées par classe).
   state.allBoxes et state.lastFrameBoxes sont mis à jour à chaque frame
   pour que doScan() puisse les consommer instantanément. */
async function loopWebcam(s) {
  const tick = async () => {
    if (!state.stream) return;
    if (!video.videoWidth || !video.videoHeight) {
      state.rafId = requestAnimationFrame(tick); return;
    }
    const W = video.videoWidth, H = video.videoHeight;
    const cfg = DETECT_CFG[state.target];

    // Modèle cible (guide + auto-capture)
    const primary = await detect(s, video, W, H, { numClasses: cfg.numClasses, conf: cfg.conf });
    const primaryBoxes = primary.boxes.map(b => ({
      ...b, boxColor: cfg.color, className: cfg.label,
    }));
    state.allBoxes[state.target] = primary.box;

    // Modèles secondaires (affichage + suivi des boîtes pour Scan)
    const extraBoxes = [];
    for (const [key, sess] of Object.entries(extraSessions)) {
      if (!sess) continue;
      const m = DETECT_CFG[key];
      try {
        const r = await detect(sess, video, W, H, { numClasses: m.numClasses, conf: m.conf });
        r.boxes.forEach(b => extraBoxes.push({ ...b, boxColor: m.color, className: m.label }));
        state.allBoxes[key] = r.box;
      } catch {
        state.allBoxes[key] = null;
      }
    }

    state.lastFrameBoxes = [...primaryBoxes, ...extraBoxes];
    drawFrame(video, W, H, state.lastFrameBoxes);
    updateScanBtn();
    setGuide(primary.guide.state);
    state.captured    = { source: video, w: W, h: H };
    state.detectedBox = primary.box;
    state.goodStreak  = primary.guide.capture ? state.goodStreak + 1 : 0;
    if (state.goodStreak >= 5) {
      state.goodStreak = 0;
      autoCapture();
    }
    state.rafId = requestAnimationFrame(tick);
  };
  tick();
}

/* Active le bouton Scan dès qu'au moins une classe est détectée. */
function updateScanBtn() {
  const btn = el("scan-btn");
  if (!btn) return;
  const detected = Object.values(state.allBoxes).some(b => b !== null);
  btn.disabled = !detected;
  btn.style.opacity = detected ? "1" : "0.5";
}

/* Fige la caméra, lance l'OCR ciblé sur chaque boîte, affiche le dossier. */
async function doScan() {
  if ((!state.cameraMode && !state.videoMode) || !video.videoWidth) return;

  // Snapshot propre AVANT d'arrêter le stream (sans annotations dessinées)
  const snap = document.createElement("canvas");
  snap.width  = video.videoWidth;
  snap.height = video.videoHeight;
  snap.getContext("2d").drawImage(video, 0, 0);

  const frozenBoxes    = [...state.lastFrameBoxes];
  const frozenAllBoxes = { ...state.allBoxes };

  // Figer (caméra ou vidéo)
  if (state.rafId) { cancelAnimationFrame(state.rafId); state.rafId = null; }
  if (state.stream) { state.stream.getTracks().forEach(t => t.stop()); state.stream = null; }
  if (state.videoMode) video.pause();
  state.cameraMode = false;
  state.videoMode  = false;
  el("scan-btn").hidden    = true;
  el("capture-btn").hidden = true;
  el("stop-btn").hidden    = true;

  // Redessiner le frame figé avec les boîtes sur l'overlay
  drawFrame(snap, snap.width, snap.height, frozenBoxes);

  // Préparer la section résultat
  const scanResult = el("scan-result");
  scanResult.hidden = false;
  el("scan-loading").hidden = false;
  el("scan-bic-input").value       = "";
  el("scan-bic-badge").textContent = "";
  el("scan-bic-raw").textContent   = "";
  el("scan-plaque-input").value       = "";
  el("scan-plaque-badge").textContent = "";
  el("scan-plaque-raw").textContent   = "";
  el("scan-bic-row").style.opacity    = "1";
  el("scan-plaque-row").style.opacity = "1";

  // OCR parallèle : bic.onnx détecte la zone code bic, plaque.onnx la zone plaque.
  // La boîte conteneur est visuelle uniquement (pas d'OCR sur la caisse).
  const bicOcrBox = frozenAllBoxes.bic ?? frozenAllBoxes.conteneur ?? null;
  const [bicResult, plaqueResult] = await Promise.all([
    bicOcrBox
      ? cropAndOcr(snap, bicOcrBox, "/api/ocr-crop")
      : Promise.resolve(null),
    frozenAllBoxes.plaque
      ? cropAndOcr(snap, frozenAllBoxes.plaque, "/api/ocr-plaque-crop")
      : Promise.resolve(null),
  ]);

  el("scan-loading").hidden = true;

  if (bicResult) {
    el("scan-bic-input").value       = bicResult.bic || "";
    el("scan-bic-badge").textContent = bicResult.valid ? "BIC valide ✓" : "à vérifier";
    el("scan-bic-badge").className   = "badge " + (bicResult.valid ? "badge-ok" : "badge-warn");
    el("scan-bic-raw").textContent   = bicResult.raw_text ? "OCR brut : " + bicResult.raw_text : "";
  } else {
    el("scan-bic-row").style.opacity = "0.4";
  }

  if (plaqueResult) {
    el("scan-plaque-input").value       = plaqueResult.plaque || "";
    el("scan-plaque-badge").textContent = plaqueResult.valid ? "valide ✓" : "à vérifier";
    el("scan-plaque-badge").className   = "badge " + (plaqueResult.valid ? "badge-ok" : "badge-warn");
    el("scan-plaque-raw").textContent   = plaqueResult.raw_text ? "OCR brut : " + plaqueResult.raw_text : "";
  } else {
    el("scan-plaque-row").style.opacity = "0.4";
  }
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
  // Pour conteneur : OCR sur la zone code bic (précise) plutôt que sur la caisse
  const box = state.target === "conteneur"
    ? (state.allBoxes.bic ?? state.detectedBox)
    : state.detectedBox;

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

/* ── Bouton Scan ── */
el("scan-btn").addEventListener("click", doScan);

/* ── Confirmer le dossier complet (BIC + Plaque en séquence) ── */
el("scan-confirm-btn").addEventListener("click", async () => {
  const bic    = el("scan-bic-input").value.trim();
  const plaque = el("scan-plaque-input").value.trim();
  if (!bic && !plaque) return;
  el("scan-confirm-btn").disabled = true;
  clearError();
  try {
    const base = await window.apiBase();
    if (bic) {
      const r    = await fetch(`${base}/api/passage/confirmer`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: "conteneur", valeur: bic }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "Erreur serveur");
      state.dossierId = data.dossier_id;
      renderDossier(data.dossier);
    }
    if (plaque) {
      const r    = await fetch(`${base}/api/passage/confirmer`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: "plaque", valeur: plaque, dossier_id: state.dossierId || undefined }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "Erreur serveur");
      state.dossierId = data.dossier_id;
      renderDossier(data.dossier);
    }
  } catch (err) {
    showError("Rattachement impossible : " + err.message);
  } finally {
    el("scan-confirm-btn").disabled = false;
  }
});

el("scan-again-btn").addEventListener("click", reset);

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

  // Afficher l'image annotée (canvas YOLO) ou l'image serveur si disponible
  const annotImg = el("result-annotated");
  const imgSrc = state.annotatedUrl || data.image_url || "";
  annotImg.hidden = !imgSrc;
  if (imgSrc) annotImg.src = imgSrc;
  state.annotatedUrl = null;
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
  const comp      = getComplement();
  const compLabel = comp === "plaque" ? "Plaque" : "Conteneur";
  el("import-complement-label").textContent = `Importer ${compLabel}`;
  el("scan-complement-label").textContent   = `Scanner ${compLabel}`;
  el("import-complement-btn").hidden = valide;
  el("scan-complement-btn").hidden   = valide;
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
    el("valider-passage-btn").hidden   = true;
    el("attente-btn").hidden           = true;
    el("import-complement-btn").hidden = true;
    el("scan-complement-btn").hidden   = true;
    el("dossier-msg").textContent      = `Passage #${state.dossierId} enregistré.`;
    state.dossierId = null;   // prochain Confirmer = nouveau dossier
  } catch (err) { showError("Validation impossible : " + err.message); }
});

el("attente-btn").addEventListener("click", () => {
  // Le dossier reste en base (en_attente) — l'agent le retrouvera dans l'historique.
  state.dossierId = null;
  el("dossier-section").hidden = true;
});

/* ── Helpers entité complémentaire ── */
function getComplement() { return state.target === "conteneur" ? "plaque" : "conteneur"; }

function updateTargetUI(target) {
  el("target-seg").querySelectorAll("[data-target]").forEach(b =>
    b.setAttribute("aria-pressed", String(b.dataset.target === target)));
}

/* Importer un fichier pour l'entité complémentaire sans perdre le dossier. */
el("import-complement-btn").addEventListener("click", () => {
  state.target = getComplement();
  updateTargetUI(state.target);
  el("complement-input").click();
});

el("complement-input").addEventListener("change", (e) => {
  const file = e.target.files[0]; if (!file) return;
  e.target.value = "";
  clearError();
  el("result-section").hidden   = true;
  el("result-annotated").hidden = true;
  state.annotatedUrl            = null;
  if (file.type.startsWith("image/")) handlePhoto(file);
  else showError("Type de fichier non supporté : " + file.type);
});

/* Scanner en temps réel l'entité complémentaire sans perdre le dossier. */
el("scan-complement-btn").addEventListener("click", async () => {
  const savedId = state.dossierId;
  state.target = getComplement();
  updateTargetUI(state.target);
  clearError();
  stopLive();
  state.captured = null; state.detectedBox = null; state.goodStreak = 0;
  state.previewOnly = false; state.cameraMode = false; state.cooldownUntil = 0;
  state.ocrPending = 0; state.allBoxes = {}; state.lastFrameBoxes = [];
  state.annotatedUrl = null;
  state.dossierId = savedId;
  el("result-annotated").hidden = true;
  el("result-section").hidden   = true;
  el("scan-result").hidden      = true;
  el("scan-btn").hidden         = true;
  el("capture-btn").hidden      = true;
  octx.clearRect(0, 0, overlay.width, overlay.height);
  setGuide("aucun");
  showActions();
  await startCameraMode();
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
  state.captured       = null;
  state.detectedBox    = null;
  state.goodStreak     = 0;
  state.previewOnly    = false;
  state.cameraMode     = false;
  state.cooldownUntil  = 0;
  state.ocrPending     = 0;
  state.allBoxes       = {};
  state.lastFrameBoxes = [];
  state.annotatedUrl   = null;
  el("result-annotated").hidden = true;
  el("result-section").hidden   = true;
  el("detection-log").hidden    = true;
  el("scan-result").hidden      = true;
  el("scan-btn").hidden         = true;
  el("capture-btn").hidden      = true;
  el("action-row").hidden       = true;
  el("log-list").innerHTML      = "";
  el("det-count").textContent   = "0";
  el("ocr-status").textContent  = "";
  document.querySelector("#detection-log h2").textContent = "Détections en cours";
  el("capture-btn-label").textContent = "Capturer cette image";
  el("scan-bic-input").value    = "";
  el("scan-plaque-input").value = "";
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
