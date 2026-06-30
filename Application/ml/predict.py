"""
predict.py — Prédiction sur nouvelles images avec le modèle final
-----------------------------------------------------------------
Charge best.pt (issu de train_final.py) et détecte les objets dans
une ou plusieurs images. Sauvegarde les images annotées avec bounding
boxes et libellés colorés.

Usage :
  python predict.py image.jpg
  python predict.py img1.jpg img2.jpg img3.jpg
  python predict.py image.jpg --model runs/final/train/weights/best.pt

Etape 8 — dernière étape du pipeline ML.
"""

import os
import cv2
import numpy as np

from ultralytics import YOLO

DEFAULT_MODEL = os.path.join(
    os.path.dirname(__file__), "runs", "final", "train", "weights", "best.pt"
)

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


def predict(
    image_paths,
    model_path: str = DEFAULT_MODEL,
    conf: float = 0.25,
    save_dir: str = None,
) -> list[dict]:
    """
    Prédit les objets dans une ou plusieurs images.
    Retourne [{image, detections:[{label,confidence,bbox}], output_path}].
    """
    if isinstance(image_paths, str):
        image_paths = [image_paths]

    if save_dir is None:
        save_dir = os.path.join(os.path.dirname(__file__), "runs", "predict")
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
            "image": img_path,
            "detections": detections,
            "output_path": output_path,
        })

    return all_results


def _draw_and_save(img_path: str, detections: list[dict], save_dir: str) -> str:
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


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if not args:
        print("Usage: python predict.py image1.jpg [image2.jpg ...]")
        sys.exit(1)

    model_path = DEFAULT_MODEL
    images = []
    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model_path = args[i + 1]
            i += 2
        else:
            images.append(args[i])
            i += 1

    print(f"Modele : {model_path}")
    results = predict(images, model_path)

    for r in results:
        print(f"\n[{r['image']}]")
        if not r["detections"]:
            print("  Aucun objet detecte.")
        for det in r["detections"]:
            print(f"  {det['label']:<15} conf={det['confidence']:.2f}  bbox={det['bbox']}")
        if r["output_path"]:
            print(f"  -> Sauvegarde : {r['output_path']}")
