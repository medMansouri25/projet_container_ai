"""Test du modèle fine-tuné best.pt sur toutes les images conteneurs."""
import os
from ultralytics import YOLO

BASE    = os.path.dirname(os.path.abspath(__file__))
MODEL   = os.path.join(BASE, "..", "..", "runs", "train_poc_conteneur", "weights", "best.pt")
IMG_DIR = os.path.join(BASE, "..", "images")
IMAGES  = ["conteneur_maersk.jpg", "image1.jpg", "image3.jpg", "image4.jpg",
           "image5.jpg", "image6.jpg", "image7.jpg", "image8.jpg"]

model = YOLO(MODEL)
detected = 0

for fname in IMAGES:
    path = os.path.join(IMG_DIR, fname)
    if not os.path.exists(path):
        print(f"  [SKIP] {fname}")
        continue
    results = model(path, verbose=False)
    found = []
    for r in results:
        for box in r.boxes:
            found.append(f"{r.names[int(box.cls[0])]} {float(box.conf[0]):.2f}")
    if found:
        detected += 1
        print(f"  [OK]  {fname}: {found}")
    else:
        print(f"  [--]  {fname}: rien détecté")

print(f"\nScore : {detected}/8 images avec conteneur détecté")
