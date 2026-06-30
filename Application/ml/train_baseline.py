"""
train_baseline.py — Entraînement baseline YOLO11m
--------------------------------------------------
Fine-tune YOLO11m sur le dataset annoté (11 classes conteneurs).
Paramètres : 50 epochs, early stopping patience=10, GPU device=0.
Sauvegarde best.pt et metrics_baseline.json dans runs/baseline/.

Usage : python train_baseline.py
Etape 3 du pipeline ML (après analyze + clean).
Résultats à analyser avec evaluate.py avant de lancer tune.py.
"""

import os
import json

from ultralytics import YOLO

DEFAULT_BASE_MODEL = os.path.join(
    os.path.dirname(__file__), "..", "..", "TestYolo", "yolo11m.pt"
)
DEFAULT_DATA_YAML = os.path.join(
    os.path.dirname(__file__), "..", "data", "data.yaml"
)


def train_baseline(
    data_yaml: str = DEFAULT_DATA_YAML,
    base_model: str = DEFAULT_BASE_MODEL,
    epochs: int = 50,
    patience: int = 10,
    project_dir: str = None,
    device: int = 0,
) -> dict:
    """
    Fine-tune YOLO11m en baseline.
    Retourne {model_path, mAP50, mAP50_95, precision, recall}.
    """
    if project_dir is None:
        project_dir = os.path.join(os.path.dirname(__file__), "runs", "baseline")

    model = YOLO(base_model)
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        patience=patience,
        project=project_dir,
        name="train",
        device=device,
        exist_ok=True,
        workers=0,
    )

    best_pt = os.path.join(results.save_dir, "best.pt")
    metrics = results.results_dict

    out = {
        "model_path": best_pt,
        "mAP50":     metrics.get("metrics/mAP50(B)", 0.0),
        "mAP50_95":  metrics.get("metrics/mAP50-95(B)", 0.0),
        "precision": metrics.get("metrics/precision(B)", 0.0),
        "recall":    metrics.get("metrics/recall(B)", 0.0),
    }

    # Sauvegarde métriques JSON à côté de best.pt
    metrics_path = os.path.join(results.save_dir, "metrics_baseline.json")
    with open(metrics_path, "w") as f:
        json.dump(out, f, indent=2)

    return out


if __name__ == "__main__":
    print("Lancement entraînement baseline YOLO11m...")
    result = train_baseline()
    print(f"\n=== Resultats baseline ===")
    print(f"  Modele   : {result['model_path']}")
    print(f"  mAP50    : {result['mAP50']:.4f}")
    print(f"  mAP50-95 : {result['mAP50_95']:.4f}")
    print(f"  Precision: {result['precision']:.4f}")
    print(f"  Recall   : {result['recall']:.4f}")
