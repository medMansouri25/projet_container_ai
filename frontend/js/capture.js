/* capture.js — écran de capture multi-source (photo / vidéo / webcam).
   Détection client-side (webdetect.js) pour le repère de distance E1 ;
   lecture OCR déléguée au serveur (une seule fois, sur la frame nette). */

import { loadSession, detect, detectVideoFrames, MODELS, IMG } from "./webdetect.js";
import { distanceGuide } from "./detect.js";

const el = (id) => document.getElementById(id);
const overlay = el("overlay");
const octx = overlay.getContext("2d");
const video = el("video");
const photo = el("photo");

const state = {
  target: "conteneur",   // conteneur | plaque
  source: "photo",       // photo | video | webcam
  sessions: {},          // cache des sessions ort par cible
  stream: null,
  rafId: null,
  goodStreak: 0,         // frames consécutives "bon" (auto-capture webcam)
  captured: null,        // {blob, endpoint}
};

const OCR = {
  conteneur: { endpoint: "/api/scan", field: "bic", label: "Code ISO (BIC)" },
  plaque:    { endpoint: "/api/scan-plaque", field: "plaque", label: "Immatriculation" },
};

function showError(msg) { const a = el("error-alert"); a.textContent = msg; a.hidden = false; }
function clearError() { el("error-alert").hidden = true; }

function setGuide(state_) {
  const g = el("guide");
  g.className = "g-" + state_;
  g.textContent = { aucun: "aucun objet", trop_loin: "trop loin — approchez",
                    bon: "bon cadrage ✓", trop_pres: "trop près — reculez" }[state_];
}

/* ── Sélecteurs ── */
el("target-seg").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  state.target = b.dataset.target;
  [...el("target-seg").children].forEach((c) => c.classList.toggle("active", c === b));
  reset();
});
el("source-seg").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  state.source = b.dataset.source;
  [...el("source-seg").children].forEach((c) => c.classList.toggle("active", c === b));
  setupSource();
});

function setupSource() {
  reset();
  el("pick-btn").hidden = state.source === "webcam";
  el("cam-start").hidden = state.source !== "webcam";
  el("capture-btn").hidden = true;
}

/* ── Chargement du modèle (lazy, par cible) ── */
async function session() {
  if (!state.sessions[state.target]) {
    el("model-status").textContent = "chargement du modèle…";
    state.sessions[state.target] = await loadSession(MODELS[state.target].url);
    el("model-status").textContent = "modèle prêt";
  }
  return state.sessions[state.target];
}

/* ── Dessin ── */
function drawFrame(source, w, h, box) {
  overlay.width = w; overlay.height = h;
  octx.drawImage(source, 0, 0, w, h);
  if (box) {
    octx.strokeStyle = "#2ecc71"; octx.lineWidth = Math.max(2, w / 200);
    octx.strokeRect(box.x, box.y, box.w, box.h);
  }
}

/* ── Mode PHOTO ── */
el("pick-btn").addEventListener("click", () =>
  el(state.source === "video" ? "file-video" : "file-photo").click());

el("file-photo").addEventListener("change", async (e) => {
  const file = e.target.files[0]; if (!file) return;
  clearError();
  photo.src = URL.createObjectURL(file);
  await photo.decode();
  const s = await session();
  const res = await detect(s, photo, photo.naturalWidth, photo.naturalHeight,
                           { numClasses: MODELS[state.target].numClasses, conf: 0.25 });
  drawFrame(photo, photo.naturalWidth, photo.naturalHeight, res.box);
  setGuide(res.guide.state);
  el("capture-btn").hidden = false;
  state.captured = { source: photo, w: photo.naturalWidth, h: photo.naturalHeight };
});

/* ── Mode VIDÉO ── */
el("file-video").addEventListener("change", async (e) => {
  const file = e.target.files[0]; if (!file) return;
  clearError();
  video.src = URL.createObjectURL(file);
  await new Promise((r) => video.addEventListener("loadeddata", r, { once: true }));
  const s = await session();
  let best = null;
  await detectVideoFrames(s, video, {
    everySeconds: 0.5, numClasses: MODELS[state.target].numClasses, conf: 0.25,
    onFrame: (t, r) => {
      drawFrame(video, video.videoWidth, video.videoHeight, r.box);
      setGuide(r.guide.state);
      if (r.box && r.guide.capture && (!best || r.box.score > best.box.score)) best = { t, ...r };
    },
  });
  if (best) {
    const { seekTo } = await import("./webdetect.js");
    await seekTo(video, best.t);
    drawFrame(video, video.videoWidth, video.videoHeight, best.box);
    setGuide(best.guide.state);
    el("capture-btn").hidden = false;
    state.captured = { source: video, w: video.videoWidth, h: video.videoHeight };
  } else {
    showError("Aucune frame bien cadrée détectée dans la vidéo.");
  }
});

/* ── Mode WEBCAM ── */
el("cam-start").addEventListener("click", async () => {
  clearError();
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 } } });
    video.srcObject = state.stream;
    await video.play();
    el("capture-btn").hidden = false;
    loopWebcam();
  } catch (err) { showError("Caméra inaccessible : " + err.message); }
});

async function loopWebcam() {
  const s = await session();
  const tick = async () => {
    if (!state.stream) return;
    const res = await detect(s, video, video.videoWidth, video.videoHeight,
                             { numClasses: MODELS[state.target].numClasses, conf: 0.25 });
    drawFrame(video, video.videoWidth, video.videoHeight, res.box);
    setGuide(res.guide.state);
    state.captured = { source: video, w: video.videoWidth, h: video.videoHeight };
    // auto-capture après 5 frames consécutives bien cadrées
    state.goodStreak = res.guide.capture ? state.goodStreak + 1 : 0;
    if (state.goodStreak >= 5) { state.goodStreak = 0; doCapture(); return; }
    state.rafId = requestAnimationFrame(tick);
  };
  tick();
}

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
    showError("Lecture impossible : " + err.message);
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
  if (data.valid) badges.push('<span class="badge badge-ok">Forme valide</span>');
  else badges.push('<span class="badge badge-warn">À vérifier</span>');
  if (data.corrected) badges.push('<span class="badge badge-warn">Recalculé</span>');
  el("result-badges").innerHTML = badges.join(" ");
}

/* Confirmer : rattachement au dossier de passage — câblé en Mission 6.
   Pour l'instant, expose la valeur validée pour la suite. */
el("confirm-btn").addEventListener("click", () => {
  const value = el("value-input").value.trim();
  if (!value) return;
  window.__CONFIRMED__ = { target: state.target, value };
  // TODO Mission 6 : POST /api/dossiers/<id>/(conteneur|plaque) puis /validate
  alert(`À rattacher au dossier (Mission 6) : ${state.target} = ${value}`);
});

el("again-btn").addEventListener("click", reset);

/* ── Utilitaires ── */
function stopWebcam() {
  if (state.rafId) cancelAnimationFrame(state.rafId), (state.rafId = null);
  if (state.stream) { state.stream.getTracks().forEach((t) => t.stop()); state.stream = null; }
}
function reset() {
  stopWebcam();
  state.captured = null; state.goodStreak = 0;
  el("result-section").hidden = true;
  el("capture-btn").hidden = true;
  octx.clearRect(0, 0, overlay.width, overlay.height);
  setGuide("aucun");
}

setupSource();
setGuide("aucun");
