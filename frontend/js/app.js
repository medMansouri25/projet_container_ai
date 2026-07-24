/* app.js — Scanner BIC : détection ONNX locale + OCR VPS sur le crop seulement.
   Fallback automatique vers /api/scan (pipeline complet VPS) si ONNX indisponible. */
import { loadSession, detect, MODELS } from './webdetect.js';

const fileInput   = document.getElementById("file-input");
const dropzone    = document.getElementById("dropzone");
const cameraBtn   = document.getElementById("camera-btn");
const cameraZone  = document.getElementById("camera-zone");
const video       = document.getElementById("video");
const canvas      = document.getElementById("canvas");
const captureBtn  = document.getElementById("capture-btn");
const closeBtn    = document.getElementById("close-camera-btn");
const previewZone = document.getElementById("preview-zone");
const previewImg  = document.getElementById("preview");
const resetBtn    = document.getElementById("reset-btn");
const analyzeBtn  = document.getElementById("analyze-btn");
const loading     = document.getElementById("loading");
const errorAlert  = document.getElementById("error-alert");

let currentFile  = null;
let currentScan  = null;
let stream       = null;
let onnxSession  = null;
let activeModel  = null;

/* Précharger le modèle ONNX NumeroBIC dédié (1 classe, yolo11n).
   Fallback sur conteneur.onnx (multi-classes) si bic.onnx absent du VPS. */
(async () => {
  try {
    onnxSession = await loadSession(MODELS.bic.url);
    activeModel = MODELS.bic;
    console.log("[scanner] Modèle bic.onnx chargé (NumeroBIC dédié)");
  } catch {
    try {
      onnxSession = await loadSession(MODELS.conteneur.url);
      activeModel = MODELS.conteneur;
      console.log("[scanner] Fallback conteneur.onnx");
    } catch (e) {
      console.warn("[scanner] ONNX indisponible, mode serveur :", e.message);
    }
  }
})();

function showError(msg) {
  errorAlert.textContent = msg;
  errorAlert.hidden = false;
}

/* ── Sélection / aperçu ── */
function showPreview(file) {
  currentFile = file;
  previewImg.src = URL.createObjectURL(file);
  dropzone.hidden = true;
  cameraZone.hidden = true;
  previewZone.hidden = false;
  errorAlert.hidden = true;
}

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) showPreview(fileInput.files[0]);
});

resetBtn.addEventListener("click", () => {
  currentFile = null;
  fileInput.value = "";
  previewZone.hidden = true;
  dropzone.hidden = false;
});

["dragenter", "dragover"].forEach(evt =>
  dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.classList.add("dragover"); }));
["dragleave", "drop"].forEach(evt =>
  dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.classList.remove("dragover"); }));

dropzone.addEventListener("drop", e => {
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith("image/")) showPreview(file);
});

/* ── Caméra ── */
cameraBtn.addEventListener("click", async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1920 } }
    });
    video.srcObject = stream;
    dropzone.hidden = true;
    cameraZone.hidden = false;
  } catch (err) {
    showError("Camera inaccessible : " + err.message);
  }
});

function stopCamera() {
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  cameraZone.hidden = true;
}

closeBtn.addEventListener("click", () => { stopCamera(); dropzone.hidden = false; });

captureBtn.addEventListener("click", () => {
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  canvas.toBlob(blob => {
    stopCamera();
    showPreview(new File([blob], "capture.jpg", { type: "image/jpeg" }));
  }, "image/jpeg", 0.92);
});

