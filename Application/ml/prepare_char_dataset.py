"""
prepare_char_dataset.py — Prépare le dataset caractère du tuteur (o_c, 36 classes)
----------------------------------------------------------------------------------
Le dataset livré via Google Drive est en vrac :
  - fichiers .npy (tenseurs pré-traités) mélangés aux .jpg -> inutiles pour YOLO
  - split valid/ vide, ses données sont dans deux .zip non extraits
  - une partie des images n'a pas de label (téléchargement Drive partiel)

Ce script construit un dataset YOLO propre dans Application/dataset/char/ :
  - extrait les .zip valid
  - ne garde que les paires (image .jpg + label .txt) qui existent toutes deux
  - ignore les .npy
  - écrit un data.yaml local (chemins absolus, nc=36, names 0-9 A-Z)

Idempotent : reconstruit char/ à chaque appel.
"""

import os
import glob
import random
import shutil
import zipfile

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "dataset",
                   "ocr_container-20260708T122750Z-3-002", "ocr_container")
DST = os.path.join(HERE, "..", "dataset", "char")

NAMES = [str(d) for d in range(10)] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
IMG_EXTS = (".jpg", ".jpeg", ".png")


def _extract_valid_zips(workdir):
    """Extrait les valid-*.zip dans un dossier temporaire, retourne son chemin."""
    tmp = os.path.join(workdir, "_valid_extracted")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    zips = glob.glob(os.path.join(SRC, "valid-*.zip"))
    for z in zips:
        try:
            with zipfile.ZipFile(z) as zf:
                zf.extractall(tmp)
            print(f"  extrait : {os.path.basename(z)}")
        except zipfile.BadZipFile:
            print(f"  ZIP illisible ignore : {os.path.basename(z)}")
    return tmp


def _index_by_stem(root, exts):
    """Indexe recursivement les fichiers par nom sans extension."""
    idx = {}
    for ext in exts:
        for p in glob.glob(os.path.join(root, "**", "*" + ext), recursive=True):
            idx[os.path.splitext(os.path.basename(p))[0]] = p
    return idx


def _matched_pairs(image_roots, label_roots):
    """Retourne {stem: (chemin_image, chemin_label)} pour les paires completes."""
    images = {}
    for r in image_roots:
        if os.path.isdir(r):
            images.update(_index_by_stem(r, IMG_EXTS))
    labels = {}
    for r in label_roots:
        if os.path.isdir(r):
            labels.update(_index_by_stem(r, (".txt",)))
    return {s: (images[s], labels[s]) for s in set(images) & set(labels)}


def _write_split(name, pairs):
    """Copie une liste de paires (stem, (img, lbl)) vers DST/name/."""
    out_img = os.path.join(DST, name, "images")
    out_lbl = os.path.join(DST, name, "labels")
    os.makedirs(out_img, exist_ok=True)
    os.makedirs(out_lbl, exist_ok=True)
    for stem, (img, lbl) in pairs:
        shutil.copy2(img, os.path.join(out_img, os.path.basename(img)))
        shutil.copy2(lbl, os.path.join(out_lbl, stem + ".txt"))
    print(f"  {name:6s}: {len(pairs)} paires")
    return len(pairs)


def _write_data_yaml(counts):
    data_path = os.path.join(DST, "data.yaml")
    root = os.path.abspath(DST).replace("\\", "/")
    with open(data_path, "w", encoding="utf-8") as f:
        f.write(f"train: {root}/train/images\n")
        f.write(f"val: {root}/valid/images\n")
        f.write(f"test: {root}/test/images\n\n")
        f.write("nc: 36\n")
        f.write("names: " + str(NAMES) + "\n")
    print(f"  data.yaml ecrit : {data_path}")


def main():
    if not os.path.isdir(SRC):
        raise SystemExit(f"Dataset source introuvable : {SRC}")
    print("Preparation du dataset caractere (36 classes)")

    if os.path.isdir(DST):
        shutil.rmtree(DST, ignore_errors=True)
    os.makedirs(DST, exist_ok=True)

    valid_tmp = _extract_valid_zips(DST)

    # Le test du tuteur reste intact = benchmark honnete.
    test_pairs = _matched_pairs(
        [os.path.join(SRC, "test", "images")],
        [os.path.join(SRC, "test", "labels")],
    )
    # train + valid mis en commun puis re-repartis 85/15 : le telechargement
    # Drive partiel avait laisse valid > train, on maximise l'entrainement.
    pool = _matched_pairs(
        [os.path.join(SRC, "train", "images"),
         os.path.join(SRC, "valid", "images"), valid_tmp],
        [os.path.join(SRC, "train", "labels"),
         os.path.join(SRC, "valid", "labels"), valid_tmp],
    )
    # une image presente dans le test ne doit pas se retrouver en train
    pool = {s: v for s, v in pool.items() if s not in test_pairs}

    items = sorted(pool.items())
    random.Random(42).shuffle(items)
    cut = int(len(items) * 0.85)

    counts = {}
    counts["train"] = _write_split("train", items[:cut])
    counts["valid"] = _write_split("valid", items[cut:])
    counts["test"] = _write_split("test", sorted(test_pairs.items()))

    shutil.rmtree(valid_tmp, ignore_errors=True)
    _write_data_yaml(counts)

    if counts["train"] < 100:
        print("ATTENTION : moins de 100 images d'entrainement appariees.")
    print("Preparation terminee.")


if __name__ == "__main__":
    main()
