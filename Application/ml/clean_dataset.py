"""
clean_dataset.py — Nettoyage du dataset YOLO
---------------------------------------------
Supprime les fichiers orphelins (images sans label, labels sans image)
dans les splits train et valid, et corrige le champ `nc` dans data.yaml
pour qu'il corresponde au nombre réel de classes dans `names`.

Usage : python clean_dataset.py [chemin/vers/data/]
Etape 1 du pipeline ML (après analyze_dataset.py).
"""

import os
import re

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def clean_dataset(data_dir: str) -> dict:
    """
    Nettoie un dataset YOLO :
    - Supprime images sans label (train + valid)
    - Supprime labels sans image (train)
    - Corrige nc dans data.yaml
    Retourne un rapport {removed_images, removed_labels, nc_fixed}.
    """
    removed_images = 0
    removed_labels = 0
    nc_fixed = False

    for split in ("train", "valid"):
        img_dir = os.path.join(data_dir, split, "images")
        lbl_dir = os.path.join(data_dir, split, "labels")
        if not os.path.isdir(img_dir):
            continue

        img_stems = {os.path.splitext(f)[0] for f in os.listdir(img_dir)
                     if os.path.splitext(f)[1].lower() in IMAGE_EXTS}
        lbl_stems = {os.path.splitext(f)[0] for f in os.listdir(lbl_dir)
                     if f.endswith(".txt")} if os.path.isdir(lbl_dir) else set()

        # Images sans label
        for fname in list(os.listdir(img_dir)):
            stem, ext = os.path.splitext(fname)
            if ext.lower() in IMAGE_EXTS and stem not in lbl_stems:
                os.remove(os.path.join(img_dir, fname))
                removed_images += 1

        # Labels sans image (train uniquement)
        if split == "train" and os.path.isdir(lbl_dir):
            for fname in list(os.listdir(lbl_dir)):
                if fname.endswith(".txt") and os.path.splitext(fname)[0] not in img_stems:
                    os.remove(os.path.join(lbl_dir, fname))
                    removed_labels += 1

    # Correction data.yaml
    yaml_path = os.path.join(data_dir, "data.yaml")
    if os.path.exists(yaml_path):
        content = open(yaml_path).read()
        names = re.findall(r"names:\s*\[([^\]]+)\]", content)
        if names:
            n = len([x.strip().strip("'\"") for x in names[0].split(",")])
            new_content = re.sub(r"nc:\s*\d+", f"nc: {n}", content)
            if new_content != content:
                open(yaml_path, "w").write(new_content)
                nc_fixed = True

    return {
        "removed_images": removed_images,
        "removed_labels": removed_labels,
        "nc_fixed": nc_fixed,
    }


if __name__ == "__main__":
    import sys
    data_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "data"
    )
    report = clean_dataset(data_dir)
    print(f"Images supprimées : {report['removed_images']}")
    print(f"Labels supprimés  : {report['removed_labels']}")
    print(f"nc corrigé        : {report['nc_fixed']}")
