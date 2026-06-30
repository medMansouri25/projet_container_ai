"""
analyze_dataset.py — Analyse et rapport du dataset YOLO
---------------------------------------------------------
Génère un rapport complet sur l'état du dataset :
  - Nombre d'images et de labels par split (train/valid/test)
  - Orphelins : images sans label, labels sans image
  - Répartition des classes et nombre de bounding boxes par classe
  - Tailles d'images (min/max largeur et hauteur)
  - Validation des indices de classe (doit être dans 0..nc-1)

Usage : python analyze_dataset.py [chemin/vers/data/]
Etape 0 du pipeline ML — à exécuter avant et après le nettoyage.
"""

import os
import re
from PIL import Image

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def analyze_dataset(data_dir: str) -> dict:
    """
    Analyse un dataset YOLO et retourne un rapport complet :
    - counts images/labels par split
    - orphelins (images sans label, labels sans image)
    - bbox par classe
    - tailles d'images (min/max)
    - vérification indices de classe 0..nc-1
    """
    # Lecture data.yaml
    yaml_path = os.path.join(data_dir, "data.yaml")
    nc, names = _parse_yaml(yaml_path)

    splits_report = {}
    class_bbox = {i: 0 for i in range(nc)}
    invalid_indices = []
    widths, heights = [], []

    for split in ("train", "valid", "test"):
        img_dir = os.path.join(data_dir, split, "images")
        lbl_dir = os.path.join(data_dir, split, "labels")

        imgs = _list_files(img_dir, IMAGE_EXTS)
        lbls = _list_files(lbl_dir, {".txt"})

        img_stems = {os.path.splitext(f)[0] for f in imgs}
        lbl_stems = {os.path.splitext(f)[0] for f in lbls}

        no_label = len(img_stems - lbl_stems)
        no_image = len(lbl_stems - img_stems)

        # Tailles d'images
        for fname in imgs:
            try:
                w, h = Image.open(os.path.join(img_dir, fname)).size
                widths.append(w)
                heights.append(h)
            except Exception:
                pass

        # Comptage bbox et vérification indices
        for fname in lbls:
            path = os.path.join(lbl_dir, fname)
            for line in open(path).read().strip().splitlines():
                parts = line.split()
                if not parts:
                    continue
                idx = int(parts[0])
                if idx < nc:
                    class_bbox[idx] = class_bbox.get(idx, 0) + 1
                else:
                    invalid_indices.append({
                        "file": os.path.join(split, "labels", fname),
                        "index": idx,
                    })

        splits_report[split] = {
            "images": len(imgs),
            "labels": len(lbls),
            "no_label": no_label,
            "no_image": no_image,
        }

    classes = {
        i: {"name": names[i] if i < len(names) else str(i), "bbox_count": class_bbox.get(i, 0)}
        for i in range(nc)
    }

    image_sizes = {
        "min_w": min(widths) if widths else 0,
        "max_w": max(widths) if widths else 0,
        "min_h": min(heights) if heights else 0,
        "max_h": max(heights) if heights else 0,
        "total": len(widths),
    }

    return {
        "splits": splits_report,
        "classes": classes,
        "image_sizes": image_sizes,
        "invalid_indices": invalid_indices,
        "nc": nc,
        "nc_valid": len(invalid_indices) == 0,
    }


def _parse_yaml(yaml_path: str):
    if not os.path.exists(yaml_path):
        return 0, []
    content = open(yaml_path).read()
    nc_match = re.search(r"nc:\s*(\d+)", content)
    nc = int(nc_match.group(1)) if nc_match else 0
    names_match = re.search(r"names:\s*\[([^\]]+)\]", content)
    names = []
    if names_match:
        names = [x.strip().strip("'\"") for x in names_match.group(1).split(",")]
    return nc, names


def _list_files(directory: str, extensions: set) -> list:
    if not os.path.isdir(directory):
        return []
    return [f for f in os.listdir(directory)
            if os.path.splitext(f)[1].lower() in extensions]


def print_report(report: dict) -> None:
    print("\n============== ANALYSE DATASET ==============")
    for split, s in report["splits"].items():
        print(f"\n[{split.upper()}]")
        print(f"  Images        : {s['images']}")
        print(f"  Labels        : {s['labels']}")
        print(f"  Sans label    : {s['no_label']}")
        print(f"  Sans image    : {s['no_image']}")

    print(f"\n[CLASSES] ({report['nc']} classes)")
    for i, cls in report["classes"].items():
        print(f"  {i:2d}. {cls['name']:<15} {cls['bbox_count']:>6} bbox")

    s = report["image_sizes"]
    print(f"\n[TAILLES IMAGES]")
    print(f"  Total   : {s['total']} images analysees")
    print(f"  Largeur : {s['min_w']}px -> {s['max_w']}px")
    print(f"  Hauteur : {s['min_h']}px -> {s['max_h']}px")

    print(f"\n[VALIDATION NC]")
    print(f"  nc_valid : {report['nc_valid']}")
    if report["invalid_indices"]:
        print(f"  /!\\ {len(report['invalid_indices'])} indices invalides detectes")
        for inv in report["invalid_indices"][:5]:
            print(f"    - {inv['file']} : classe {inv['index']}")
    print("=============================================\n")


if __name__ == "__main__":
    import sys
    data_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "data"
    )
    report = analyze_dataset(data_dir)
    print_report(report)