/* ── Dessine les boîtes de détection sur une copie de l'image source ── */
function annotateImage(srcImg, boxes, targetBox) {
  const W = srcImg.naturalWidth, H = srcImg.naturalHeight;
  const cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  const ctx = cv.getContext("2d");
  ctx.drawImage(srcImg, 0, 0, W, H);

  const lw = Math.max(3, W / 250);
  const fs = Math.max(16, W / 45);

  for (const b of boxes) {
    const isBic = activeModel === MODELS.bic
      ? true
      : b.cls === activeModel.bicClassId;
    const color  = isBic ? "#FFD700" : "#00CC66";
    const label  = isBic ? "code bic" : "Conteneur";
    const pct    = Math.round(b.score * 100);

    // Boîte arrondie
    const r = lw * 3;
    ctx.strokeStyle = color;
    ctx.lineWidth   = lw;
    ctx.beginPath();
    ctx.moveTo(b.x + r, b.y);
    ctx.lineTo(b.x + b.w - r, b.y);
    ctx.quadraticCurveTo(b.x + b.w, b.y, b.x + b.w, b.y + r);
    ctx.lineTo(b.x + b.w, b.y + b.h - r);
    ctx.quadraticCurveTo(b.x + b.w, b.y + b.h, b.x + b.w - r, b.y + b.h);
    ctx.lineTo(b.x + r, b.y + b.h);
    ctx.quadraticCurveTo(b.x, b.y + b.h, b.x, b.y + b.h - r);
    ctx.lineTo(b.x, b.y + r);
    ctx.quadraticCurveTo(b.x, b.y, b.x + r, b.y);
    ctx.closePath();
    ctx.stroke();

    // Label (fond couleur + texte noir)
    ctx.font = `bold ${fs}px monospace`;
    const txt = `${label}  ${pct}%`;
    const tw  = ctx.measureText(txt).width;
    const lh  = fs + 8;
    const lx  = b.x;
    const ly  = b.y > lh + 4 ? b.y - lh - 2 : b.y + b.h + 2;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(lx, ly, tw + 14, lh, 4);
    ctx.fill();
    ctx.fillStyle = "#000";
    ctx.fillText(txt, lx + 7, ly + fs - 1);
  }
  return cv.toDataURL("image/jpeg", 0.92);
}

/* ── Détection locale ONNX → OCR VPS sur le crop ── */
async function analyzeLocal() {
  const img = previewImg;
  if (!img.complete || !img.naturalWidth) {
    await new Promise(res => img.addEventListener("load", res, { once: true }));
  }

  loading.textContent = "Détection zone BIC (locale)…";
  const model = activeModel;
  const { box, boxes } = await detect(
    onnxSession, img, img.naturalWidth, img.naturalHeight,
    { numClasses: model.numClasses, conf: 0.25 }
  );

  // Préférer la classe NumeroBIC (bicClassId) si disponible dans le modèle multi-classes
  let targetBox = null;
  if (model.bicClassId !== null && boxes.length) {
    const bicBoxes = boxes.filter(b => b.cls === model.bicClassId);
    if (bicBoxes.length) {
      targetBox = bicBoxes.reduce((a, b) => b.score > a.score ? b : a);
    }
  }
  if (!targetBox) targetBox = box;  // fallback : meilleure boîte toutes classes
  if (!targetBox) return null;      // aucune détection → fallback serveur

  // Annoter l'image source avec les boîtes détectées
  const annotatedUrl = annotateImage(img, boxes, targetBox);

  loading.textContent = "Lecture OCR en cours…";

  // Crop avec 5 % de marge autour de la boîte détectée
  const pad = 0.05;
  const W = img.naturalWidth, H = img.naturalHeight;
  const cx = Math.max(0, targetBox.x - targetBox.w * pad);
  const cy = Math.max(0, targetBox.y - targetBox.h * pad);
  const cw = Math.min(W - cx, targetBox.w * (1 + 2 * pad));
  const ch = Math.min(H - cy, targetBox.h * (1 + 2 * pad));

  const cv = document.createElement("canvas");
  cv.width = Math.round(cw); cv.height = Math.round(ch);
  cv.getContext("2d").drawImage(img, cx, cy, cw, ch, 0, 0, cv.width, cv.height);

  return new Promise((resolve, reject) => {
    cv.toBlob(async blob => {
      try {
        const fd = new FormData();
        fd.append("image", new File([blob], "crop.jpg", { type: "image/jpeg" }));
        const r = await fetch(`${await apiBase()}/api/ocr-crop`, { method: "POST", body: fd });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || "Erreur OCR");
        resolve({
          found: true,
          container_found: true,
          local_detection: true,
          bic: data.bic || "",
          valid: data.valid,
          ocr_confidence: data.ocr_confidence,
          raw_text: data.raw_text,
          image_url: data.image_url,
          image_name: data.image_name,
          yolo_confidence: targetBox.score,
          annotated_url: annotatedUrl,
        });
      } catch (e) { reject(e); }
    }, "image/jpeg", 0.92);
  });
}

