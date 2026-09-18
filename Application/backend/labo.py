"""labo.py — Labo de comparaison de modèles de détection BIC.

Découvre les modèles .pt comparables sous Application/models :
  - bic/best_v*.pt              (production VPS, yolo11s)
  - bic_browser/best_v*.pt      (navigateur, yolo11n)
  - bic_bench/best_config*.pt   (sorties de la campagne benchmark multi-configs,
                                 métriques dans bic_bench/metadata.json)

Et exécute une inférence YOLO sur une image importée pour renvoyer les zones
détectées + l'image annotée (base64). Les modèles chargés sont mis en cache.
"""
import base64
import glob
import json
import os
import time

# Dossiers versionnés (best_v*.pt) à scanner, avec libellé humain
_VERSIONED_DIRS = [
    ("bic",         "BIC serveur (yolo11s)"),
    ("bic_browser", "BIC navigateur (yolo11n)"),
]
_BENCH_DIR = "bic_bench"   # une sous-arborescence par config : <config>/best.pt


def _meta_entry(meta_path, version):
    """Entrée metadata.json d'une version, ou {} si indisponible."""
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f).get(version, {})
    except (OSError, ValueError):
        return {}


def _train_imgsz(entry):
    """Résolution d'ENTRAÎNEMENT du modèle, indispensable à l'inférence :
    évaluer un modèle entraîné à 1280 px avec le défaut 640 px le handicape
    lourdement (config2_hires 960, config10 1280). Les deux schémas de
    metadata coexistent : `params` (bench) et `hyperparameters` (versionnés)."""
    for key in ("params", "hyperparameters"):
        size = entry.get(key, {}).get("imgsz")
        if size:
            return int(size)
    return 640


def _tutor_root(models_root):
    """RessourceFourni/ à la racine du projet (models_root = Application/models)."""
    return os.path.abspath(os.path.join(models_root, "..", "..",
                                        "RessourceFourni"))


def discover_tutor_region_models(models_root):
    """Modèles de détection de zone fournis par le tuteur.

    Même tâche que nos détecteurs BIC (classe `container_code_region`), donc
    directement comparables dans le Labo. Le glob passe par `*/region_models`
    pour ne pas dépendre du nom exact du dossier parent (accents).
    Certains fichiers sont au format YOLOv5, incompatible avec l'ultralytics
    installé : ils sont listés quand même et l'échec remonte à l'inférence,
    plutôt que de charger 7 modèles à chaque appel pour les filtrer.
    """
    out = []
    pattern = os.path.join(_tutor_root(models_root), "*", "region_models", "*.pt")
    for path in sorted(glob.glob(pattern)):
        name = os.path.splitext(os.path.basename(path))[0]
        out.append({
            "id": f"tuteur/region/{name}", "label": f"Tuteur · {name}",
            "path": path, "map50_95": None, "imgsz": 960 if "960" in name else 640,
            "group": "tuteur",
        })
    return out


def discover_ocr_engines(models_root):
    """Moteurs de lecture disponibles pour comparaison.

    EasyOCR est le moteur historique du projet. Les modèles du tuteur sont des
    détecteurs de CARACTÈRES YOLO (36 classes : 0-9 + A-Z) : ils lisent chaque
    caractère indépendamment, donc l'orientation du texte n'a plus d'importance
    — piste directe contre l'échec systématique sur les codes verticaux.
    Ils se branchent via char_reader.read_bic(model_path=...).
    """
    engines = [{"id": "easyocr", "label": "EasyOCR (actuel)", "path": None,
                "group": "mien"}]
    best_ocr = os.path.join(models_root, "bestOCR.pt")
    if os.path.exists(best_ocr):
        engines.append({"id": "best/ocr", "label": "★ Meilleur OCR (bestOCR.pt)",
                        "path": best_ocr, "group": "mien"})
    pattern = os.path.join(_tutor_root(models_root), "*", "ocr_models", "*.pt")
    for path in sorted(glob.glob(pattern)):
        name = os.path.splitext(os.path.basename(path))[0]
        engines.append({"id": f"tuteur/ocr/{name}",
                        "label": f"Tuteur · {name}",
                        "path": path, "group": "tuteur"})
    return engines


