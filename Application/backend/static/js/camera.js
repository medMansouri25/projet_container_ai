/* camera.js — capture caméra (getUserMedia) + drag & drop + aperçu.
   La photo capturée est injectée dans l'input file du formulaire :
   le POST /scan reste un envoi de formulaire classique. */

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

let stream = null;

/* ── Aperçu après sélection de fichier ── */
function showPreview(file) {
  previewImg.src = URL.createObjectURL(file);
  dropzone.hidden = true;
  cameraZone.hidden = true;
  previewZone.hidden = false;
}

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) showPreview(fileInput.files[0]);
});

resetBtn.addEventListener("click", () => {
  fileInput.value = "";
  previewZone.hidden = true;
  dropzone.hidden = false;
});

/* ── Drag & drop ── */
["dragenter", "dragover"].forEach(evt =>
  dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.classList.add("dragover"); }));
["dragleave", "drop"].forEach(evt =>
  dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.classList.remove("dragover"); }));

dropzone.addEventListener("drop", e => {
  const file = e.dataTransfer.files[0];
  if (!file || !file.type.startsWith("image/")) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  fileInput.files = dt.files;
  showPreview(file);
});

/* ── Caméra (HTTPS requis → Cloudflare Tunnel en prod) ── */
cameraBtn.addEventListener("click", async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1920 } }
    });
    video.srcObject = stream;
    dropzone.hidden = true;
    cameraZone.hidden = false;
  } catch (err) {
    alert("Camera inaccessible : " + err.message + "\n(HTTPS requis pour getUserMedia)");
  }
});

function stopCamera() {
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  cameraZone.hidden = true;
}

closeBtn.addEventListener("click", () => { stopCamera(); dropzone.hidden = false; });

captureBtn.addEventListener("click", () => {
  canvas.width  = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  canvas.toBlob(blob => {
    const file = new File([blob], "capture.jpg", { type: "image/jpeg" });
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    stopCamera();
    showPreview(file);
  }, "image/jpeg", 0.92);
});
