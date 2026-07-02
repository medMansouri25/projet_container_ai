"""
evaluate.py — Évaluation d'un modèle versionné
------------------------------------------------
Évalue best_vN.pt sur le split test et génère un rapport dans reports/run_NNN/.

Usage :
  python evaluate.py                      # évalue le dernier modèle
  python evaluate.py --version v1         # évalue une version spécifique
  python evaluate.py --split val
"""

import os
import sys
import json
import argparse
import numpy as np
from datetime import datetime

from ultralytics import YOLO

DEFAULT_DATASET_DIR = os.path.join(os.path.dirname(__file__), "..", "dataset")
DEFAULT_MODELS_DIR  = os.path.join(os.path.dirname(__file__), "..", "models")
DEFAULT_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: str, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def _save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _latest_version(models_dir: str) -> str | None:
    """Retourne la dernière version disponible dans metadata.json."""
    metadata = _load_json(os.path.join(models_dir, "metadata.json"), {})
    if not metadata:
        return None
    return sorted(metadata.keys())[-1]


def _next_run_name(reports_dir: str) -> str:
    if not os.path.isdir(reports_dir):
        return "run_001"
    runs = [d for d in os.listdir(reports_dir) if d.startswith("run_")]
    return f"run_{len(runs) + 1:03d}"


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate(
    dataset_dir: str = DEFAULT_DATASET_DIR,
    models_dir: str  = DEFAULT_MODELS_DIR,
    reports_dir: str = DEFAULT_REPORTS_DIR,
    version: str = None,
    split: str = "test",
    device: int = 0,
) -> dict:
    """
    Évalue best_vN.pt sur le split indiqué.
    version=None → utilise le dernier modèle.
    Retourne {version, mAP50, mAP50_95, precision, recall, report_path}.
    """
    os.makedirs(reports_dir, exist_ok=True)

    if version is None:
        version = _latest_version(models_dir)
        if version is None:
            raise ValueError("Aucun modèle trouvé dans models/. Lancez d'abord train.py.")

    model_path = os.path.join(models_dir, f"best_{version}.pt")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Modèle introuvable : {model_path}")

    data_yaml = os.path.join(dataset_dir, "data.yaml")
    run_name  = _next_run_name(reports_dir)
    run_dir   = os.path.join(reports_dir, run_name)
    os.makedirs(run_dir, exist_ok=True)

    model   = YOLO(model_path)
    results = model.val(
        data=data_yaml,
        split=split,
        project=run_dir,
        name="eval",
        device=device,
        exist_ok=True,
        plots=True,
    )

    # Métriques globales
    out = {
        "version":   version,
        "mAP50":     float(results.box.map50),
        "mAP50_95":  float(results.box.map),
        "precision": float(results.box.mp),
        "recall":    float(results.box.mr),
    }

    # Métriques par classe — np.atleast_1d gère nc=1 (scalaire → array)
    names = results.names
    maps  = np.atleast_1d(results.box.maps)
    precs = np.atleast_1d(results.box.p)
    recs  = np.atleast_1d(results.box.r)

    out["per_class"] = {
        name: {
            "mAP50_95":  float(maps[i])  if i < len(maps)  else 0.0,
            "precision": float(precs[i]) if i < len(precs) else 0.0,
            "recall":    float(recs[i])  if i < len(recs)  else 0.0,
        }
        for i, name in names.items()
    }

    # Rapport Markdown
    report_path = _write_report(out, run_dir, model_path, models_dir)
    out["report_path"] = report_path

    # metrics.json
    _save_json(os.path.join(run_dir, "metrics.json"),
               {k: v for k, v in out.items() if k != "report_path"})

    return out


def _write_report(metrics: dict, run_dir: str, model_path: str, models_dir: str) -> str:
    metadata = _load_json(os.path.join(models_dir, "metadata.json"), {})
    version  = metrics["version"]
    versions = sorted(metadata.keys())
    prev     = versions[versions.index(version) - 1] if versions.index(version) > 0 else None

    lines = [
        f"# Rapport d'evaluation — {version}",
        f"",
        f"**Date** : {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Modele** : `{model_path}`",
        f"",
        f"## Metriques globales",
        f"",
        f"| Metrique | {version} |" + (f" {prev} | Delta |" if prev else ""),
        f"|----------|----------|" + ("----------|-------|" if prev else ""),
    ]

    prev_meta = metadata.get(prev, {}) if prev else {}
    for key, label in [("mAP50","mAP50"), ("mAP50_95","mAP50-95"), ("precision","Precision"), ("recall","Recall")]:
        val = metrics[key]
        row = f"| {label} | {val:.4f} |"
        if prev and key in prev_meta:
            delta = val - prev_meta[key]
            sign  = "+" if delta >= 0 else ""
            row  += f" {prev_meta[key]:.4f} | {sign}{delta:.4f} |"
        lines.append(row)

    lines += [
        "",
        "## Metriques par classe",
        "",
        "| Classe | mAP50-95 | Precision | Recall |",
        "|--------|----------|-----------|--------|",
    ]
    for cls, m in sorted(metrics["per_class"].items()):
        lines.append(f"| {cls} | {m['mAP50_95']:.4f} | {m['precision']:.4f} | {m['recall']:.4f} |")

    report_path = os.path.join(run_dir, "evaluation_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return report_path


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluation modele YOLO")
    parser.add_argument("--dataset",  default=DEFAULT_DATASET_DIR)
    parser.add_argument("--models",   default=DEFAULT_MODELS_DIR)
    parser.add_argument("--reports",  default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--version",  default=None)
    parser.add_argument("--split",    default="test")
    parser.add_argument("--device",   type=int, default=0)
    args = parser.parse_args()

    r = evaluate(args.dataset, args.models, args.reports, args.version, args.split, args.device)
    print(f"\nVersion   : {r['version']}")
    print(f"mAP50     : {r['mAP50']:.4f}")
    print(f"mAP50-95  : {r['mAP50_95']:.4f}")
    print(f"Precision : {r['precision']:.4f}")
    print(f"Recall    : {r['recall']:.4f}")
    print(f"Rapport   : {r['report_path']}")
