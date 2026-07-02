"""
predict.py — Prédiction sur nouvelles images avec le dernier modèle
---------------------------------------------------------------------
Charge best_vN.pt (dernier par défaut, via models/metadata.json) et
détecte les objets dans une ou plusieurs images. Sauvegarde les images
annotées dans reports/predict/.

Usage :
  python predict.py image.jpg
  python predict.py img1.jpg img2.jpg img3.jpg
  python predict.py image.jpg --version v1
  python predict.py image.jpg --conf 0.5
"""

import os
import json
import argparse
import cv2
import numpy as np

from ultralytics import YOLO

DEFAULT_MODELS_DIR  = os.path.join(os.path.dirname(__file__), "..", "models")
DEFAULT_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")

COLORS = [
    (231, 76,  60),   # rouge
    (52,  152, 219),  # bleu
    (46,  204, 113),  # vert
    (241, 196, 15),   # jaune
    (155, 89,  182),  # violet
    (26,  188, 156),  # turquoise
    (230, 126, 34),   # orange
    (52,  73,  94),   # gris foncé
    (233, 30,  99),   # rose
    (0,   188, 212),  # cyan
    (139, 195, 74),   # vert clair
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: str, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def _latest_version(models_dir: str) -> str | None:
    metadata = _load_json(os.path.join(models_dir, "metadata.json"), {})
    if not metadata:
        return None
    return sorted(metadata.keys())[-1]


# ── Public API ────────────────────────────────────────────────────────────────

def predict(
    image_paths,
    models_dir: str = DEFAULT_MODELS_DIR,
    reports_dir: str = DEFAULT_REPORTS_DIR,
    version: str = None,
    conf: float = 0.25,
) -> list[dict]:
    """
    Prédit les objets dans une ou plusieurs images avec le dernier modèle
    (ou une version explicite). Sauvegarde les images annotées dans
    reports/predict/. Retourne [{version, image, detections, output_path}].
    """
    if isinstance(image_paths, str):
        image_paths = [image_paths]

    if version is None:
        version = _latest_version(models_dir)
        if version is None:
            raise ValueError("Aucun modèle trouvé dans models/. Lancez d'abord train.py.")

    model_path = os.path.join(models_dir, f"best_{version}.pt")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Modèle introuvable : {model_path}")

    save_dir = os.path.join(reports_dir, "predict")
    os.makedirs(save_dir, exist_ok=True)

    model = YOLO(model_path)
    all_results = []

    for img_path in image_paths:
        yolo_results = model(img_path, conf=conf, verbose=False)
        detections = []

        for result in yolo_results:
            for box in result.boxes:
                label = result.names[int(box.cls[0])]
                confidence = round(float(box.conf[0]), 4)
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                detections.append({
                    "label": label,
                    "confidence": confidence,
                    "bbox": [x1, y1, x2, y2],
                })

        output_path = _draw_and_save(img_path, detections, save_dir)
        all_results.append({
            "version": version,
            "image": img_path,
            "detections": detections,
            "output_path": output_path,
        })

    return all_results


def _draw_and_save(img_path: str, detections: list, save_dir: str) -> str:
    img = cv2.imread(img_path)
    if img is None:
        return None

    font_scale = max(0.4, img.shape[1] / 1200)
    thickness  = max(1, img.shape[1] // 400)

    for i, det in enumerate(detections):
        color = COLORS[i % len(COLORS)]
        x1, y1, x2, y2 = det["bbox"]
        label = f"{det['label']} {det['confidence']:.0%}"

        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        cv2.rectangle(img, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(img, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness)

    basename = os.path.splitext(os.path.basename(img_path))[0]
    output_path = os.path.join(save_dir, f"{basename}_pred.jpg")
    cv2.imwrite(output_path, img)
    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prediction YOLO")
    parser.add_argument("images", nargs="+")
    parser.add_argument("--models",  default=DEFAULT_MODELS_DIR)
    parser.add_argument("--reports", default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--version", default=None)
    parser.add_argument("--conf",    type=float, default=0.25)
    args = parser.parse_args()

    results = predict(args.images, args.models, args.reports, args.version, args.conf)

    for r in results:
        print(f"\n[{r['image']}] (modele {r['version']})")
        if not r["detections"]:
            print("  Aucun objet detecte.")
            print("  ==> RIEN DETECTE")
        else:
            for det in r["detections"]:
                print(f"  {det['label']:<15} conf={det['confidence']:.2f}  bbox={det['bbox']}")
            best = max(r["detections"], key=lambda d: d["confidence"])
            n = len(r["detections"])
            objets = f" ({n} objets detectes)" if n > 1 else ""
            print(f"  ==> C'EST UN {best['label'].upper()} (confiance {best['confidence']:.0%}){objets}")
        if r["output_path"]:
            print(f"  -> Sauvegarde : {r['output_path']}")
