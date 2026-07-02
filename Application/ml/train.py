"""
train.py — Fine-tuning incrémental YOLO11m
-------------------------------------------
Repart toujours du dernier best_vN.pt (ou yolo11m.pt pour v1).
Le modèle n'oublie pas quand on ajoute une nouvelle classe.

Usage :
  python train.py                   # mode normal
  python train.py --tune            # optimisation hyperparams + train final
  python train.py --epochs 100
  python train.py --dataset Application/dataset --models Application/models
"""

import os
import sys
import json
import shutil
import argparse
from datetime import datetime

from ultralytics import YOLO

DEFAULT_BASE_MODEL = os.path.join(
    os.path.dirname(__file__), "..", "..", "TestYolo", "yolo11m.pt"
)
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


def _get_latest_model(models_dir: str) -> str | None:
    """Retourne le chemin vers le best_vN.pt le plus récent, ou None."""
    if not os.path.isdir(models_dir):
        return None
    pts = sorted(
        f for f in os.listdir(models_dir)
        if f.startswith("best_v") and f.endswith(".pt")
    )
    return os.path.join(models_dir, pts[-1]) if pts else None


def _next_version_name(models_dir: str) -> str:
    """Retourne le prochain nom de version : v1, v2, v3..."""
    if not os.path.isdir(models_dir):
        return "v1"
    pts = [f for f in os.listdir(models_dir) if f.startswith("best_v") and f.endswith(".pt")]
    return f"v{len(pts) + 1}"


def _next_run_name(reports_dir: str) -> str:
    """Retourne le prochain nom de run : run_001, run_002..."""
    if not os.path.isdir(reports_dir):
        return "run_001"
    runs = [d for d in os.listdir(reports_dir) if d.startswith("run_")]
    return f"run_{len(runs) + 1:03d}"


def _read_classes(dataset_dir: str) -> list:
    classes = _load_json(os.path.join(dataset_dir, "classes.json"), {})
    return [classes[str(i)] for i in range(len(classes))]


HYPERPARAM_KEYS = ["lr0", "lrf", "momentum", "weight_decay", "batch", "imgsz", "epochs", "optimizer"]


def _read_hyperparams(save_dir: str) -> dict:
    """Lit les hyperparamètres clés depuis args.yaml du run YOLO."""
    args_path = os.path.join(save_dir, "args.yaml")
    if not os.path.exists(args_path):
        return {}
    import yaml
    with open(args_path, encoding="utf-8") as f:
        args = yaml.safe_load(f) or {}
    return {k: args[k] for k in HYPERPARAM_KEYS if k in args}


