/* detect.js — logique PURE de détection (partagée navigateur + tests node).
   Aucune dépendance onnxruntime : ne traite que des tableaux de nombres.
   L'inférence réelle (onnxruntime-web) vit ailleurs et appelle ces fonctions. */

/* Parse la sortie brute YOLO ONNX (1, 4+nc, N) stockée en channel-major :
   4 coords de boîte (cx,cy,w,h) + nc scores de classe, sur N ancres.
   Retourne les boîtes au-dessus du seuil : {x,y,w,h,score,cls} (x,y = coin haut-gauche). */
export function parseYoloOutput(data, { numClasses, imgSize = 640, confThreshold = 0.25 }) {
  const channels = 4 + numClasses;
  const n = data.length / channels;           // nombre d'ancres
  const boxes = [];
  for (let i = 0; i < n; i++) {
    let best = 0, cls = 0;
    for (let k = 0; k < numClasses; k++) {
      const s = data[(4 + k) * n + i];
      if (s > best) { best = s; cls = k; }
    }
    if (best < confThreshold) continue;
    const cx = data[i], cy = data[n + i], w = data[2 * n + i], h = data[3 * n + i];
    boxes.push({ x: cx - w / 2, y: cy - h / 2, w, h, score: best, cls });
  }
  return boxes;
}

/* Intersection-over-Union de deux boîtes {x,y,w,h} (coin haut-gauche). */
export function iou(a, b) {
  const x1 = Math.max(a.x, b.x), y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.w, b.x + b.w), y2 = Math.min(a.y + a.h, b.y + b.h);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const union = a.w * a.h + b.w * b.h - inter;
  return union <= 0 ? 0 : inter / union;
}

/* Non-Max Suppression : trie par score décroissant, écarte toute boîte trop
   chevauchante (IoU ≥ seuil) avec une déjà retenue. */
export function nms(boxes, iouThreshold = 0.45) {
  const kept = [];
  for (const b of [...boxes].sort((p, q) => q.score - p.score)) {
    if (kept.every((k) => iou(k, b) < iouThreshold)) kept.push(b);
  }
  return kept;
}

/* La boîte la plus confiante, ou null si aucune. */
export function bestBox(boxes) {
  return boxes.length ? boxes.reduce((a, b) => (b.score > a.score ? b : a)) : null;
}

/* Repère de distance (E1) : à partir de l'aire relative de la boîte dans la
   frame carrée imgSize×imgSize, indique à l'agent s'il doit s'approcher/reculer
   et si le cadrage est assez bon pour déclencher la capture (OCR).
   Seuils par défaut ajustables selon le terrain (validés en run). */
export function distanceGuide(box, imgSize = 640, { minRatio = 0.06, maxRatio = 0.6 } = {}) {
  if (!box) return { state: "aucun", capture: false };
  const ratio = (box.w * box.h) / (imgSize * imgSize);
  if (ratio < minRatio) return { state: "trop_loin", capture: false };
  if (ratio > maxRatio) return { state: "trop_pres", capture: false };
  return { state: "bon", capture: true };
}

/* Instants (secondes) auxquels échantillonner une vidéo importée : 0, puis tous
   les `everySeconds`, borne `duration` incluse si elle tombe pile. */
export function sampleFrameTimes(duration, everySeconds) {
  if (everySeconds <= 0) throw new Error("everySeconds doit être > 0");
  const times = [];
  for (let t = 0; t <= duration + 1e-9; t += everySeconds) {
    times.push(Math.round(t * 1000) / 1000);
  }
  return times;
}

/* Ramène une boîte détectée dans l'espace modèle letterboxé (640) vers les
   pixels de l'image d'origine : retire le padding puis divise par l'échelle. */
export function scaleBoxToImage(box, { scale, padX, padY }) {
  return {
    x: (box.x - padX) / scale,
    y: (box.y - padY) / scale,
    w: box.w / scale,
    h: box.h / scale,
    score: box.score,
    cls: box.cls,
  };
}