def discover_models(models_root):
    """Liste les modèles BIC comparables : [{id, label, path, map50_95, group}].

    `group` distingue mes modèles ("mien") de ceux du tuteur ("tuteur") pour
    que le Labo puisse séparer visuellement les deux familles.
    """
    models = []

    for dirname, human in _VERSIONED_DIRS:
        folder = os.path.join(models_root, dirname)
        meta = os.path.join(folder, "metadata.json")
        for path in sorted(glob.glob(os.path.join(folder, "best_v*.pt"))):
            version = os.path.splitext(os.path.basename(path))[0].replace("best_", "")
            entry = _meta_entry(meta, version)
            models.append({
                "id":       f"{dirname}/best_{version}",
                "label":    f"{human} {version}",
                "path":     path,
                "map50_95": entry.get("mAP50_95"),
                "imgsz":    _train_imgsz(entry),
                "group":    "mien",
            })

    bench_root = os.path.join(models_root, _BENCH_DIR)
    meta = os.path.join(bench_root, "metadata.json")
    for path in sorted(glob.glob(os.path.join(bench_root, "best_config*.pt"))):
        config = os.path.splitext(os.path.basename(path))[0].replace("best_", "")
        entry = _meta_entry(meta, config)
        models.append({
            "id":       f"bench/{config}",
            "label":    f"Benchmark {config}",
            "path":     path,
            "map50_95": entry.get("mAP50_95"),
            "imgsz":    _train_imgsz(entry),
            "group":    "mien",
        })

    # Détecteurs multi-code (dataset MultiCodeBic, 5 classes) — détectent TOUS
    # les codes d'une image (ADR-18). config11 = yolo11s 960 ; config14 = tête
    # P2 1280 (petits objets). Découverts dès que leur best est présent.
    mc_dir = os.path.join(models_root, "multicode")
    for fname, mid, label, imgsz in [
        ("best.pt",           "multicode/config11", "config11 multi-code (yolo11s 960px)", 960),
        ("best_config14.pt",  "multicode/config14", "config14 multi-code (P2 1280px)",    1280),
    ]:
        pth = os.path.join(mc_dir, fname)
        if os.path.exists(pth):
            models.append({
                "id": mid, "label": label, "path": pth,
                "map50_95": None, "imgsz": imgsz, "group": "mien",
            })

    # Meilleur modèle courant, placé directement sous Application/models/ par
    # commodité (identique en contenu à multicode/config11 au moment de son
    # ajout, mais listé explicitement pour rester le pointeur "à jour" même
    # si un futur entraînement le remplace sans toucher au dossier multicode/).
    best_pt = os.path.join(models_root, "bestYolo.pt")
    if os.path.exists(best_pt):
        models.append({
            "id": "best/yolo", "label": "★ Meilleur modèle (bestYolo.pt)",
            "path": best_pt, "map50_95": None, "imgsz": 960, "group": "mien",
        })

    models.extend(discover_tutor_region_models(models_root))
    return models


# ── Inférence (frontière YOLO — vérifiée en run, pas en test unitaire) ──

_model_cache = {}
_v5_ready = False


def _enable_v5():
    """Prépare le runtime YOLOv5 (paquet `yolov5`) pour les poids anciens.

    Trois obstacles, tous levés ici une seule fois :
      - torch >= 2.6 impose weights_only=True par défaut ; yolov5 7.0.14
        (2023) appelle torch.load sans ce paramètre → on repasse en
        weights_only=False (poids locaux fournis par le tuteur, même niveau
        de confiance que les .pt chargés par ultralytics).
      - certains poids ont été entraînés sous Linux et leur pickle contient
        un PosixPath, non instanciable sous Windows.
      - yolov5 exige huggingface-hub < 0.25 (épinglé dans requirements).
    """
    import functools
    import pathlib
    import sys

    import torch

    global _v5_ready
    if not _v5_ready:
        torch.load = functools.partial(torch.load, weights_only=False)
        if os.name == "nt":
            pathlib.PosixPath = pathlib.WindowsPath
        _v5_ready = True

    # À REFAIRE AVANT CHAQUE CHARGEMENT v5 : une tentative ultralytics qui
    # échoue laisse ses propres alias dans sys.modules['models'/'utils']
    # (couche de compatibilité). Le dépicklage v5 instancierait alors des
    # classes ultralytics — d'où « BaseModel.fuse() got an unexpected keyword
    # argument 'verbose' ». On réécrit donc les alias (pas de setdefault).
    import yolov5.models.common
    import yolov5.models.yolo
    import yolov5.utils.general
    sys.modules["models"] = sys.modules["yolov5.models"]
    sys.modules["models.yolo"] = sys.modules["yolov5.models.yolo"]
    sys.modules["models.common"] = sys.modules["yolov5.models.common"]
    sys.modules["utils"] = sys.modules["yolov5.utils"]
    sys.modules["utils.general"] = sys.modules["yolov5.utils.general"]


