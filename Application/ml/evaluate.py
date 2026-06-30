"""
evaluate.py — Evaluation complète du modèle YOLO
-------------------------------------------------
Evalue un modèle fine-tuné (best.pt) sur le split test et génère :
  - Métriques globales : mAP50, mAP50-95, Precision, Recall
  - Métriques par classe : idem pour chaque classe
  - Rapport Markdown lisible avec tableau récapitulatif
  - Artefacts ultralytics : matrice de confusion, courbes PR, courbes loss

Usage : python evaluate.py [chemin/best.pt] [chemin/data.yaml]
Etape 4 du pipeline ML — à exécuter après train_baseline.py.
Résultats dans runs/evaluate/.
"""

import os
import json
from datetime import datetime

import numpy as np
from ultralytics import YOLO

DEFAULT_DATA_YAML = os.path.join(
    os.path.dirname(__file__), "..", "data", "data.yaml"
)


def evaluate(
    model_path: str,
    data_yaml: str = DEFAULT_DATA_YAML,
    split: str = "test",
    project_dir: str = None,
    device: int = 0,
) -> dict:
    """
    Evalue le modèle sur le split indiqué.
    Retourne {mAP50, mAP50_95, precision, recall, per_class, report_path}.
    """
    if project_dir is None:
        project_dir = os.path.join(os.path.dirname(__file__), "runs", "evaluate")

    model = YOLO(model_path)
    results = model.val(
        data=data_yaml,
        split=split,
        project=project_dir,
        name="eval",
        device=device,
        exist_ok=True,
        plots=True,
    )

    # Métriques globales
    out = {
        "mAP50":     float(results.box.map50),
        "mAP50_95":  float(results.box.map),
        "precision": float(results.box.mp),
        "recall":    float(results.box.mr),
    }

    # Métriques par classe — np.atleast_1d gère le cas nc=1 (scalaire → array)
    names = results.names  # {0: "conteneur", ...}
    maps  = np.atleast_1d(results.box.maps)  # mAP50-95 par classe
    precs = np.atleast_1d(results.box.p)     # Precision par classe
    recs  = np.atleast_1d(results.box.r)     # Recall par classe

    per_class = {}
    for i, name in names.items():
        per_class[name] = {
            "mAP50_95":  float(maps[i])  if i < len(maps)  else 0.0,
            "precision": float(precs[i]) if i < len(precs) else 0.0,
            "recall":    float(recs[i])  if i < len(recs)  else 0.0,
        }
    out["per_class"] = per_class

    # Rapport Markdown
    report_path = _generate_report(out, project_dir, model_path)
    out["report_path"] = report_path

    # Sauvegarde JSON
    json_path = os.path.join(project_dir, "metrics_eval.json")
    os.makedirs(project_dir, exist_ok=True)
    with open(json_path, "w") as f:
        json.dump({k: v for k, v in out.items() if k != "report_path"}, f, indent=2)

    return out


def _generate_report(metrics: dict, output_dir: str, model_path: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "evaluation_report.md")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# Rapport d'evaluation YOLO",
        f"",
        f"**Date** : {ts}  ",
        f"**Modele** : `{model_path}`",
        f"",
        f"## Metriques globales",
        f"",
        f"| Metrique | Valeur |",
        f"|----------|--------|",
        f"| mAP50    | {metrics['mAP50']:.4f} |",
        f"| mAP50-95 | {metrics['mAP50_95']:.4f} |",
        f"| Precision | {metrics['precision']:.4f} |",
        f"| Recall   | {metrics['recall']:.4f} |",
        f"",
        f"## Metriques par classe",
        f"",
        f"| Classe | mAP50-95 | Precision | Recall |",
        f"|--------|----------|-----------|--------|",
    ]

    for cls_name, m in sorted(metrics["per_class"].items()):
        lines.append(
            f"| {cls_name} | {m['mAP50_95']:.4f} | {m['precision']:.4f} | {m['recall']:.4f} |"
        )

    lines += [
        f"",
        f"## Artefacts",
        f"",
        f"Les courbes PR, la matrice de confusion et les courbes de loss",
        f"sont disponibles dans le dossier : `{output_dir}`",
    ]

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return report_path


if __name__ == "__main__":
    import sys
    model_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "runs", "baseline", "train", "weights", "best.pt"
    )
    data_yaml = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DATA_YAML

    print(f"Evaluation de : {model_path}")
    out = evaluate(model_path, data_yaml)
    print(f"\nmAP50    : {out['mAP50']:.4f}")
    print(f"mAP50-95 : {out['mAP50_95']:.4f}")
    print(f"Precision: {out['precision']:.4f}")
    print(f"Recall   : {out['recall']:.4f}")
    print(f"\nRapport  : {out['report_path']}")
    print(f"\nPar classe :")
    for cls, m in sorted(out["per_class"].items()):
        print(f"  {cls:<15} mAP50-95={m['mAP50_95']:.3f}  P={m['precision']:.3f}  R={m['recall']:.3f}")
