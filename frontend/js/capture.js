/* capture.js — écran de capture multi-source.
   3 modes : IMPORTER image, IMPORTER vidéo (lecture live + YOLO), CAMÉRA temps réel.
   Détection client-side (webdetect.js + onnxruntime-web) pour le repère de cadrage ;
   OCR final sur le serveur (POST /api/scan ou /api/scan-plaque). */

import { loadSession, detect, seekTo, MODELS } from "./webdetect.js";

const el = (id) => document.getElementById(id);
const overlay = el("overlay");
const octx    = overlay.getContext("2d");
const video   = el("video");
const photo   = el("photo");

const state = {
  target:    "conteneur",   // conteneur | plaque
  sessions:  {},            // cache sessions ort par cible
  stream:    null,          // MediaStream (caméra)
  rafId:     null,
  goodStreak: 0,
  captured:  null,          // {source, w, h}
  videoMode:   false,       // true = vidéo importée en lecture live
  previewOnly: false,       // true = caméra sans YOLO (modèle en cours de chargement)
};

const OCR = {
  conteneur: { endpoint: "/api/scan",        field: "bic",   label: "Code ISO (BIC)" },
  plaque:    { endpoint: "/api/scan-plaque", field: "plaque", label: "Immatriculation" },
};

// Noms de classes par cible (doivent correspondre à l'ordre du modèle ONNX)
const CLASS_NAMES = {
  conteneur: ["Conteneur", "Fruit"],
  plaque:    ["Plaque"],
};
const BOX_COLORS = ["#3b82f6", "#f97316", "#22c55e", "#a855f7"];

const showError  = (m) => { const a = el("error-alert"); a.textContent = m; a.hidden = false; };
const clearError = ()  => { el("error-alert").hidden = true; };
const T = (k) => (window.i18n ? window.i18n.t(k) : k);

function setGuide(s) {
  const g = el("guide");
  g.className = "g-" + s;
  const MAP = { aucun: "aucun objet", trop_loin: "trop loin — approchez", trop_pres: "trop près — reculez", bon: "bien cadré ✓" };
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
    const mb = state.target === "conteneur" ? 77 : 37;
    const cached = await modelIsCached(MODELS[state.target].url);
    el("model-status").textContent = cached
      ? "chargement depuis le cache…"
      : `1er téléchargement YOLO (${mb} Mo) — une seule fois…`;
    state.sessions[state.target] = await loadSession(MODELS[state.target].url);
    el("model-status").textContent = "";
  }
  return state.sessions[state.target];
}

async function modelIsCached(url) {
  if (!("caches" in window)) return false;
  try {
    const abs = new URL(url, location.href).href;
    const r   = await caches.match(abs);
    return !!r;
  } catch { return false; }
}
const numClasses = () => MODELS[state.target].numClasses;

/* ── Dessin : toutes les boîtes avec label classe + score ── */
function drawFrame(source, w, h, boxes = []) {
  if (!w || !h) return;
  overlay.width  = w;
  overlay.height = h;
  octx.drawImage(source, 0, 0, w, h);

  const names = CLASS_NAMES[state.target] || [];
  const lw    = Math.max(2, w / 200);
  const fs    = Math.max(13, Math.round(w / 42));

  for (const box of (Array.isArray(boxes) ? boxes : box ? [boxes] : [])) {
    const color = BOX_COLORS[(box.cls || 0) % BOX_COLORS.length];
    const label = `${names[box.cls || 0] || "?"} ${Math.round((box.score || 0) * 100)}%`;

    // Rectangle de détection
    octx.strokeStyle = color;
    octx.lineWidth   = lw;
    octx.strokeRect(box.x, box.y, box.w, box.h);

    // Badge label au-dessus de la boîte
    octx.font = `bold ${fs}px sans-serif`;
    const tw = octx.measureText(label).width;
    const tx = Math.max(0, box.x);
    const ty = Math.max(fs + 6, box.y - 2);
    octx.fillStyle = color;
    octx.fillRect(tx, ty - fs - 4, tw + 10, fs + 6);
    octx.fillStyle = "#ffffff";
    octx.fillText(label, tx + 5, ty - 1);
  }
}

function showActions() { el("action-row").hidden = false; }

/* ── MODE 1 : Importer une image ── */
el("mode-import").addEventListener("click", () => el("file-input").click());

