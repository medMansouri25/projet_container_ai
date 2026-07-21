/* capture.js — écran de capture multi-source.
   2 façons de capturer : IMPORTER un fichier (image OU vidéo, routé selon le
   type MIME) ou DÉTECTION TEMPS RÉEL (caméra). Détection client-side
   (webdetect.js) pour le repère de distance E1 ; lecture OCR sur le serveur. */

import { loadSession, detect, detectVideoFrames, seekTo, MODELS } from "./webdetect.js";

const el = (id) => document.getElementById(id);
const overlay = el("overlay");
const octx = overlay.getContext("2d");
const video = el("video");
const photo = el("photo");

const state = {
  target: "conteneur",   // conteneur | plaque
  sessions: {},          // cache sessions ort par cible
  stream: null,
  rafId: null,
  goodStreak: 0,
  captured: null,        // {source, w, h}
};

const OCR = {
  conteneur: { endpoint: "/api/scan", field: "bic", label: "Code ISO (BIC)" },
  plaque:    { endpoint: "/api/scan-plaque", field: "plaque", label: "Immatriculation" },
};

const showError = (m) => { const a = el("error-alert"); a.textContent = m; a.hidden = false; };
const clearError = () => { el("error-alert").hidden = true; };

const T = (k) => (window.i18n ? window.i18n.t(k) : k);

function setGuide(s) {
  const g = el("guide");
  g.className = "g-" + s;
  g.textContent = T("guide." + s);
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
    el("model-status").textContent = "chargement du modèle…";
    state.sessions[state.target] = await loadSession(MODELS[state.target].url);
    el("model-status").textContent = "";
  }
  return state.sessions[state.target];
}
const numClasses = () => MODELS[state.target].numClasses;

/* ── Dessin ── */
function drawFrame(source, w, h, box) {
  overlay.width = w; overlay.height = h;
  octx.drawImage(source, 0, 0, w, h);
  if (box) {
    octx.strokeStyle = "#2ecc71"; octx.lineWidth = Math.max(2, w / 200);
    octx.strokeRect(box.x, box.y, box.w, box.h);
  }
}
function showActions() { el("action-row").hidden = false; }

/* ── MODE 1 : Importer un fichier (image OU vidéo) ── */
el("mode-import").addEventListener("click", () => el("file-input").click());

el("file-input").addEventListener("change", (e) => {
  const file = e.target.files[0]; if (!file) return;
  clearError(); reset();
  if (file.type.startsWith("video/")) handleVideo(file);
  else if (file.type.startsWith("image/")) handlePhoto(file);
  else showError("Type de fichier non supporté : " + file.type);
});

async function handlePhoto(file) {
  showActions();
  photo.src = URL.createObjectURL(file);
  await photo.decode();
  const res = await detect(await session(), photo, photo.naturalWidth, photo.naturalHeight,
                           { numClasses: numClasses(), conf: 0.25 });
  drawFrame(photo, photo.naturalWidth, photo.naturalHeight, res.box);
  setGuide(res.guide.state);
  el("capture-btn").hidden = false;
  state.captured = { source: photo, w: photo.naturalWidth, h: photo.naturalHeight };
}

async function handleVideo(file) {
  showActions();
  el("model-status").textContent = "analyse de la vidéo…";
  video.src = URL.createObjectURL(file);
  await new Promise((r) => video.addEventListener("loadeddata", r, { once: true }));
  const s = await session();
  let best = null;
  await detectVideoFrames(s, video, {
    everySeconds: 0.5, numClasses: numClasses(), conf: 0.25,
    onFrame: (t, r) => {
      drawFrame(video, video.videoWidth, video.videoHeight, r.box);
      setGuide(r.guide.state);
      if (r.box && r.guide.capture && (!best || r.box.score > best.box.score)) best = { t, ...r };
    },
  });
  el("model-status").textContent = "";
  if (best) {
    await seekTo(video, best.t);
    drawFrame(video, video.videoWidth, video.videoHeight, best.box);
    setGuide(best.guide.state);
    el("capture-btn").hidden = false;
    state.captured = { source: video, w: video.videoWidth, h: video.videoHeight };
  } else {
    showError("Aucune frame bien cadrée trouvée dans la vidéo. Réessaie avec une vue plus rapprochée.");
  }
}

/* ── MODE 2 : Détection temps réel (caméra) ── */
el("mode-realtime").addEventListener("click", async () => {
  clearError(); reset(); showActions();
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 } } });
    video.srcObject = state.stream;
    await video.play();
    el("capture-btn").hidden = false;
    el("stop-btn").hidden = false;
    loopWebcam();
  } catch (err) { showError("Caméra inaccessible : " + err.message); }
});

async function loopWebcam() {
  const s = await session();
  const tick = async () => {
    if (!state.stream) return;
    const res = await detect(s, video, video.videoWidth, video.videoHeight,
                             { numClasses: numClasses(), conf: 0.25 });
    drawFrame(video, video.videoWidth, video.videoHeight, res.box);
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
  stopWebcam();
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
    const r = await fetch(`${await window.apiBase()}${cfg.endpoint}`, { method: "POST", body: fd });
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
  el("result-section").hidden = false;
  el("value-label").textContent = cfg.label;
  el("value-input").value = data[cfg.field] || "";
  el("result-raw").textContent = data.raw_text ? "OCR brut : " + data.raw_text : "";
  const badges = [];
  badges.push(data.valid ? `<span class="badge badge-ok">${T("badge.valid")}</span>`
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
function stopWebcam() {
  if (state.rafId) { cancelAnimationFrame(state.rafId); state.rafId = null; }
  if (state.stream) { state.stream.getTracks().forEach((t) => t.stop()); state.stream = null; }
  el("stop-btn").hidden = true;
}
function reset() {
  stopWebcam();
  state.captured = null; state.goodStreak = 0;
  el("result-section").hidden = true;
  el("capture-btn").hidden = true;
  el("action-row").hidden = true;
  octx.clearRect(0, 0, overlay.width, overlay.height);
  setGuide("aucun");
}

reset();
