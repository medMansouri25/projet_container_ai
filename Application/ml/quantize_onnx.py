"""
quantize_onnx.py — Quantisation int8 des modèles ONNX pour le navigateur
-------------------------------------------------------------------------
Réduit le poids des modèles ONNX (float32 → uint8) sans réentraînement :
  conteneur.onnx : ~77 Mo → ~20 Mo
  plaque.onnx    : ~37 Mo → ~10 Mo

Seuls les poids sont quantisés (dynamic quantization) ; les activations
restent float32 — compatible onnxruntime-web WASM sans calibration dataset.

Usage : python Application/ml/quantize_onnx.py
"""

import os
import shutil

from onnxruntime.quantization import quantize_dynamic, QuantType

HERE    = os.path.dirname(__file__)
ROOT    = os.path.abspath(os.path.join(HERE, "..", ".."))
FE_DIR  = os.path.join(ROOT, "frontend", "models")

MODELS  = ["conteneur", "plaque"]


def quantize_one(name: str) -> None:
    src = os.path.join(FE_DIR, f"{name}.onnx")
    tmp = os.path.join(FE_DIR, f"{name}_q.onnx")
    if not os.path.exists(src):
        print(f"  {name}: fichier source absent ({src}) — ignoré")
        return

    orig_mb = os.path.getsize(src) / 1024 / 1024
    print(f"  {name}: quantisation {orig_mb:.0f} Mo ...", end=" ", flush=True)

    quantize_dynamic(src, tmp, weight_type=QuantType.QUInt8)

    new_mb = os.path.getsize(tmp) / 1024 / 1024
    shutil.move(tmp, src)          # remplace l'original
    print(f"→ {new_mb:.0f} Mo  (réduction {orig_mb/new_mb:.1f}×)")


def main():
    for name in MODELS:
        quantize_one(name)
    print("Quantisation terminée.")


if __name__ == "__main__":
    main()
