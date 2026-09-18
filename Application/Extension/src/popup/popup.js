import { BackendApi } from "../services/backend-api.js";
import { DEFAULT_BACKEND_URL } from "../../config/default.js";
import { setStatus } from "../utils/status.js";

const $ = (id) => document.getElementById(id);
const api = new BackendApi(DEFAULT_BACKEND_URL);
$("backend-url").textContent = DEFAULT_BACKEND_URL;

let session = null;
let statusPoll = null;
let recTimerInterval = null;
let recStartTime = null;

function status(state, message) {
  setStatus($("status-dot"), $("status-text"), state, message);
}

$("btn-connect").addEventListener("click", async () => {
  const url = $("rtsp-url").value.trim();
  if (!url) { status("error", "adresse RTSP manquante"); return; }
  if (!url.toLowerCase().startsWith("rtsp://")) {
    status("error", "l'adresse doit commencer par rtsp://");
    return;
  }

  $("btn-connect").disabled = true;
  status("connecting", "Connexion…");
  try {
    const d = await api.rtspConnect(url);
    session = d.session;
    status("connected");
    $("meta-res").textContent = d.resolution || "—";
    $("meta-fps").textContent = d.fps != null ? `${d.fps} fps` : "—";
    $("preview-panel").hidden = false;
    $("preview-img").src = api.rtspPreviewUrl(session);
    $("btn-connect").hidden = true;
    $("btn-disconnect").hidden = false;
    statusPoll = setInterval(pollStatus, 3000);
  } catch (e) {
    status("error", e.message);
  } finally {
    $("btn-connect").disabled = false;
  }
});

$("btn-disconnect").addEventListener("click", async () => {
  await teardown();
  status("disconnected");
});

async function teardown() {
  if (statusPoll) { clearInterval(statusPoll); statusPoll = null; }
  if (recTimerInterval) { clearInterval(recTimerInterval); recTimerInterval = null; }
  if (session) {
    try { await api.rtspDisconnect(session); } catch { /* déjà perdue, tant pis */ }
  }
  session = null;
  $("preview-panel").hidden = true;
  $("preview-img").src = "";
  $("btn-connect").hidden = false;
  $("btn-disconnect").hidden = true;
  $("btn-rec-start").hidden = false;
  $("btn-rec-stop").hidden = true;
  $("rec-timer").hidden = true;
  $("analysis-panel").hidden = true;
  $("results-panel").hidden = true;
  $("hide-uncertain").checked = false;
  lastCodes = [];
}

// ── Phase D : enregistrement ───────────────────────────────────────────

$("btn-rec-start").addEventListener("click", async () => {
  if (!session) return;
  $("btn-rec-start").disabled = true;
  try {
    await api.rtspRecordStart(session);
    recStartTime = Date.now();
    $("btn-rec-start").hidden = true;
    $("btn-rec-stop").hidden = false;
    $("rec-timer").hidden = false;
    updateRecTimer();
    recTimerInterval = setInterval(updateRecTimer, 500);
  } catch (e) {
    status("error", e.message);
  } finally {
    $("btn-rec-start").disabled = false;
  }
});

$("btn-rec-stop").addEventListener("click", async () => {
  if (!session) return;
  if (recTimerInterval) { clearInterval(recTimerInterval); recTimerInterval = null; }
  $("btn-rec-stop").disabled = true;
  try {
    const d = await api.rtspRecordStop(session);
    $("btn-rec-stop").hidden = true;
    $("btn-rec-start").hidden = false;
    $("rec-timer").hidden = true;
    await runAnalysis(d.recording);
  } catch (e) {
    status("error", e.message);
  } finally {
    $("btn-rec-stop").disabled = false;
  }
});

