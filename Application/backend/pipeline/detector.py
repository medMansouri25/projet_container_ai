"""
detector.py — Détection du conteneur (YOLO versionné)
------------------------------------------------------
Charge le dernier best_vN.pt via models/metadata.json (ou MODEL_PATH env),
détecte la classe Conteneur, détermine l'orientation (bbox plus haute que
large = texte vertical probable) et retourne le crop pour l'OCR.
"""

import os
import json

import cv2

from ultralytics import YOLO

DEFAULT_MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models")

_model_cache = {}


def _latest_model_path(models_dir: str) -> str:
    env = os.environ.get("MODEL_PATH")
    if env:
        return env
    meta_path = os.path.join(models_dir, "metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            metadata = json.load(f)
        if metadata:
            latest = sorted(metadata.keys())[-1]
            return os.path.join(models_dir, f"best_{latest}.pt")
    raise FileNotFoundError("Aucun modele trouve (metadata.json vide et MODEL_PATH absent).")


def _get_model(models_dir: str):
    path = _latest_model_path(models_dir)
    if path not in _model_cache:
        _model_cache[path] = YOLO(path)
    return _model_cache[path], path


def _get_bic_model(models_dir: str):
    """Modèle spécialiste zone BIC (models/bic/best_vN.pt ou env BIC_MODEL_PATH).
    Retourne None s'il n'existe pas encore."""
    path = os.environ.get("BIC_MODEL_PATH")
    if not path:
        bic_dir = os.path.join(models_dir, "bic")
        meta = os.path.join(bic_dir, "metadata.json")
        if os.path.exists(meta):
            with open(meta, encoding="utf-8") as f:
                metadata = json.load(f)
            if metadata:
                latest = sorted(metadata.keys())[-1]
                path = os.path.join(bic_dir, f"best_{latest}.pt")
    if not path or not os.path.exists(path):
        return None
    if path not in _model_cache:
        _model_cache[path] = YOLO(path)
    return _model_cache[path]


def detect_container(image_path: str, models_dir: str = DEFAULT_MODELS_DIR,
                     conf: float = 0.25, annotated_dir: str = None) -> dict:
    """
    Détecte le conteneur le plus confiant dans l'image.
    Retourne {"found", "bbox", "confidence", "vertical", "crop", "model_path",
              "annotated_path"} — crop est un numpy BGR (None si rien trouvé).
    """
    model, model_path = _get_model(models_dir)
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Image illisible : {image_path}")

    out = {"found": False, "bbox": None, "confidence": 0.0, "vertical": False,
           "crop": None, "bic_zone": None, "model_path": model_path,
           "annotated_path": None}

    best_box = None
    bic_candidates = []   # [(conf, bbox)] toutes sources confondues
    for result in model(image_path, conf=conf, verbose=False):
        for box in result.boxes:
            label = result.names[int(box.cls[0])]
            c = float(box.conf[0])
            if label == "Conteneur":
                if c > out["confidence"]:
                    out["confidence"] = round(c, 4)
                    best_box = [int(v) for v in box.xyxy[0].tolist()]
            elif label == "NumeroBIC":
                bic_candidates.append((c, [int(v) for v in box.xyxy[0].tolist()]))

    # Modele specialiste zone BIC (entraine uniquement sur datasetEnt).
    # Seuil bas : une seule classe tres precise, mieux vaut attraper la zone.
    bic_model = _get_bic_model(models_dir)
    if bic_model is not None:
        for result in bic_model(image_path, conf=0.15, verbose=False):
            for box in result.boxes:
                c = float(box.conf[0])
                bic_candidates.append((c, [int(v) for v in box.xyxy[0].tolist()]))

    # La zone retenue doit etre DANS le conteneur detecte (sinon on lirait
    # le marquage d'un conteneur voisin en arriere-plan)
    def _center_inside(zone):
        if best_box is None:
            return True
        cx = (zone[0] + zone[2]) / 2
        cy = (zone[1] + zone[3]) / 2
        return (best_box[0] <= cx <= best_box[2]
                and best_box[1] <= cy <= best_box[3])

    best_bic = None
    best_bic_conf = 0.0
    for c, bbox in bic_candidates:
        if c > best_bic_conf and _center_inside(bbox):
            best_bic_conf = c
            best_bic = bbox

    if best_box:
        x1, y1, x2, y2 = best_box
        out["found"] = True
        out["bbox"] = best_box
        out["vertical"] = (y2 - y1) > (x2 - x1)
        out["crop"] = img[max(0, y1):y2, max(0, x1):x2]

    if best_bic:
        bx1, by1, bx2, by2 = best_bic
        # Marge autour de la zone : le chiffre de controle (encadre) suit le
        # numero de serie dans le sens de lecture et se fait couper sinon.
        # 40% dans le sens de lecture, 15% dans l'autre.
        H, W = img.shape[:2]
        zone_vertical = (by2 - by1) > (bx2 - bx1)
        if zone_vertical:
            mw = int(0.15 * (bx2 - bx1))
            mh = int(0.40 * (by2 - by1))
        else:
            mw = int(0.40 * (bx2 - bx1))
            mh = int(0.15 * (by2 - by1))
        out["bic_zone"] = {
            "bbox": best_bic,
            "confidence": round(best_bic_conf, 4),
            "vertical": (by2 - by1) > (bx2 - bx1),
            "crop": img[max(0, by1 - mh):min(H, by2 + mh),
                        max(0, bx1 - mw):min(W, bx2 + mw)],
        }

    if (best_box or best_bic) and annotated_dir:
        os.makedirs(annotated_dir, exist_ok=True)
        annotated = img.copy()
        if best_box:
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (52, 152, 219), 3)
            cv2.putText(annotated, f"Conteneur {out['confidence']:.0%}",
                        (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (52, 152, 219), 2)
        if best_bic:
            bx1, by1, bx2, by2 = best_bic
            cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (60, 204, 46), 3)
            cv2.putText(annotated, f"BIC {best_bic_conf:.0%}",
                        (bx1, max(20, by1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (60, 204, 46), 2)
        name = os.path.splitext(os.path.basename(image_path))[0] + "_annotated.jpg"
        out["annotated_path"] = os.path.join(annotated_dir, name)
        cv2.imwrite(out["annotated_path"], annotated)

    return out
