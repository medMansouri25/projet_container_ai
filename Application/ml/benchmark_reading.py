"""
benchmark_reading.py — Char reader (YOLO 36 classes) vs EasyOCR
----------------------------------------------------------------
Compare les deux moteurs de lecture sur le test du tuteur (crops de codes,
vérité terrain reconstruite depuis les labels caractère). Ne garde que les
échantillons dont le label forme un code BIC valide ISO 6346 (les conteneurs) :
c'est là que la comparaison a un sens métier.

Mesure, moteur contre moteur :
  - taux de code EXACT (chaîne identique à la vérité)
  - taux de code valide ISO
  - temps moyen par image

Usage : python benchmark_reading.py [--limit N] [--char-model chemin.pt]
"""

import os
import sys
import time
import glob
import argparse

import cv2

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "backend", "pipeline"))

import ocr
import char_reader

TEST_DIR = os.path.join(HERE, "..", "dataset", "char", "test")
DEFAULT_CHAR = os.path.join(HERE, "..", "models", "char", "best_v1.pt")

NAMES = [str(d) for d in range(10)] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def _truth_from_label(label_path):
    """Reconstruit le code depuis un label caractère + son orientation.
    Retourne (code_valide_ISO ou None, vertical)."""
    dets = []
    for line in open(label_path):
        p = line.split()
        if len(p) < 5:
            continue
        cls, cx, cy, w, h = int(p[0]), float(p[1]), float(p[2]), float(p[3]), float(p[4])
        dets.append((cx, cy, w, h, NAMES[cls], 1.0))
    if not dets:
        return None, False
    xs = [d[0] for d in dets]
    ys = [d[1] for d in dets]
    vertical = (max(ys) - min(ys)) > (max(xs) - min(xs))
    lines = char_reader._group_lines(dets, vertical)
    res = ocr.resolve_bic(lines)
    if res["bic"] and res["valid"] and not res["corrected"]:
        return res["bic"], vertical
    return None, vertical


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--char-model", default=DEFAULT_CHAR)
    args = ap.parse_args()

    from ultralytics import YOLO
    char_model = YOLO(args.char_model)
    reader = ocr._get_reader()

    labels = sorted(glob.glob(os.path.join(TEST_DIR, "labels", "*.txt")))
    img_dir = os.path.join(TEST_DIR, "images")

    stats = {"char": {"exact": 0, "valid": 0, "t": 0.0},
             "easy": {"exact": 0, "valid": 0, "t": 0.0}}
    n = 0
    for lbl in labels:
        stem = os.path.splitext(os.path.basename(lbl))[0]
        imgs = glob.glob(os.path.join(img_dir, stem + ".*"))
        if not imgs:
            continue
        truth, vertical = _truth_from_label(lbl)
        if truth is None:            # pas un code conteneur propre -> ignore
            continue
        img = cv2.imread(imgs[0])
        if img is None:
            continue

        t0 = time.monotonic()
        c = char_reader.read_bic(img, model=char_model, vertical=vertical)
        stats["char"]["t"] += time.monotonic() - t0
        if c["bic"] == truth:
            stats["char"]["exact"] += 1
        if c["valid"]:
            stats["char"]["valid"] += 1

        t0 = time.monotonic()
        e = ocr.extract_bic(img, vertical=vertical, reader=reader, is_zone=True)
        stats["easy"]["t"] += time.monotonic() - t0
        if e["bic"] == truth:
            stats["easy"]["exact"] += 1
        if e["valid"]:
            stats["easy"]["valid"] += 1

        n += 1
        if n >= args.limit:
            break

    if n == 0:
        print("Aucun echantillon conteneur trouve.")
        return
    print("\n" + "=" * 58)
    print(f"BENCHMARK LECTURE — {n} codes conteneurs (test tuteur)")
    print("=" * 58)
    print(f"{'Moteur':<12}{'Code exact':>14}{'Valide ISO':>14}{'Temps/img':>14}")
    for key, label in (("char", "YOLO char"), ("easy", "EasyOCR")):
        s = stats[key]
        print(f"{label:<12}{s['exact']/n*100:>12.1f}%{s['valid']/n*100:>13.1f}%"
              f"{s['t']/n*1000:>11.0f} ms")
    print("=" * 58)


if __name__ == "__main__":
    main()