function updateRecTimer() {
  const s = Math.floor((Date.now() - recStartTime) / 1000);
  $("rec-timer").textContent =
    `🔴 ${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

// ── Phase E : analyse (pipeline vidéo existant, Tasks 1/2 — aucune
// logique YOLO/OCR dupliquée ici, seulement l'affichage du flux NDJSON) ──

async function runAnalysis(recordingName) {
  $("results-panel").hidden = true;
  $("results-list").innerHTML = "";
  $("analysis-panel").hidden = false;
  $("progress-bar").style.width = "0%";
  $("progress-text").textContent = "Ouverture de la vidéo…";

  const { modelId, ocrEngine } = await pickEngines();

  try {
    await api.detectVideo({ recording: recordingName, modelId, ocrEngine }, (evt) => {
      if (evt.type === "meta") {
        $("progress-text").textContent = `${evt.to_analyze} frames à analyser (${evt.analysis_fps} FPS)`;
      } else if (evt.type === "progress") {
        $("progress-bar").style.width = `${evt.pct}%`;
        $("progress-text").textContent =
          `${evt.analyzed}/${evt.to_analyze} · ${evt.pct}% · ${evt.codes} code(s)`;
      } else if (evt.type === "done") {
        $("progress-bar").style.width = "100%";
        $("progress-text").textContent = `Terminé — ${evt.analyzed} frames en ${evt.elapsed}s`;
        renderResults(evt.codes);
      } else if (evt.type === "error") {
        throw new Error(evt.error);
      }
    });
  } catch (e) {
    $("progress-text").textContent = `Échec : ${e.message}`;
  }
}

/** Choisit les "meilleurs" modèle/moteur OCR (best/yolo, best/ocr) s'ils
 * existent, sinon se replie sur le premier modèle/moteur disponible —
 * jamais une valeur codée en dur qui pourrait ne pas exister. */
async function pickEngines() {
  let modelId = "best/yolo";
  let ocrEngine = "best/ocr";
  try {
    const { models, ocr_engines } = await api.models();
    if (!models.some((m) => m.id === modelId)) modelId = models[0]?.id;
    if (!ocr_engines.some((e) => e.id === ocrEngine)) ocrEngine = ocr_engines[0]?.id || "easyocr";
  } catch {
    // liste indisponible : on tente quand même avec les valeurs par défaut,
    // detectVideo() remontera une erreur claire si elles n'existent pas.
  }
  return { modelId, ocrEngine };
}

let lastCodes = [];

function renderResults(codes) {
  lastCodes = codes;
  $("results-panel").hidden = false;
  renderResultsList();
}

/** Un code "confirmé" = chiffre de contrôle authentique OU vu sur >= 2
 * frames (vote temporel) — même critère que labo.html (onglet Vidéo) : une
 * lecture à un seul vote et recalculée est la plus susceptible d'être du
 * bruit OCR, pas un vrai code. Filtre optionnel, jamais des données cachées
 * silencieusement : la case précise ce qu'elle masque. */
function renderResultsList() {
  const hideUncertain = $("hide-uncertain").checked;
  const sorted = [...lastCodes].sort((a, b) => (b.valid - a.valid) || (b.count - a.count));
  const shown = hideUncertain ? sorted.filter((c) => c.valid || c.count >= 2) : sorted;

  if (!sorted.length) {
    $("results-list").innerHTML = `<p class="hint">Aucun code BIC détecté.</p>`;
    return;
  }
  if (!shown.length) {
    $("results-list").innerHTML = `<p class="hint">Tous les codes détectés sont incertains (décoche le filtre pour les voir).</p>`;
    return;
  }
  $("results-list").innerHTML = shown.map((c) => `
    <div class="result-item ${c.valid ? "ok" : "warn"}">
      ${c.crop ? `<img src="${c.crop}" alt="">` : ""}
      <div>
        <div class="result-code">
          ${c.bic}
          <button class="btn-copy" data-code="${c.bic}" title="Copier le code">📋</button>
        </div>
        <div class="result-meta">${c.valid ? "✔ authentique" : "⚠ recalculé"} · ${c.count} frame(s)</div>
      </div>
    </div>`).join("");
}

$("hide-uncertain").addEventListener("change", renderResultsList);

/** Copie un code BIC dans le presse-papiers (bouton 📋 de chaque résultat).
 * L'extension (chrome-extension://) est un contexte sécurisé : l'API
 * Clipboard fonctionne sans permission supplémentaire, déclenchée par un
 * geste utilisateur (le clic). */
async function copyCode(btn) {
  const code = btn.dataset.code;
  try {
    await navigator.clipboard.writeText(code);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = code; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch { /* rien de plus a tenter */ }
    document.body.removeChild(ta);
  }
  const original = btn.textContent;
  btn.textContent = "✔";
  btn.classList.add("copied");
  setTimeout(() => { btn.textContent = original; btn.classList.remove("copied"); }, 1200);
}

$("results-list").addEventListener("click", (e) => {
  const btn = e.target.closest(".btn-copy");
  if (btn) copyCode(btn);
});

async function pollStatus() {
  if (!session) return;
  try {
    const st = await api.rtspStatus(session);
    if (!st.connected) {
      await teardown();
      status("error", st.error || "connexion perdue");
    }
  } catch {
    await teardown();
    status("error", "session perdue (backend redémarré ?)");
  }
}
