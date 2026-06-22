"""
train_yolo_poc.py
Fine-tuning YOLO11m sur le dataset POC conteneurs (4 train / 1 val).

Objectif : valider la chaîne entraînement → détection avant le vrai dataset Marsa Maroc.
Le modèle va over-fitter sur 4 images — c'est attendu et voulu pour ce POC.

Sortie : runs/train_poc_conteneur/weights/best.pt
"""
import os
from ultralytics import YOLO

BASE      = os.path.dirname(os.path.abspath(__file__))
DATA_YAML = os.path.join(BASE, "data.yaml")
MODEL_PT  = os.path.join(BASE, "..", "..", "yolo11m.pt")
PROJECT   = os.path.join(BASE, "..", "..", "runs")
RUN_NAME  = "train_poc_conteneur"


def train():
    model = YOLO(MODEL_PT)

    results = model.train(
        data      = DATA_YAML,
        epochs    = 50,
        imgsz     = 640,
        batch     = 4,
        lr0       = 0.001,
        patience  = 20,        # early stopping si pas d'amélioration
        device    = 0,         # GPU RTX 5070 Ti
        project   = PROJECT,
        name      = RUN_NAME,
        exist_ok  = True,
        verbose   = False,
    )

    best_pt = os.path.join(PROJECT, RUN_NAME, "weights", "best.pt")
    print(f"\nModèle sauvegardé : {best_pt}")
    return best_pt


if __name__ == "__main__":
    train()
