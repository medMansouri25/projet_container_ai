/* webdetect.js — glue onnxruntime-web (intégration, vérifiée en run).
   Charge un modèle .onnx exporté (export_onnx.py), infère sur une source
   image/vidéo/canvas et post-traite via la logique pure de detect.js.
   `ort` est fourni globalement par onnxruntime-web (chargé en <script>). */

import { parseYoloOutput, nms, bestBox, distanceGuide, scaleBoxToImage, sampleFrameTimes } from "./detect.js";

export const IMG = 640;

// Modèles servis par le VPS Flask (/models/<name>) — cache SW après 1er téléchargement.
// nc : plaque=1 (immatriculation), conteneur=1 (NumeroBIC, modèle spécialiste bic/)
const _VPS = typeof window !== "undefined" && window.API_BASE
  ? window.API_BASE : "https://api.containerai-marsa-maroc.online";

export const MODELS = {
  plaque:    { url: `${_VPS}/models/plaque.onnx`,    numClasses: 1 },
  conteneur: { url: `${_VPS}/models/conteneur.onnx`, numClasses: 1 },
};

export async function loadSession(url) {
  return ort.InferenceSession.create(url, {
    executionProviders: ["wasm"],
    graphOptimizationLevel: "all",
  });
}

/* Letterbox une source (HTMLImageElement / HTMLVideoElement / canvas) en
   640×640 (fond gris), renvoie le tenseur CHW normalisé + les paramètres
   letterbox pour remapper les boîtes vers l'image d'origine. */
export function preprocess(source, srcW, srcH) {
  const scale = Math.min(IMG / srcW, IMG / srcH);
  const newW = Math.round(srcW * scale), newH = Math.round(srcH * scale);
  const padX = Math.floor((IMG - newW) / 2), padY = Math.floor((IMG - newH) / 2);

  const canvas = document.createElement("canvas");
  canvas.width = IMG; canvas.height = IMG;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#727272";
  ctx.fillRect(0, 0, IMG, IMG);
  ctx.drawImage(source, padX, padY, newW, newH);

  const { data } = ctx.getImageData(0, 0, IMG, IMG);   // RGBA plat
  const area = IMG * IMG;
  const tensor = new Float32Array(3 * area);
  for (let i = 0; i < area; i++) {
    tensor[i]            = data[i * 4]     / 255;  // R
    tensor[area + i]     = data[i * 4 + 1] / 255;  // G
    tensor[2 * area + i] = data[i * 4 + 2] / 255;  // B
  }
  return { tensor, lb: { scale, padX, padY } };
}

/* Détecte la meilleure boîte sur une source + calcule le repère de distance.
   Retourne {box|null (coords image d'origine), guide:{state,capture}, count}. */
export async function detect(session, source, srcW, srcH, { numClasses = 1, conf = 0.25 } = {}) {
  const { tensor, lb } = preprocess(source, srcW, srcH);
  const input = new ort.Tensor("float32", tensor, [1, 3, IMG, IMG]);
  const output = await session.run({ [session.inputNames[0]]: input });
  const data = output[session.outputNames[0]].data;

  let boxes = parseYoloOutput(data, { numClasses, imgSize: IMG, confThreshold: conf });
  boxes = nms(boxes, 0.45);
  const best = bestBox(boxes);
  return {
    box:   best ? scaleBoxToImage(best, lb) : null,
    boxes: boxes.map((b) => scaleBoxToImage(b, lb)),
    guide: distanceGuide(best, IMG),
    count: boxes.length,
  };
}

/* Positionne un <video> à l'instant t (secondes) et résout quand la frame est prête. */
export function seekTo(video, t) {
  return new Promise((resolve) => {
    const onSeeked = () => { video.removeEventListener("seeked", onSeeked); resolve(); };
    video.addEventListener("seeked", onSeeked);
    video.currentTime = Math.min(t, Math.max(0, video.duration - 0.01));
  });
}

/* Détecte sur une vidéo importée en échantillonnant une frame tous les
   `everySeconds`. Appelle onFrame(t, res) au fil de l'eau. Retourne la liste
   des résultats. (Mode « vidéo importée » du sélecteur multi-source.) */
export async function detectVideoFrames(session, video,
    { everySeconds = 1.0, numClasses = 1, conf = 0.25, onFrame } = {}) {
  const results = [];
  for (const t of sampleFrameTimes(video.duration, everySeconds)) {
    await seekTo(video, t);
    const res = await detect(session, video, video.videoWidth, video.videoHeight,
                             { numClasses, conf });
    results.push({ t, ...res });
    if (onFrame) onFrame(t, res);
  }
  return results;
}
