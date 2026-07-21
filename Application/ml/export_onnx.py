"""
export_onnx.py — Export ONNX des détecteurs pour le navigateur
---------------------------------------------------------------
Exporte les modèles YOLO en ONNX (onnxruntime-web, WASM).
Entrée figée (1,3,640,640), opset 12 = large compat web.

Cibles disponibles :
  conteneur       -> models/best_vN.pt          -> frontend/models/conteneur.onnx
  plaque          -> models/plaque/best_vN.pt   -> frontend/models/plaque.onnx
  plaque_browser  -> models/plaque_browser/best_vN.pt -> frontend/models/plaque.onnx
                     (yolo11n entrainé via : trainImmat.bat browser)

Usage :
  python Application/ml/export_onnx.py                    # exporte tout
  python Application/ml/export_onnx.py --target plaque_browser
"""

import argparse
import os
import shutil

from ultralytics import YOLO

HERE    = os.path.dirname(__file__)
ROOT    = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_DIR = os.path.join(ROOT, "frontend", "models")
IMGSZ   = 640

# Définition des cibles : (dossier modèle, nom fichier ONNX de sortie)
TARGETS = {
    "conteneur": (
        os.path.join(ROOT, "Application", "models"),
        "conteneur.onnx",
    ),
    "plaque": (
        os.path.join(ROOT, "Application", "models", "plaque"),
        "plaque.onnx",
    ),
    "plaque_browser": (
        os.path.join(ROOT, "Application", "models", "plaque_browser"),
        "plaque.onnx",          # remplace le même fichier navigateur
    ),
}


def _latest_pt(models_dir: str) -> str | None:
    """Retourne le dernier best_vN.pt dans un dossier, ou None."""
    if not os.path.isdir(models_dir):
        return None
    pts = sorted(f for f in os.listdir(models_dir)
                 if f.startswith("best_v") and f.endswith(".pt"))
    return os.path.join(models_dir, pts[-1]) if pts else None


def export_one(models_dir: str, onnx_name: str) -> str | None:
    """Exporte le dernier .pt du dossier vers frontend/models/<onnx_name>."""
    pt = _latest_pt(models_dir)
    if not pt:
        print(f"  aucun best_vN.pt dans {models_dir} — ignoré")
        return None

    model    = YOLO(pt)
    onnx_src = model.export(format="onnx", imgsz=IMGSZ, opset=12,
                            simplify=True, dynamic=False)
    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, onnx_name)
    shutil.copy2(onnx_src, dst)
    mb = os.path.getsize(dst) / 1024 / 1024
    print(f"  {os.path.basename(pt)} -> {dst} ({mb:.0f} Mo)")
    return dst


def main(targets: list[str] | None = None) -> None:
    if targets is None:
        targets = list(TARGETS.keys())

    for name in targets:
        if name not in TARGETS:
            print(f"  cible inconnue : {name}  (valeurs : {', '.join(TARGETS)})")
            continue
        models_dir, onnx_name = TARGETS[name]
        print(f"\n[{name}]")
        export_one(models_dir, onnx_name)

    print("\nExport ONNX terminé.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", nargs="+",
                        help="cibles à exporter (défaut : toutes)")
    args = parser.parse_args()
    main(args.target)
