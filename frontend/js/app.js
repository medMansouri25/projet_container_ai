/* app.js — Scanner : upload/caméra → POST /api/scan → panneau résultat.
   Front statique (Vercel) ; le backend Flask tourne sur le VPS (API_BASE). */

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

let currentFile = null;
let currentScan = null;
let stream = null;

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

/* ── Analyse ── */
analyzeBtn.addEventListener("click", async () => {
  if (!currentFile) return;
  loading.hidden = false;
  analyzeBtn.disabled = true;
  try {
    const fd = new FormData();
    fd.append("image", currentFile);
    const r = await fetch(`${await apiBase()}/api/scan`, { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Erreur serveur");
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
  document.getElementById("result-img").src = data.image_url;

  const badges = [];
  if (!data.found) {
    badges.push(badge("Aucun conteneur détecté", "badge-warn"));
  } else {
    if (data.container_found) {
      badges.push(badge(`Conteneur ${Math.round(data.yolo_confidence * 100)}%`));
    } else {
      badges.push(badge("Gros plan — lecture directe de la zone BIC", "badge-info"));
    }
    if (data.vertical) badges.push(badge("Texte vertical (ROI pivotée)", "badge-info"));
    if (data.bic_zone_found) badges.push(badge("Zone BIC localisée par le modèle", "badge-info"));
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
        ocr_confidence: currentScan ? currentScan.ocr_confidence : null,
        image_name: currentScan ? currentScan.image_name : null,
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