def _get_model(path):
    """Charge un modèle avec le runtime approprié.

    ultralytics (YOLOv8+) d'abord ; en cas d'incompatibilité de format, repli
    sur le paquet `yolov5`. Le modèle renvoyé est encapsulé pour offrir la
    même interface `.predict(...)` dans les deux cas (cf. _V5Model).
    """
    if path not in _model_cache:
        loaded = None
        try:
            from ultralytics import YOLO
            import numpy as np
            m = YOLO(path)
            # VALIDATION : certains poids v5 se CHARGENT dans ultralytics sans
            # erreur mais cassent à l'inférence (`forward() got 'embed'`,
            # `fuse(verbose=...)`). On force une micro-inférence pour trancher
            # ici et non au premier scan de l'utilisateur.
            m.predict(np.zeros((64, 64, 3), dtype=np.uint8), verbose=False)
            loaded = m
        except Exception:
            loaded = None
        if loaded is None:
            # Repli v5 : chargement ET inférence ultralytics ont échoué.
            _enable_v5()
            import yolov5
            loaded = _V5Model(yolov5.load(path))
        _model_cache[path] = loaded
    return _model_cache[path]


class _V5Model:
    """Adaptateur : expose l'API `.predict()` d'ultralytics pour un modèle v5.

    Les résultats v5 (`.xyxy[0]`) sont traduits en objets porteurs de `.boxes`
    avec `.xyxy` et `.conf`, plus un `.plot()` qui dessine les boîtes — le
    strict nécessaire pour que run_detect() n'ait pas à connaître le runtime.
    """

    def __init__(self, model):
        self.model = model
        self.names = model.names

    def predict(self, source, conf=0.15, imgsz=640, verbose=False, **_):
        import cv2
        self.model.conf = conf
        img = cv2.imread(source) if isinstance(source, str) else source
        res = self.model(img[:, :, ::-1], size=imgsz)   # v5 attend du RGB
        return [_V5Result(res.xyxy[0], img, self.names)]

    # char_reader appelle le modèle directement : model(image, verbose=False)
    def __call__(self, source, conf=0.15, imgsz=640, verbose=False, **kw):
        return self.predict(source, conf=conf, imgsz=imgsz, verbose=verbose)


