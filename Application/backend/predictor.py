"""
predictor.py — Inférence YOLO pour l'API web
---------------------------------------------
Charge un modèle fine-tuné (best.pt) et prédit les objets
présents dans une image. Retourne label, score de confiance
et bounding box pour chaque détection.

Utilisé par : backend/app.py (route POST /predict)
"""

from ultralytics import YOLO


def predict(image_path: str, model_path: str) -> list[dict]:
    """Inférence YOLO sur une image. Retourne [{label, confidence, bbox}, ...]."""
    model = YOLO(model_path)
    results = model(image_path, verbose=False)

    detections = []
    for result in results:
        for box in result.boxes:
            label = result.names[int(box.cls[0])]
            confidence = round(float(box.conf[0]), 4)
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            detections.append({
                "label": label,
                "confidence": confidence,
                "bbox": [x1, y1, x2, y2],
            })
    return detections