def _write_run_report(out: dict, run_dir: str) -> str:
    """Écrit reports/run_NNN/report.md : métriques en % + hyperparamètres."""
    lines = [
        f"# Rapport d'entrainement — {out['version']}",
        "",
        f"**Date** : {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Meilleur modele** : `{out['model_path']}`",
        "",
        "## Resultats",
        "",
        "| Metrique | Score |",
        "|----------|-------|",
        f"| mAP50 | {out['mAP50'] * 100:.2f} % |",
        f"| mAP50-95 | {out['mAP50_95'] * 100:.2f} % |",
        f"| Precision | {out['precision'] * 100:.2f} % |",
        f"| Recall | {out['recall'] * 100:.2f} % |",
        "",
        "## Hyperparametres",
        "",
        "| Parametre | Valeur |",
        "|-----------|--------|",
    ]
    for k, v in out.get("hyperparameters", {}).items():
        lines.append(f"| {k} | {v} |")

    report_path = os.path.join(run_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return report_path


# ── Public API ────────────────────────────────────────────────────────────────

def train(
    dataset_dir: str = DEFAULT_DATASET_DIR,
    models_dir: str = DEFAULT_MODELS_DIR,
    reports_dir: str = DEFAULT_REPORTS_DIR,
    base_model: str = DEFAULT_BASE_MODEL,
    epochs: int = 20,
    patience: int = 10,
    device: int = 0,
    tune: bool = False,
    tune_iterations: int = 30,
    tune_epochs: int = 13,
) -> dict:
    """
    Lance le fine-tuning YOLO11m de façon incrémentale.
    Repart depuis le dernier best_vN.pt (ou yolo11m.pt pour v1).
    Sauvegarde models/best_vN.pt, met à jour metadata.json, crée reports/run_NNN/.
    Retourne {"version", "model_path", "mAP50", "mAP50_95", "precision", "recall", "run"}.
    """
    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    data_yaml   = os.path.join(dataset_dir, "data.yaml")
    start_model = _get_latest_model(models_dir) or base_model
    version     = _next_version_name(models_dir)
    run_name    = _next_run_name(reports_dir)
    run_dir     = os.path.join(reports_dir, run_name)
    os.makedirs(run_dir, exist_ok=True)

    model = YOLO(start_model)

    if tune:
        model.tune(
            data=data_yaml,
            iterations=tune_iterations,
            epochs=tune_epochs,
            device=device,
            plots=False,
            save=False,
            val=False,
        )

    results = model.train(
        data=data_yaml,
        epochs=epochs,
        patience=patience,
        project=run_dir,
        name="train",
        device=device,
        exist_ok=True,
        workers=8,       # chargement des images en parallèle (le GPU n'attend plus)
        cache=True,      # images en RAM après la 1re epoch (plus de lecture disque)
        batch=-1,        # auto : utilise le max de VRAM disponible
        cos_lr=True,     # learning rate cosinus : descente douce, meilleur final
    )

    # Copie best.pt → models/best_vN.pt (YOLO le sauvegarde dans weights/)
    best_src = os.path.join(results.save_dir, "weights", "best.pt")
    best_dst = os.path.join(models_dir, f"best_{version}.pt")
    shutil.copy2(best_src, best_dst)

    metrics = results.results_dict
    out = {
        "version":   version,
        "model_path": best_dst,
        "mAP50":     metrics.get("metrics/mAP50(B)", 0.0),
        "mAP50_95":  metrics.get("metrics/mAP50-95(B)", 0.0),
        "precision": metrics.get("metrics/precision(B)", 0.0),
        "recall":    metrics.get("metrics/recall(B)", 0.0),
        "run":       run_name,
        "hyperparameters": _read_hyperparams(str(results.save_dir)),
    }

    _write_run_report(out, run_dir)

    # Met à jour metadata.json
    metadata = _load_json(os.path.join(models_dir, "metadata.json"), {})
    metadata[version] = {
        "model_path":  best_dst,
        "classes":     _read_classes(dataset_dir),
        "mAP50":       out["mAP50"],
        "mAP50_95":    out["mAP50_95"],
        "precision":   out["precision"],
        "recall":      out["recall"],
        "run":         run_name,
        "date":        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "epochs":      epochs,
        "tuned":       tune,
        "hyperparameters": out["hyperparameters"],
    }
    _save_json(os.path.join(models_dir, "metadata.json"), metadata)

    return out


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-tuning incrémental YOLO11m")
    parser.add_argument("--dataset",  default=DEFAULT_DATASET_DIR)
    parser.add_argument("--models",   default=DEFAULT_MODELS_DIR)
    parser.add_argument("--reports",  default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--epochs",   type=int, default=20)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--device",   type=int, default=0)
    parser.add_argument("--tune",     action="store_true")
    parser.add_argument("--tune-iterations", type=int, default=30)
    parser.add_argument("--tune-epochs",     type=int, default=13)
    args = parser.parse_args()

    print(f"Mode : {'optimisation (tune)' if args.tune else 'normal'}")
    r = train(
        dataset_dir=args.dataset,
        models_dir=args.models,
        reports_dir=args.reports,
        base_model=args.base_model,
        epochs=args.epochs,
        patience=args.patience,
        device=args.device,
        tune=args.tune,
        tune_iterations=args.tune_iterations,
        tune_epochs=args.tune_epochs,
    )
    print(f"\n{'='*50}")
    print(f"Version          : {r['version']}")
    print(f"Meilleur modele  : {r['model_path']}")
    print(f"{'='*50}")
    print(f"mAP50     : {r['mAP50'] * 100:.2f} %")
    print(f"mAP50-95  : {r['mAP50_95'] * 100:.2f} %")
    print(f"Precision : {r['precision'] * 100:.2f} %")
    print(f"Recall    : {r['recall'] * 100:.2f} %")
    print(f"{'='*50}")
    print("Hyperparametres :")
    for k, v in r["hyperparameters"].items():
        print(f"  {k:<14} : {v}")
    print(f"{'='*50}")
    print(f"Rapport   : {r['run']}/report.md")