class _V5Result:
    def __init__(self, det, img, names):
        self.boxes = [_V5Box(row) for row in det.tolist()]
        self._img, self._names = img, names
        self.names = names          # attendu par char_reader._detections

    def plot(self):
        import cv2
        out = self._img.copy()
        for b in self.boxes:
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0]]
            cv2.rectangle(out, (x1, y1), (x2, y2), (255, 120, 0), 2)
            label = f"{self._names.get(b._cls, '?')} {b.conf[0]:.2f}"
            cv2.putText(out, label, (x1, max(12, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 120, 0), 2)
        return out


class _V5Box:
    def __init__(self, row):
        self.xyxy = [row[:4]]
        self.conf = [row[4]]
        self._cls = int(row[5]) if len(row) > 5 else 0
        self.cls = [self._cls]      # attendu par char_reader._detections


def run_detect(model_path, source, conf=0.15, imgsz=640, annotate=True):
    """Inférence YOLO sur une image. Retourne zones, temps et image annotée.

    `source` : chemin fichier OU frame ndarray BGR (les frames vidéo passent
    directement l'array, sans écriture disque).
    `imgsz` doit être la résolution d'ENTRAÎNEMENT du modèle (cf.
    _train_imgsz) : inférer à 640 un modèle entraîné à 1280 le handicape.
    `annotate=False` saute le rendu de l'image annotée (plot + JPEG) — utile
    en vidéo où on traite beaucoup de frames et n'en a pas besoin par frame.

    {time_ms, boxes: [{x, y, w, h, conf, cls}], annotated_b64 (jpeg|None)}
    """
    import cv2

    model = _get_model(model_path)
    t0 = time.perf_counter()
    results = model.predict(source, conf=conf, imgsz=imgsz, verbose=False)
    elapsed_ms = round((time.perf_counter() - t0) * 1000)

    r = results[0]
    names = getattr(r, "names", None) or getattr(model, "names", {})
    boxes = []
    for b in r.boxes:
        x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
        cls_id = int(b.cls[0]) if getattr(b, "cls", None) is not None else -1
        boxes.append({
            "x": round(x1), "y": round(y1),
            "w": round(x2 - x1), "h": round(y2 - y1),
            "conf": round(float(b.conf[0]), 3),
            "cls": names.get(cls_id, "") if isinstance(names, dict) else "",
        })

    annotated_b64 = None
    if annotate:
        annotated = r.plot()                      # BGR ndarray avec boîtes
        ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 88])
        annotated_b64 = base64.b64encode(buf).decode() if ok else None

    return {"time_ms": elapsed_ms, "boxes": boxes, "annotated_b64": annotated_b64}


# Classes « code taille ISO » (22G1/45G1) des détecteurs multi-classes : à NE
# PAS passer à l'OCR (ce ne sont pas des codes BIC). Mono-classe → cls="".
_TYPE_CLASSES = {"Htype", "Vtype"}


def _prep_crop(crop):
    """Agrandit un petit crop avant l'OCR : le détecteur de caractères lit
    mieux des glyphes plus grands. Cible ~180 px sur le petit côté."""
    import cv2
    h, w = crop.shape[:2]
    short = min(h, w)
    if short and short < 180:
        s = min(3.0, 180.0 / short)
        crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    return crop


def read_zones(img_bgr, boxes, read_fn, do_ocr=True, want_crops=True, max_zones=20):
    """CŒUR PARTAGÉ image + vidéo — extrait sans changement de la boucle OCR
    du endpoint image. Pour chaque boîte : crop (+6 % marge), routage par classe
    (skip type ISO), upscale, OCR via `read_fn(crop, vertical) -> {bic,valid,
    corrected,raw}`, déduplication par code. Aucun état Flask ici.

    Retourne (zones, ocr_results) : `zones` = une entrée par boîte (avec crop
    encodé si want_crops) ; `ocr_results` = codes uniques triés authentique d'abord.
    """
    import base64

    import cv2

    def _b64(im):
        ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else None

    H, W = img_bgr.shape[:2]
    ordered = sorted(boxes, key=lambda b: b["conf"], reverse=True)[:max_zones]
    zones, results, seen = [], [], set()
    for i, b in enumerate(ordered):
        pad_w, pad_h = b["w"] * 0.06, b["h"] * 0.06
        x1 = max(0, int(b["x"] - pad_w));  y1 = max(0, int(b["y"] - pad_h))
        x2 = min(W, int(b["x"] + b["w"] + pad_w))
        y2 = min(H, int(b["y"] + b["h"] + pad_h))
        crop = img_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        cls = b.get("cls", "")
        z = {"index": i + 1, "box": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
             "conf": round(b["conf"], 3), "cls": cls,
             "crop": _b64(crop) if want_crops else None,
             "bic": None, "valid": False, "corrected": False, "raw_text": ""}
        if do_ocr and cls not in _TYPE_CLASSES:
            oc = _prep_crop(crop)
            r = read_fn(oc, False)
            if not r["bic"]:
                rv = read_fn(oc, True)
                if rv["bic"]:
                    r = rv
            if r["bic"]:
                z.update(bic=r["bic"], valid=r["valid"], corrected=r["corrected"],
                         raw_text=" | ".join(r["raw"]))
                if r["bic"] not in seen:
                    seen.add(r["bic"])
                    results.append({"bic": r["bic"], "valid": r["valid"],
                                    "corrected": r["corrected"], "conf": b["conf"],
                                    "raw_text": " | ".join(r["raw"])})
        zones.append(z)
    results.sort(key=lambda o: (not o["valid"], -o["conf"]))
    return zones, results