/* ── Fallback : pipeline complet côté VPS ── */
async function analyzeServer() {
  loading.textContent = "Analyse côté serveur… (premier démarrage ~30 s)";
  const fd = new FormData();
  fd.append("image", currentFile);
  const r = await fetch(`${await apiBase()}/api/scan`, { method: "POST", body: fd });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || "Erreur serveur");
  return data;
}

/* ── Bouton Analyser ── */
analyzeBtn.addEventListener("click", async () => {
  if (!currentFile) return;
  errorAlert.hidden = true;
  loading.hidden = false;
  analyzeBtn.disabled = true;
  try {
    let data = null;
    if (onnxSession) {
      try {
        data = await analyzeLocal();
      } catch (e) {
        console.warn("[scanner] Local échoué, fallback serveur :", e.message);
      }
    }
    if (!data) data = await analyzeServer();
    renderResult(data);
  } catch (err) {
    showError("Analyse impossible : " + err.message);
  } finally {
    loading.hidden = true;
    analyzeBtn.disabled = false;
  }
});

function badge(text, cls) {
  return `<span class="badge ${cls || ""}">${text}</span>`;
}

function renderResult(data) {
  currentScan = data;
  document.getElementById("scanner-section").hidden = true;
  document.getElementById("result-section").hidden = false;
  document.getElementById("result-img").src = data.annotated_url || data.image_url || "";

  const badges = [];
  if (!data.found) {
    badges.push(badge("Aucun conteneur détecté", "badge-warn"));
  } else {
    if (data.local_detection) {
      badges.push(badge("Détection locale ⚡", "badge-ok"));
    }
    if (data.container_found) {
      badges.push(badge(`Conteneur ${Math.round((data.yolo_confidence || 0) * 100)} %`));
    } else {
      badges.push(badge("Gros plan — lecture directe de la zone BIC", "badge-info"));
    }
    if (data.vertical)      badges.push(badge("Texte vertical (ROI pivotée)", "badge-info"));
    if (data.bic_zone_found) badges.push(badge("Zone BIC localisée", "badge-info"));
    if (data.bic && data.valid && data.corrected) {
      badges.push(badge("Chiffre de contrôle recalculé — vérifiez le code", "badge-warn"));
    } else if (data.bic && data.valid) {
      badges.push(badge("BIC valide (ISO 6346)", "badge-ok"));
    } else if (data.bic) {
      badges.push(badge("Chiffre de contrôle incorrect", "badge-warn"));
    } else {
      badges.push(badge("Aucun BIC lu par l'OCR", "badge-warn"));
    }
  }
  document.getElementById("result-badges").innerHTML = badges.join("");
  document.getElementById("result-raw").textContent =
    data.raw_text ? "Texte OCR brut : " + data.raw_text : "";
  document.getElementById("bic").value = data.bic || "";
}

/* ── Confirmer / Rejeter ── */
document.getElementById("confirm-btn").addEventListener("click", async () => {
  const bic = document.getElementById("bic").value.replace(/\s/g, "").toUpperCase();
  if (!bic) return;
  try {
    const r = await fetch(`${await apiBase()}/api/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bic,
        ocr_confidence: currentScan?.ocr_confidence ?? null,
        image_name:     currentScan?.image_name     ?? null,
      }),
    });
    if (!r.ok) throw new Error("Erreur serveur");
    window.location.href = "history.html";
  } catch (err) {
    showError("Enregistrement impossible : " + err.message);
  }
});

document.getElementById("reject-btn").addEventListener("click", () => {
  window.location.reload();
});
