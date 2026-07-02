"""
dataset.py — Gestionnaire dataset dataset-centric
--------------------------------------------------
Gère les classes, l'import d'images, l'annotation automatique,
la validation et le versioning du dataset.

Usage :
  python dataset.py add-class Conteneur
  python dataset.py import images/ Conteneur --annotation auto
  python dataset.py import images/ Conteneur --annotation sam2
  python dataset.py import images/ Conteneur --annotation manual
  python dataset.py validate
  python dataset.py version
"""

import os
import sys
import json
import shutil
import random
import argparse

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _load_json(path: str, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def _save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _classes_path(dataset_dir: str) -> str:
    return os.path.join(dataset_dir, "classes.json")


def _manifest_path(dataset_dir: str) -> str:
    return os.path.join(dataset_dir, "manifest.json")


# ── Public API ────────────────────────────────────────────────────────────────

def add_class(dataset_dir: str, class_name: str) -> dict:
    """
    Ajoute une classe dans classes.json (idempotent).
    Retourne {"classes": {...}, "index": N}.
    """
    classes = _load_json(_classes_path(dataset_dir), {})

    for idx, name in classes.items():
        if name == class_name:
            return {"classes": classes, "index": int(idx)}

    next_idx = str(len(classes))
    classes[next_idx] = class_name
    _save_json(_classes_path(dataset_dir), classes)
    return {"classes": classes, "index": int(next_idx)}


def import_images(
    dataset_dir: str,
    images_dir: str,
    class_name: str,
    annotation: str = "auto",
) -> dict:
    """
    Importe des images dans raw/<Classe>/ et les enregistre dans manifest.json.
    annotation : "auto" (pleine image), "sam2" (SAM2 point prompt), "manual" (pas de label).
    Retourne {"imported": N, "annotated": N, "failed": N}.
    """
    classes = _load_json(_classes_path(dataset_dir), {})
    class_id = next((int(i) for i, n in classes.items() if n == class_name), None)
    if class_id is None:
        result = add_class(dataset_dir, class_name)
        class_id = result["index"]

    raw_dir = os.path.join(dataset_dir, "raw", class_name)
    os.makedirs(raw_dir, exist_ok=True)

    manifest = _load_json(_manifest_path(dataset_dir), [])
    existing = {e["file"] for e in manifest}

    imported = annotated = failed = 0

    for img_file in sorted(
        f for f in os.listdir(images_dir)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    ):
        dst = _unique_path(os.path.join(raw_dir, img_file))
        shutil.copy2(os.path.join(images_dir, img_file), dst)
        rel = os.path.relpath(dst, dataset_dir).replace("\\", "/")

        if rel in existing:
            continue

        if annotation == "auto":
            _write_full_image_label(dst, class_id)
            annotated += 1
        elif annotation == "sam2":
            ok = _annotate_sam2(dst, class_id)
            if ok:
                annotated += 1
            else:
                failed += 1
        # "manual" : rien

        manifest.append({
            "file": rel,
            "class": class_name,
            "class_id": class_id,
            "validated": False,
            "split": None,
        })
        imported += 1

    _save_json(_manifest_path(dataset_dir), manifest)
    return {"imported": imported, "annotated": annotated, "failed": failed}


def validate(dataset_dir: str) -> dict:
    """
    Marque toutes les images non-validées comme validated=True.
    Retourne {"validated": N}.
    """
    manifest = _load_json(_manifest_path(dataset_dir), [])
    count = sum(1 for e in manifest if not e["validated"])
    for e in manifest:
        e["validated"] = True
    _save_json(_manifest_path(dataset_dir), manifest)
    return {"validated": count}


def create_version(
    dataset_dir: str,
    train_ratio: float = 0.70,
    valid_ratio: float = 0.20,
    test_ratio: float = 0.10,
    seed: int = 42,
) -> str:
    """
    Crée une nouvelle version du dataset depuis les images validées.
    Génère versions/vN/, met à jour current/ et data.yaml.
    Retourne le nom de version ("v1", "v2"...).
    """
    manifest = _load_json(_manifest_path(dataset_dir), [])
    validated = [e for e in manifest if e["validated"]]
    if not validated:
        raise ValueError("Aucune image validée dans le manifest.")

    versions_dir = os.path.join(dataset_dir, "versions")
    os.makedirs(versions_dir, exist_ok=True)
    existing = [d for d in os.listdir(versions_dir) if d.startswith("v")]
    version_name = f"v{len(existing) + 1}"
    version_dir = os.path.join(versions_dir, version_name)

    random.seed(seed)
    random.shuffle(validated)
    n_train = int(len(validated) * train_ratio)
    n_valid = int(len(validated) * valid_ratio)

    splits = {
        "train": validated[:n_train],
        "valid": validated[n_train:n_train + n_valid],
        "test":  validated[n_train + n_valid:],
    }

    for split_name, entries in splits.items():
        img_out = os.path.join(version_dir, split_name, "images")
        lbl_out = os.path.join(version_dir, split_name, "labels")
        os.makedirs(img_out, exist_ok=True)
        os.makedirs(lbl_out, exist_ok=True)

        for entry in entries:
            src_img = os.path.join(dataset_dir, entry["file"])
            fname = os.path.basename(src_img)
            shutil.copy2(src_img, os.path.join(img_out, fname))
            src_lbl = os.path.splitext(src_img)[0] + ".txt"
            if os.path.exists(src_lbl):
                shutil.copy2(src_lbl, os.path.join(lbl_out, os.path.splitext(fname)[0] + ".txt"))
            entry["split"] = split_name

    _save_json(_manifest_path(dataset_dir), manifest)

    current_dir = os.path.join(dataset_dir, "current")
    if os.path.exists(current_dir):
        shutil.rmtree(current_dir)
    shutil.copytree(version_dir, current_dir)

    classes = _load_json(_classes_path(dataset_dir), {})
    _write_data_yaml(dataset_dir, classes)

    return version_name


# ── Helpers internes ──────────────────────────────────────────────────────────

def _unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{stem}_{i}{ext}"):
        i += 1
    return f"{stem}_{i}{ext}"


def _write_full_image_label(image_path: str, class_id: int) -> None:
    lbl = os.path.splitext(image_path)[0] + ".txt"
    with open(lbl, "w") as f:
        f.write(f"{class_id} 0.5 0.5 1.0 1.0\n")


def _annotate_sam2(image_path: str, class_id: int) -> bool:
    """Annote avec SAM2 point prompt centre. Retourne True si succès."""
    try:
        from ultralytics import SAM
        import numpy as np
        from PIL import Image as PILImage

        model = SAM("sam2_b.pt")
        img = PILImage.open(image_path)
        W, H = img.size
        results = model(image_path, points=[[W // 2, H // 2]], labels=[1], verbose=False)

        masks_data = None
        if results and results[0].masks is not None:
            masks_data = results[0].masks.data.cpu().numpy()

        if masks_data is None or len(masks_data) == 0:
            return False

        mask = masks_data[0].astype(bool)
        if mask.sum() / (H * W) < 0.10:
            return False

        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]
        ph, pw = 0.02 * H, 0.02 * W
        y1 = max(0.0, rmin - ph);  y2 = min(float(H), rmax + 1 + ph)
        x1 = max(0.0, cmin - pw);  x2 = min(float(W), cmax + 1 + pw)

        cx, cy = (x1 + x2) / 2 / W, (y1 + y2) / 2 / H
        w, h   = (x2 - x1) / W, (y2 - y1) / H

        with open(os.path.splitext(image_path)[0] + ".txt", "w") as f:
            f.write(f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
        return True

    except Exception:
        return False


def _write_data_yaml(dataset_dir: str, classes: dict) -> None:
    current = os.path.abspath(os.path.join(dataset_dir, "current")).replace("\\", "/")
    names = [classes[str(i)] for i in range(len(classes))]
    with open(os.path.join(dataset_dir, "data.yaml"), "w") as f:
        f.write(
            f"train: {current}/train/images\n"
            f"val: {current}/valid/images\n"
            f"test: {current}/test/images\n"
            f"nc: {len(classes)}\n"
            f"names: {names}\n"
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dataset manager")
    sub = parser.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add-class")
    p_add.add_argument("class_name")
    p_add.add_argument("--dataset", default=os.path.join(os.path.dirname(__file__), "..", "dataset"))

    p_imp = sub.add_parser("import")
    p_imp.add_argument("images_dir")
    p_imp.add_argument("class_name")
    p_imp.add_argument("--annotation", choices=["auto", "sam2", "manual"], default="auto")
    p_imp.add_argument("--dataset", default=os.path.join(os.path.dirname(__file__), "..", "dataset"))

    p_val = sub.add_parser("validate")
    p_val.add_argument("--dataset", default=os.path.join(os.path.dirname(__file__), "..", "dataset"))

    p_ver = sub.add_parser("version")
    p_ver.add_argument("--dataset", default=os.path.join(os.path.dirname(__file__), "..", "dataset"))

    args = parser.parse_args()

    if args.cmd == "add-class":
        r = add_class(args.dataset, args.class_name)
        print(f"Classe '{args.class_name}' → index {r['index']}")
        print(f"Classes : {r['classes']}")

    elif args.cmd == "import":
        r = import_images(args.dataset, args.images_dir, args.class_name, args.annotation)
        print(f"Import termine : {r['imported']} images, {r['annotated']} annotees, {r['failed']} echecs")

    elif args.cmd == "validate":
        r = validate(args.dataset)
        print(f"{r['validated']} images marquees comme validees")

    elif args.cmd == "version":
        v = create_version(args.dataset)
        print(f"Version creee : {v}")
        print(f"Dataset : {os.path.join(args.dataset, 'versions', v)}")

    else:
        parser.print_help()