def _iou(a, b):
    """Intersection sur union de deux boîtes {x, y, w, h}."""
    x1, y1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def run_detect_ensemble(models, image_path, conf=0.15, iou_thr=0.5):
    """Inférence de PLUSIEURS modèles, boîtes fusionnées et dédupliquées.

    `models` : liste de (model_id, path). Les modèles disponibles sont
    complémentaires et non hiérarchisés (ADR-14) — leur union détecte
    nettement plus que le meilleur d'entre eux. Deux boîtes qui se recouvrent
    (IoU > iou_thr) sont considérées comme la même zone : on garde celle du
    meilleur score, pour ne pas lancer deux OCR sur le même code.

    Retourne le même contrat que run_detect(), avec en plus `found_by` sur
    chaque boîte (quel modèle l'a trouvée) et l'image annotée du modèle
    ayant produit la boîte de meilleur score.
    """
    import cv2

    merged, best_annot, best_score, total_ms = [], None, -1.0, 0
    for entry in models:
        model_id, path = entry[0], entry[1]
        size = entry[2] if len(entry) > 2 else 640
        try:
            r = run_detect(path, image_path, conf=conf, imgsz=size)
        except Exception:
            continue                      # un modèle absent ne bloque pas les autres
        total_ms += r["time_ms"]
        for b in r["boxes"]:
            merged.append({**b, "found_by": model_id})
        top = max((b["conf"] for b in r["boxes"]), default=0.0)
        if r["boxes"] and top > best_score:
            best_score, best_annot = top, r["annotated_b64"]

    # Déduplication : meilleur score d'abord, on écarte les recouvrements
    merged.sort(key=lambda b: b["conf"], reverse=True)
    kept = []
    for b in merged:
        if not any(_iou(b, k) > iou_thr for k in kept):
            kept.append(b)

    return {"time_ms": total_ms, "boxes": kept, "annotated_b64": best_annot}


# ── Vidéo — mêmes run_detect()/read_zones() que l'image, frames échantillonnées ──

VIDEO_ANALYSIS_FPS = 5          # configurable : frames/s réellement analysées
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}


def _best_crop_for(zones, bic):
    """Parmi les zones de la frame courante, celle dont l'OCR a produit `bic`
    (illustre un nouveau code du résultat consolidé avec un crop représentatif)."""
    for z in zones:
        if z.get("bic") == bic:
            return z.get("crop")
    return None


def _consolidate_codes(codes, max_diff=3):
    """Regroupe les codes proches (même conteneur physique, lectures OCR
    légèrement différentes d'une frame à l'autre à cause du flou de
    mouvement — ex. MAMU6698882 / HMMU6698882). Chaque code est comparé au
    REPRÉSENTANT d'un cluster existant, jamais de chaînage proche-en-proche
    (sinon deux conteneurs réellement différents finiraient fusionnés sur une
    vidéo longue). "proche" = même longueur ET <= max_diff caractères
    différents à position égale. Représentant = le meilleur
    (authentique > nombre de votes > confiance).

    `codes` : liste de {"bic","valid","corrected","conf","count","crop","first_time"}.
    Retourne les clusters (même forme + "candidates"/"variants"), triés
    authentiques d'abord puis par nombre de votes.
    """
    def _rank(c):
        return (c["valid"], c["count"], c["conf"])

    clusters = []
    for c in sorted(codes, key=lambda c: -c["count"]):
        placed = False
        for cl in clusters:
            rep_bic = cl["rep"]["bic"]
            if len(rep_bic) == len(c["bic"]):
                diff = sum(1 for a, b in zip(rep_bic, c["bic"]) if a != b)
                if diff <= max_diff:
                    cl["members"].append(c)
                    if _rank(c) > _rank(cl["rep"]):
                        cl["rep"] = c
                    placed = True
                    break
        if not placed:
            clusters.append({"rep": c, "members": [c]})

    out = []
    for cl in clusters:
        rep = dict(cl["rep"])
        rep["candidates"] = sorted(cl["members"], key=lambda c: -c["count"])
        rep["variants"] = [m for m in rep["candidates"] if m["bic"] != rep["bic"]]
        out.append(rep)
    out.sort(key=lambda c: (not c["valid"], -c["count"]))
    return out


