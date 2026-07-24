"""
prepare_conteneur_dataset.py — Prépare le dataset dédié Conteneur (1 classe).
-----------------------------------------------------------------------------
Lit raw/Conteneur/ (labels classe 0, pas de remapping nécessaire),
génère le split train/valid/test dans dataset/conteneur/.

Usage :
  python Application/ml/prepare_conteneur_dataset.py
  python Application/ml/prepare_conteneur_dataset.py --src Application/dataset/raw/Conteneur
                                                      --out Application/dataset/conteneur
"""

import os
import shutil
import random
import argparse
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_SRC = os.path.join(os.path.dirname(__file__), "..", "dataset", "raw", "Conteneur")
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "dataset", "conteneur")


def prepare(src_dir: str, out_dir: str,
            train_ratio=0.75, valid_ratio=0.15, test_ratio=0.10,
            seed=42) -> dict:
    src = Path(src_dir)
    out = Path(out_dir)

    pairs = []
    for img_file in sorted(src.iterdir()):
        if img_file.suffix.lower() not in IMAGE_EXTS:
            continue
        lbl_file = img_file.with_suffix(".txt")
        if lbl_file.exists():
            pairs.append((img_file, lbl_file))

    if not pairs:
        raise ValueError(f"Aucune paire image+label trouvée dans {src_dir}")

    random.seed(seed)
    random.shuffle(pairs)

    n = len(pairs)
    n_train = int(n * train_ratio)
    n_valid = int(n * valid_ratio)
    splits = {
        "train": pairs[:n_train],
        "valid": pairs[n_train:n_train + n_valid],
        "test":  pairs[n_train + n_valid:],
    }

    counts = {}
    for split_name, items in splits.items():
        img_out = out / split_name / "images"
        lbl_out = out / split_name / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        for img_path, lbl_path in items:
            shutil.copy2(img_path, img_out / img_path.name)
            # Labels déjà classe 0 (Conteneur) — copie directe
            shutil.copy2(lbl_path, lbl_out / lbl_path.name)
        counts[split_name] = len(items)

    abs_out = out.resolve().as_posix()
    yaml_content = (
        f"train: {abs_out}/train/images\n"
        f"val:   {abs_out}/valid/images\n"
        f"test:  {abs_out}/test/images\n"
        f"nc: 1\n"
        f"names: ['Conteneur']\n"
    )
    (out / "data.yaml").write_text(yaml_content, encoding="utf-8")
    print(f"data.yaml écrit : {out / 'data.yaml'}")

    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prépare le dataset Conteneur (1 classe)")
    parser.add_argument("--src",   default=DEFAULT_SRC)
    parser.add_argument("--out",   default=DEFAULT_OUT)
    parser.add_argument("--train", type=float, default=0.75)
    parser.add_argument("--valid", type=float, default=0.15)
    parser.add_argument("--test",  type=float, default=0.10)
    parser.add_argument("--seed",  type=int,   default=42)
    args = parser.parse_args()

    print(f"Source  : {args.src}")
    print(f"Sortie  : {args.out}")
    counts = prepare(args.src, args.out, args.train, args.valid, args.test, args.seed)
    total = sum(counts.values())
    print(f"Dataset prêt : {total} paires")
    for split, n in counts.items():
        print(f"  {split:6s} : {n:5d} images")
    print(f"\nLancez ensuite : trainConteneur.bat")
