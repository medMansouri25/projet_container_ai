"""
prepare_plaque_dataset.py — Prépare le dataset plaque marocaine (Roboflow)
--------------------------------------------------------------------------
Le dataset transmis par le tuteur (Roboflow « moroccan-dataset ») est livré
en vrac dans Application/dataset/plaque_immatriculation_maroc/ :
  - splits pré-découpés aux noms hétérogènes (train_plaque/train,
    valid_palque/valid, test-plaque/test)
  - data.yaml pointant vers des chemins Colab (/content/drive/...) inutilisables
    en local
  - 1 seule classe nommée '0' (zone plaque) ; format YOLO détection

Ce script construit un dataset YOLO propre dans Application/dataset/plaque/ :
  1. NETTOYAGE  : ne garde que les paires (image + label) complètes et lisibles,
     ignore les labels malformés (classe forcée à 0, une seule classe).
  2. ANTI-FUITE : regroupe les images par SOURCE avant re-découpage. Roboflow
     nomme les augmentations `<source>_jpg.rf.<hash>.jpg` — toutes les
     variantes d'une même photo partagent le préfixe `<source>_jpg`. On les
     garde dans le même split (sinon fuite train↔test, cf. ADR-1 et le POC
     Fieldbox : « ne pas mettre des frames d'une même vidéo dans deux splits »).
  3. SPLIT 70/20/10 : re-découpage reproductible (seed) au niveau des sources.
  4. Écrit data.yaml (chemins absolus locaux) + classes.json (nc=1,
     names=['immatriculation']) pour que train.py/evaluate.py aient le bon nom.

Idempotent : reconstruit Application/dataset/plaque/ à chaque appel.

⚠️ Manque connu dans le dataset : les nouvelles plaques marocaines avec la
lettre ط. Sans impact sur la DÉTECTION (le modèle localise la zone quelle que
soit la lettre) ; l'OCR/format les gère (pipeline/plaque.py) mais généralisera
mal faute d'exemples — collecte dédiée à prévoir.
"""

import os
import glob
import random
import shutil

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "dataset", "plaque_immatriculation_maroc")
DST = os.path.join(HERE, "..", "dataset", "plaque")

CLASS_NAME = "immatriculation"
IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

# splits Roboflow (dossier images, dossier labels)
SRC_SPLITS = [
    ("train_plaque", "train"),
    ("valid_palque", "valid"),
    ("test-plaque", "test"),
]

TRAIN_RATIO, VALID_RATIO = 0.70, 0.20  # le reste (0.10) -> test
SEED = 42


def _source_key(stem: str) -> str:
    """Clé de regroupement anti-fuite : préfixe avant le marqueur Roboflow
    `.rf.`. Toutes les augmentations d'une même photo la partagent."""
    return stem.split(".rf.")[0]


