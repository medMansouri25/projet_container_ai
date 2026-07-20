"""
benchmark_plaque.py — Qualité de lecture des plaques marocaines (EasyOCR ar/en)
-------------------------------------------------------------------------------
Le dataset Roboflow n'a PAS de vérité terrain texte (labels = bbox de zone
seulement) : impossible de calculer un « exact match » automatique. Ce
benchmark mesure donc ce qui est mesurable **sans vérité terrain** et produit
un artefact de **vérification humaine** (crops + lecture), comme le check réel
qui a arbitré le BIC (ADR-6).

Deux sources de crop :
  --source labels  (défaut) : découpe via la box du LABEL → isole la qualité
                    OCR, indépendante du détecteur (marche même sans best.pt).
  --source detect  : bout en bout via models/plaque/best_vN.pt (détection + OCR).

Mesures (sur N échantillons) :
  - taux de LECTURE      : une plaque non vide a été composée
  - taux de FORME valide : série + lettre connue + région (validation de forme)
  - taux LETTRE lue      : lettre ≠ '?' (le point faible : lettre arabe isolée)
  - temps moyen / image
Chaque crop est sauvegardé + un report.md liste « image → lecture » (l'arabe
s'affiche en markdown, pas en overlay OpenCV).

Usage :
  python benchmark_plaque.py [--limit 30] [--source labels|detect] [--conf 0.25]
"""

import os
import sys
import time
import glob
import shutil
import argparse
from datetime import datetime

import cv2

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "backend", "pipeline"))

import plaque  # noqa: E402

TEST_DIR = os.path.join(HERE, "..", "dataset", "plaque", "test")
OUT_DIR = os.path.join(HERE, "..", "reports", "plaque", "benchmark")


def _crop_from_label(img, label_path, margin=0.05):
    """Retourne le crop de la plus grande box du label (YOLO normalisé)."""
    H, W = img.shape[:2]
    best, best_area = None, 0.0
    for line in open(label_path, encoding="utf-8"):
        p = line.split()
        if len(p) < 5:
            continue
        cx, cy, w, h = map(float, p[1:5])
        if w * h > best_area:
            best_area = w * h
            best = (cx, cy, w, h)
    if best is None:
        return None
    cx, cy, w, h = best
    x1 = int((cx - w / 2 - margin * w) * W)
    y1 = int((cy - h / 2 - margin * h) * H)
    x2 = int((cx + w / 2 + margin * w) * W)
    y2 = int((cy + h / 2 + margin * h) * H)
    return img[max(0, y1):min(H, y2), max(0, x1):min(W, x2)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--source", choices=["labels", "detect"], default="labels")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()

    if not os.path.isdir(TEST_DIR):
        raise SystemExit(f"Split test introuvable : {TEST_DIR}\n"
                         f"Lance d'abord la preparation (trainImmat.bat).")

    detector = None
    if args.source == "detect":
        sys.path.insert(0, os.path.join(HERE, "..", "backend", "pipeline"))
        import detector as det_mod
        if det_mod._get_plaque_model(det_mod.DEFAULT_MODELS_DIR) is None:
            raise SystemExit("Aucun modele plaque (best_vN.pt). Lance trainImmat.bat "
                             "ou utilise --source labels.")
        detector = det_mod

    reader = plaque._get_reader()  # arabe si dispo, sinon anglais seul (chiffres)

    if os.path.isdir(args.out):
        shutil.rmtree(args.out, ignore_errors=True)
    os.makedirs(args.out, exist_ok=True)

    images = sorted(glob.glob(os.path.join(TEST_DIR, "images", "*")))
    lbl_dir = os.path.join(TEST_DIR, "labels")

    stats = {"n": 0, "read": 0, "valid": 0, "letter": 0, "t": 0.0}
    rows = []

    for img_path in images:
        if stats["n"] >= args.limit:
            break
        stem = os.path.splitext(os.path.basename(img_path))[0]
        img = cv2.imread(img_path)
        if img is None:
            continue

        if args.source == "labels":
            lbl = os.path.join(lbl_dir, stem + ".txt")
            if not os.path.exists(lbl):
                continue
            crop = _crop_from_label(img, lbl)
        else:
            det = detector.detect_plaque(img_path, conf=args.conf)
            crop = det["crop"] if det["found"] else None
        if crop is None or crop.size == 0:
            continue

        t0 = time.monotonic()
        res = plaque.extract_plaque(crop)
        dt = time.monotonic() - t0

        stats["n"] += 1
        stats["t"] += dt
        if res["plaque"]:
            stats["read"] += 1
        if res["valid"]:
            stats["valid"] += 1
        if res["letter"] != "?":
            stats["letter"] += 1

        crop_name = f"{stats['n']:03d}_{stem[:20]}.jpg"
        cv2.imwrite(os.path.join(args.out, crop_name), crop)
        rows.append((crop_name, res["plaque"] or "—", res["valid"],
                     res["letter"], round(dt * 1000)))

    _write_report(args, stats, rows)
    _print_summary(args, stats)


def _write_report(args, stats, rows):
    n = max(stats["n"], 1)
    lines = [
        "# Benchmark lecture plaque — vérification humaine",
        "",
        f"**Date** : {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Source crop** : {args.source} · **échantillons** : {stats['n']}",
        "",
        "> Pas de vérité terrain texte : les taux ci-dessous sont *automatiques*,",
        "> mais la **justesse réelle** se juge à l'œil (colonne image vs lecture).",
        "",
        "## Taux (sans vérité terrain)",
        "",
        "| Mesure | Taux |",
        "|--------|------|",
        f"| Lecture (plaque composée) | {stats['read']/n*100:.1f} % |",
        f"| Forme valide (série+lettre+région) | {stats['valid']/n*100:.1f} % |",
        f"| Lettre arabe lue (≠ ?) | {stats['letter']/n*100:.1f} % |",
        f"| Temps moyen / image | {stats['t']/n*1000:.0f} ms |",
        "",
        "## Détail (à vérifier visuellement)",
        "",
        "| Crop | Lecture | Forme OK | Lettre |",
        "|------|---------|----------|--------|",
    ]
    for name, read, valid, letter, ms in rows:
        lines.append(f"| ![]({name}) | `{read}` | {'✅' if valid else '—'} | {letter} |")
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _print_summary(args, stats):
    n = max(stats["n"], 1)
    print("\n" + "=" * 58)
    print(f"BENCHMARK PLAQUE — {stats['n']} images (source: {args.source})")
    print("=" * 58)
    print(f"Lecture composee   : {stats['read']/n*100:>5.1f} %")
    print(f"Forme valide       : {stats['valid']/n*100:>5.1f} %")
    print(f"Lettre arabe lue   : {stats['letter']/n*100:>5.1f} %")
    print(f"Temps moyen/image  : {stats['t']/n*1000:>5.0f} ms")
    print("=" * 58)
    print(f"Crops + report.md  : {os.path.abspath(args.out)}")
    print("-> ouvre report.md pour juger lecture vs image (verite humaine).")


if __name__ == "__main__":
    main()
