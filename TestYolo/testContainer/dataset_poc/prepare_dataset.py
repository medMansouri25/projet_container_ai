"""
prepare_dataset.py
Génère le dataset POC pour fine-tuner YOLO11m sur la classe "conteneur".

Stratégie : on utilise les détections YOLO11m existantes (truck/refrigerator)
comme pseudo-annotations et on les relabellise "conteneur" (class_id=0).
Images où YOLO ne détecte rien → ignorées pour ce POC.

Sortie :
    dataset_poc/
    ├── data.yaml
    ├── images/train/  + images/val/
    └── labels/train/  + labels/val/   (format YOLO : cx cy w h normalisé)
"""
import os
import shutil
import cv2
from ultralytics import YOLO

BASE     = os.path.dirname(os.path.abspath(__file__))
IMG_DIR  = os.path.join(BASE, "..", "images")
MODEL_PT = os.path.join(BASE, "..", "..", "yolo11m.pt")

TRAIN_IMAGES = ["image1.jpg", "image3.jpg", "image4.jpg", "image7.jpg"]
VAL_IMAGES   = ["conteneur_maersk.jpg"]


def bbox_to_yolo(x1: int, y1: int, x2: int, y2: int, img_w: int, img_h: int) -> str:
    """Convertit xyxy → cx cy w h normalisé (format YOLO txt, class_id=0)."""
    cx = ((x1 + x2) / 2) / img_w
    cy = ((y1 + y2) / 2) / img_h
    w  = (x2 - x1) / img_w
    h  = (y2 - y1) / img_h
    return f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def best_detection(image_path: str, model: YOLO) -> dict | None:
    """
    Retourne la détection avec la plus haute confiance sur l'image.
    Quelle que soit la classe COCO — on relabellisera tout en "conteneur".
    """
    img = cv2.imread(image_path)
    if img is None:
        return None
    h, w = img.shape[:2]

    best = None
    for result in model(image_path, verbose=False):
        for box in result.boxes:
            conf = float(box.conf[0])
            if best is None or conf > best["conf"]:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                best = {
                    "conf":  conf,
                    "class": result.names[int(box.cls[0])],
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "img_w": w, "img_h": h,
                }
    return best


def process_split(filenames: list, split: str, model: YOLO) -> int:
    img_out = os.path.join(BASE, "images", split)
    lbl_out = os.path.join(BASE, "labels", split)
    count = 0

    for fname in filenames:
        src = os.path.join(IMG_DIR, fname)
        if not os.path.exists(src):
            print(f"  [SKIP] {fname} introuvable")
            continue

        print(f"  {fname}")
        det = best_detection(src, model)

        if det is None:
            print(f"    → aucune détection, image ignorée")
            continue

        print(f"    → {det['class']} conf={det['conf']:.2f}  "
              f"bbox=[{det['x1']},{det['y1']},{det['x2']},{det['y2']}]  "
              f"relabellisé → conteneur")

        shutil.copy2(src, os.path.join(img_out, fname))

        stem = os.path.splitext(fname)[0]
        line = bbox_to_yolo(det["x1"], det["y1"], det["x2"], det["y2"],
                            det["img_w"], det["img_h"])
        with open(os.path.join(lbl_out, f"{stem}.txt"), "w") as f:
            f.write(line + "\n")

        count += 1

    return count


def write_data_yaml(n_train: int, n_val: int) -> None:
    content = f"""\
# Dataset POC conteneurs — pseudo-labels depuis YOLO11m (truck/refrigerator → conteneur)
# {n_train} images train / {n_val} images val

path: {BASE.replace(os.sep, "/")}
train: images/train
val:   images/val

nc: 1
names:
  0: conteneur
"""
    yaml_path = os.path.join(BASE, "data.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n  data.yaml → {yaml_path}")


def main():
    model = YOLO(MODEL_PT)

    print("\n── TRAIN ──────────────────────────────")
    n_train = process_split(TRAIN_IMAGES, "train", model)

    print("\n── VAL ────────────────────────────────")
    n_val = process_split(VAL_IMAGES, "val", model)

    write_data_yaml(n_train, n_val)
    print(f"\nDataset prêt : {n_train} train / {n_val} val")


if __name__ == "__main__":
    main()
