"""
export_onnx.py — Export ONNX des détecteurs pour exécution navigateur
----------------------------------------------------------------------
Exporte les modèles YOLO de détection (conteneur + plaque) en ONNX afin de
faire tourner le **guide de capture live dans le navigateur** via
onnxruntime-web (décision archi (a), ADR-12) — seul le cadrage/repère de
distance tourne côté client ; l'OCR reste sur le VPS.

Sortie : frontend/models/<name>.onnx (servi statiquement par Vercel, fetché
par onnxruntime-web). Entrée figée (1,3,640,640), opset 12 = large compat web.

Usage : python Application/ml/export_onnx.py
"""

import os
import shutil

from ultralytics import YOLO

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_DIR = os.path.join(ROOT, "frontend", "models")
IMGSZ = 640

MODELS = {
    "conteneur": os.path.join(ROOT, "Application", "models", "best_v2.pt"),
    "plaque": os.path.join(ROOT, "Application", "models", "plaque", "best_v1.pt"),
}


def export_one(name: str, pt_path: str) -> str:
    """Exporte un .pt en .onnx (entrée figée, opset web) et le copie vers
    frontend/models/<name>.onnx. Retourne le chemin de destination."""
    model = YOLO(pt_path)
    onnx_src = model.export(format="onnx", imgsz=IMGSZ, opset=12,
                            simplify=True, dynamic=False)
    dst = os.path.join(OUT_DIR, f"{name}.onnx")
    shutil.copy2(onnx_src, dst)
    return dst


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, pt in MODELS.items():
        if not os.path.exists(pt):
            print(f"  {name}: modele absent ({pt}) — ignore")
            continue
        dst = export_one(name, pt)
        print(f"  {name}: {dst} ({os.path.getsize(dst) // 1024} Ko)")
    print("Export ONNX termine.")


if __name__ == "__main__":
    main()