def _valid_label(path: str) -> bool:
    """Un label YOLO détection valide : lignes de 5 nombres. Vide autorisé
    (image de fond sans plaque). Retourne False si une ligne est malformée."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if not parts:
                    continue
                if len(parts) != 5:
                    return False
                float(parts[1]); float(parts[2]); float(parts[3]); float(parts[4])
        return True
    except (OSError, ValueError):
        return False


def _collect_pairs() -> dict:
    """Indexe toutes les paires (image, label) complètes des 3 splits source.
    Force la classe à 0 (une seule classe). Retourne {stem: (img, lbl)}."""
    pairs = {}
    for parent, leaf in SRC_SPLITS:
        img_dir = os.path.join(SRC, parent, leaf, "images")
        lbl_dir = os.path.join(SRC, parent, leaf, "labels")
        if not os.path.isdir(img_dir):
            print(f"  ignore (absent) : {img_dir}")
            continue
        for img in glob.glob(os.path.join(img_dir, "*")):
            if os.path.splitext(img)[1].lower() not in IMG_EXTS:
                continue
            stem = os.path.splitext(os.path.basename(img))[0]
            lbl = os.path.join(lbl_dir, stem + ".txt")
            if not os.path.exists(lbl) or not _valid_label(lbl):
                continue
            pairs[stem] = (img, lbl)
    return pairs


def _group_by_source(pairs: dict) -> list:
    """Regroupe les stems par source. Retourne une liste de listes de stems."""
    groups = {}
    for stem in pairs:
        groups.setdefault(_source_key(stem), []).append(stem)
    return list(groups.values())


def _write_split(name: str, stems: list, pairs: dict) -> int:
    """Copie image + label (classe normalisée à 0) vers DST/name/."""
    out_img = os.path.join(DST, name, "images")
    out_lbl = os.path.join(DST, name, "labels")
    os.makedirs(out_img, exist_ok=True)
    os.makedirs(out_lbl, exist_ok=True)
    for stem in stems:
        img, lbl = pairs[stem]
        shutil.copy2(img, os.path.join(out_img, os.path.basename(img)))
        # réécrit le label en forçant la classe 0 (dataset mono-classe)
        with open(lbl, encoding="utf-8") as f:
            lines = [l.split() for l in f if l.split()]
        with open(os.path.join(out_lbl, stem + ".txt"), "w", encoding="utf-8") as f:
            for p in lines:
                f.write("0 " + " ".join(p[1:]) + "\n")
    print(f"  {name:6s}: {len(stems)} images")
    return len(stems)


def _write_data_yaml() -> None:
    root = os.path.abspath(DST).replace("\\", "/")
    with open(os.path.join(DST, "data.yaml"), "w", encoding="utf-8") as f:
        f.write(f"train: {root}/train/images\n")
        f.write(f"val: {root}/valid/images\n")
        f.write(f"test: {root}/test/images\n\n")
        f.write("nc: 1\n")
        f.write(f"names: ['{CLASS_NAME}']\n")


def _write_classes_json() -> None:
    import json
    with open(os.path.join(DST, "classes.json"), "w", encoding="utf-8") as f:
        json.dump({"0": CLASS_NAME}, f, indent=2, ensure_ascii=False)


def main():
    if not os.path.isdir(SRC):
        raise SystemExit(f"Dataset source introuvable : {SRC}")
    print("Preparation du dataset plaque marocaine (1 classe : immatriculation)")

    pairs = _collect_pairs()
    if not pairs:
        raise SystemExit("Aucune paire image+label valide trouvee.")
    print(f"  {len(pairs)} paires image+label valides collectees")

    groups = _group_by_source(pairs)
    print(f"  {len(groups)} sources distinctes (anti-fuite par augmentation)")

    random.Random(SEED).shuffle(groups)
    n = len(groups)
    n_train = int(n * TRAIN_RATIO)
    n_valid = int(n * VALID_RATIO)

    def flatten(gs):
        return [stem for g in gs for stem in g]

    if os.path.isdir(DST):
        shutil.rmtree(DST, ignore_errors=True)
    os.makedirs(DST, exist_ok=True)

    counts = {
        "train": _write_split("train", flatten(groups[:n_train]), pairs),
        "valid": _write_split("valid", flatten(groups[n_train:n_train + n_valid]), pairs),
        "test":  _write_split("test",  flatten(groups[n_train + n_valid:]), pairs),
    }

    _write_data_yaml()
    _write_classes_json()
    print(f"  data.yaml + classes.json ecrits dans {os.path.abspath(DST)}")

    total = sum(counts.values())
    print(f"Repartition : "
          f"train {counts['train']/total*100:.0f}% / "
          f"valid {counts['valid']/total*100:.0f}% / "
          f"test {counts['test']/total*100:.0f}%")
    if counts["train"] < 100:
        print("ATTENTION : moins de 100 images d'entrainement.")
    print("Preparation terminee.")


if __name__ == "__main__":
    main()