el("file-input").addEventListener("change", (e) => {
  const file = e.target.files[0]; if (!file) return;
  e.target.value = "";            // permet de re-choisir le même fichier
  clearError(); reset();
  if (file.type.startsWith("video/"))      handleVideo(file);
  else if (file.type.startsWith("image/")) handlePhoto(file);
  else showError("Type de fichier non supporté : " + file.type);
});

async function handlePhoto(file) {
  showActions();
  photo.src = URL.createObjectURL(file);
  await photo.decode();
  const res = await detect(await session(), photo,
                           photo.naturalWidth, photo.naturalHeight,
                           { numClasses: numClasses(), conf: 0.25 });
  drawFrame(photo, photo.naturalWidth, photo.naturalHeight, res.boxes);
  setGuide(res.guide.state);
  el("capture-btn").hidden = false;
  state.captured = { source: photo, w: photo.naturalWidth, h: photo.naturalHeight };
}

/* ── MODE 2 : Vidéo importée — lecture live + YOLO frame par frame ── */
async function handleVideo(file) {
  showActions();
  state.videoMode = true;
  video.src = URL.createObjectURL(file);
  await new Promise((r) => video.addEventListener("loadeddata", r, { once: true }));
  el("capture-btn").hidden = false;
  el("stop-btn").hidden    = false;
  video.play();
  loopVideo(await session());
}

async function loopVideo(s) {
  const tick = async () => {
    if (!state.videoMode || video.ended || video.paused) {
      el("stop-btn").hidden = true;
      return;
    }
    if (!video.videoWidth || !video.videoHeight) {
      state.rafId = requestAnimationFrame(tick); return;
    }
    const res = await detect(s, video, video.videoWidth, video.videoHeight,
                             { numClasses: numClasses(), conf: 0.25 });
    drawFrame(video, video.videoWidth, video.videoHeight, res.boxes);
    setGuide(res.guide.state);
    state.captured = { source: video, w: video.videoWidth, h: video.videoHeight };
    state.rafId = requestAnimationFrame(tick);
  };
  tick();
}

/* ── MODE 3 : Caméra temps réel ── */
el("mode-realtime").addEventListener("click", async () => {
  clearError(); reset(); showActions();
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 } },
    });
    video.srcObject = state.stream;
    await video.play();
    el("capture-btn").hidden = false;
    el("stop-btn").hidden    = false;

    // Afficher le flux caméra immédiatement (sans attendre le modèle ONNX)
    startCameraPreview();

    // Charger le modèle ONNX en parallèle (session() gère le message)
    const s = await session();
    el("model-status").textContent = "modèle prêt ✓";
    setTimeout(() => { el("model-status").textContent = ""; }, 2000);
    state.previewOnly = false;
    loopWebcam(s);
  } catch (err) { showError("Caméra inaccessible : " + err.message); }
});

/* Prévisualisation caméra brute (sans YOLO) pendant le chargement du modèle. */
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

async function loopWebcam(s) {
  const tick = async () => {
    if (!state.stream) return;
    // Attendre que la caméra soit prête (videoWidth=0 les premières ms)
    if (!video.videoWidth || !video.videoHeight) {
      state.rafId = requestAnimationFrame(tick); return;
    }
    const res = await detect(s, video, video.videoWidth, video.videoHeight,
                             { numClasses: numClasses(), conf: 0.25 });
    drawFrame(video, video.videoWidth, video.videoHeight, res.boxes);
    setGuide(res.guide.state);
    state.captured = { source: video, w: video.videoWidth, h: video.videoHeight };
    state.goodStreak = res.guide.capture ? state.goodStreak + 1 : 0;
    if (state.goodStreak >= 5) { state.goodStreak = 0; return doCapture(); }  // auto
    state.rafId = requestAnimationFrame(tick);
  };
  tick();
}

el("stop-btn").addEventListener("click", reset);

/* ── Capture → OCR serveur ── */
el("capture-btn").addEventListener("click", doCapture);

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
  el("result-section").hidden  = false;
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

/* Confirmer → rattachement au dossier de passage : câblé en Mission 6. */
el("confirm-btn").addEventListener("click", () => {
  const value = el("value-input").value.trim();
  if (!value) return;
  window.__CONFIRMED__ = { target: state.target, value };
  alert(`À rattacher au dossier (Mission 6) : ${state.target} = ${value}`);
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
  state.captured    = null;
  state.goodStreak  = 0;
  state.previewOnly = false;
  el("result-section").hidden = true;
  el("capture-btn").hidden    = true;
  el("action-row").hidden     = true;
  octx.clearRect(0, 0, overlay.width, overlay.height);
  setGuide("aucun");
}

reset();
