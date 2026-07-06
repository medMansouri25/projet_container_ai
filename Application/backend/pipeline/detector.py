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
           "crop": None, "model_path": model_path, "annotated_path": None}

    best_box = None
    for result in model(image_path, conf=conf, verbose=False):
        for box in result.boxes:
            label = result.names[int(box.cls[0])]
            if label != "Conteneur":
                continue
            c = float(box.conf[0])
            if c > out["confidence"]:
                out["confidence"] = round(c, 4)
                best_box = [int(v) for v in box.xyxy[0].tolist()]

    if best_box:
        x1, y1, x2, y2 = best_box
        out["found"] = True
        out["bbox"] = best_box
        out["vertical"] = (y2 - y1) > (x2 - x1)
        out["crop"] = img[max(0, y1):y2, max(0, x1):x2]

        if annotated_dir:
            os.makedirs(annotated_dir, exist_ok=True)
            annotated = img.copy()
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (52, 152, 219), 3)
            cv2.putText(annotated, f"Conteneur {out['confidence']:.0%}",
                        (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (52, 152, 219), 2)
            name = os.path.splitext(os.path.basename(image_path))[0] + "_annotated.jpg"
            out["annotated_path"] = os.path.join(annotated_dir, name)
            cv2.imwrite(out["annotated_path"], annotated)

    return out