def stream_video_detection(video_path, model_path, imgsz, read_fn,
                           conf=0.15, analysis_fps=VIDEO_ANALYSIS_FPS,
                           want_crops=True):
    """Générateur — traite une vidéo avec le MÊME pipeline que l'image
    (run_detect + read_zones, aucune logique dupliquée), en n'analysant
    qu'`analysis_fps` frames/s quel que soit le FPS d'origine.

    yield des dicts d'événements (l'appelant les sérialise, une ligne JSON
    par événement — NDJSON) :
      {"type": "meta", ...}      une fois, avant traitement
      {"type": "progress", ...}  une fois par frame analysée
      {"type": "done", ...}      une fois, à la fin
      {"type": "error", ...}     si la vidéo est illisible

    `read_fn` est injecté par l'appelant (moteur OCR choisi, cf. read_zones).
    Générateur pur, sans état Flask : réutilisable tel quel par un
    enregistrement RTSP (même fichier vidéo en entrée qu'un upload manuel).
    """
    import time

    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        yield {"type": "error",
               "error": "vidéo illisible (codec non supporté ou fichier corrompu)"}
        return

    orig_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    step = max(1, round(orig_fps / analysis_fps))
    to_analyze = (total_frames // step) if total_frames else 0

    yield {"type": "meta", "orig_fps": round(orig_fps, 1), "analysis_fps": analysis_fps,
           "total_frames": total_frames, "to_analyze": to_analyze,
           "width": width, "height": height,
           "duration": round(total_frames / orig_fps, 1) if orig_fps else 0}

    agg = {}   # bic -> {bic, valid, corrected, conf, count, crop, first_time}
    idx = 0
    analyzed = 0
    t0 = time.perf_counter()

    try:
        while True:
            grabbed = cap.grab()              # avance sans décoder — frames sautées gratuites
            if not grabbed:
                break
            idx += 1
            if idx % step != 0:
                continue
            ok, frame = cap.retrieve()        # décode SEULEMENT la frame retenue
            if not ok:
                continue

            analyzed += 1
            det = run_detect(model_path, frame, conf=conf, imgsz=imgsz, annotate=False)
            zones, results = read_zones(frame, det["boxes"], read_fn, do_ocr=True,
                                        want_crops=want_crops)

            t_sec = round(idx / orig_fps, 2) if orig_fps else 0.0
            for r in results:
                bic = r["bic"]
                entry = agg.get(bic)
                if entry is None:
                    agg[bic] = entry = {"bic": bic, "valid": r["valid"],
                                        "corrected": r["corrected"], "conf": r["conf"],
                                        "count": 0, "crop": _best_crop_for(zones, bic),
                                        "first_time": t_sec}
                entry["count"] += 1
                # meilleure occurrence : authentique gagne, sinon meilleure confiance
                if (r["valid"] and not entry["valid"]) or \
                   (r["valid"] == entry["valid"] and r["conf"] > entry["conf"]):
                    entry["valid"], entry["conf"] = r["valid"], r["conf"]
                    entry["corrected"] = r["corrected"]
                    crop = _best_crop_for(zones, bic)
                    if crop:
                        entry["crop"] = crop

            elapsed = time.perf_counter() - t0
            proc_fps = round(analyzed / elapsed, 1) if elapsed > 0 else 0.0
            yield {"type": "progress", "frame": idx, "analyzed": analyzed,
                   "to_analyze": to_analyze or analyzed,
                   "pct": round(analyzed / to_analyze * 100) if to_analyze else 0,
                   "proc_fps": proc_fps, "codes": len(agg)}
    finally:
        cap.release()                          # libère le fichier dans tous les cas

    elapsed_total = round(time.perf_counter() - t0, 1)
    codes = _consolidate_codes(list(agg.values()))
    yield {"type": "done", "analyzed": analyzed, "elapsed": elapsed_total, "codes": codes}
