"""
trainer.py — Entraînement YOLO pour l'API web
----------------------------------------------
Fournit deux modes d'entraînement déclenchables depuis l'interface web :
  - Mode "dataset" : utilise un dataset annoté existant (data.yaml)
  - Mode "raw"     : prend des images brutes, génère les annotations
                     automatiquement (bbox = pleine image)

Utilisé par : backend/app.py (route POST /train)
Pour le pipeline ML complet, voir : ml/train_baseline.py
"""

import os
import shutil

from ultralytics import YOLO

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def auto_annotate(images_dir: str, labels_dir: str) -> int:
    """Crée un fichier label YOLO (bbox pleine image) pour chaque image."""
    os.makedirs(labels_dir, exist_ok=True)
    count = 0
    for fname in os.listdir(images_dir):
        stem, ext = os.path.splitext(fname)
        if ext.lower() not in IMAGE_EXTENSIONS:
            continue
        label_path = os.path.join(labels_dir, stem + ".txt")
        with open(label_path, "w") as f:
            f.write("0 0.5 0.5 1.0 1.0")
        count += 1
    return count


def prepare_raw_dataset(images_dir: str, class_name: str, output_dir: str) -> str:
    """Construit la structure YOLO et génère data.yaml. Retourne le chemin du yaml."""
    train_images = os.path.join(output_dir, "train", "images")
    train_labels = os.path.join(output_dir, "train", "labels")
    os.makedirs(train_images, exist_ok=True)
    os.makedirs(train_labels, exist_ok=True)

    for fname in os.listdir(images_dir):
        _, ext = os.path.splitext(fname)
        if ext.lower() in IMAGE_EXTENSIONS:
            shutil.copy2(os.path.join(images_dir, fname), os.path.join(train_images, fname))

    auto_annotate(train_images, train_labels)

    yaml_path = os.path.join(output_dir, "data.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"train: {os.path.join(output_dir, 'train', 'images')}\n")
        f.write(f"val: {os.path.join(output_dir, 'train', 'images')}\n")
        f.write(f"nc: 1\n")
        f.write(f"names: ['{class_name}']\n")
    return yaml_path


def train(
    data_yaml: str,
    base_model: str,
    epochs: int = 50,
    project_dir: str = "runs/train",
) -> dict:
    """Fine-tune YOLO sur le dataset. Retourne {model_path, mAP50, precision, recall}."""
    model = YOLO(base_model)
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        project=project_dir,
        device=0,
        exist_ok=True,
    )
    metrics = results.results_dict
    best_pt = os.path.join(results.save_dir, "best.pt")
    return {
        "model_path": best_pt,
        "mAP50": metrics.get("metrics/mAP50(B)", 0.0),
        "precision": metrics.get("metrics/precision(B)", 0.0),
        "recall": metrics.get("metrics/recall(B)", 0.0),
    }
