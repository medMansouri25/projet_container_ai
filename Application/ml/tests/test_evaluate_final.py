import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evaluate_final import evaluate_final


BASELINE_METRICS = {
    "model_path": "runs/baseline/train/weights/best.pt",
    "mAP50":     0.80,
    "mAP50_95":  0.55,
    "precision": 0.84,
    "recall":    0.76,
}

FINAL_METRICS = {
    "mAP50":     0.92,
    "mAP50_95":  0.71,
    "precision": 0.94,
    "recall":    0.89,
}


@pytest.fixture
def baseline_file(tmp_path):
    path = tmp_path / "metrics_baseline.json"
    path.write_text(json.dumps(BASELINE_METRICS))
    return str(path)


@pytest.fixture
def fake_val_result(tmp_path):
    result = MagicMock()
    result.box.map50 = FINAL_METRICS["mAP50"]
    result.box.map   = FINAL_METRICS["mAP50_95"]
    result.box.mp    = FINAL_METRICS["precision"]
    result.box.mr    = FINAL_METRICS["recall"]
    result.box.maps  = np.array([0.93, 0.91, 0.88])
    result.box.p     = np.array([[0.95, 0.93, 0.90]])
    result.box.r     = np.array([[0.91, 0.87, 0.85]])
    result.names     = {0: "code", 1: "mark3", 2: "plaque"}
    result.save_dir  = str(tmp_path / "eval_final")
    os.makedirs(result.save_dir, exist_ok=True)
    return result


@pytest.fixture
def fake_model(fake_val_result):
    model = MagicMock()
    model.val.return_value = fake_val_result
    return model


# ── Test 1 : retourne les métriques du modèle final ──────────────────────────

def test_returns_final_metrics(fake_model, baseline_file, tmp_path):
    with patch("evaluate_final.YOLO", return_value=fake_model):
        out = evaluate_final(
            model_path="final/best.pt",
            data_yaml="data.yaml",
            baseline_metrics_path=baseline_file,
            project_dir=str(tmp_path),
        )

    assert abs(out["mAP50"]     - 0.92) < 0.001
    assert abs(out["mAP50_95"]  - 0.71) < 0.001
    assert abs(out["precision"] - 0.94) < 0.001
    assert abs(out["recall"]    - 0.89) < 0.001


# ── Test 2 : calcule les deltas baseline → final ──────────────────────────────

def test_computes_deltas_vs_baseline(fake_model, baseline_file, tmp_path):
    with patch("evaluate_final.YOLO", return_value=fake_model):
        out = evaluate_final(
            model_path="final/best.pt",
            data_yaml="data.yaml",
            baseline_metrics_path=baseline_file,
            project_dir=str(tmp_path),
        )

    assert "comparison" in out
    comp = out["comparison"]
    assert abs(comp["mAP50"]["baseline"] - 0.80) < 0.001
    assert abs(comp["mAP50"]["final"]    - 0.92) < 0.001
    assert abs(comp["mAP50"]["delta"]    - 0.12) < 0.001


# ── Test 3 : génère un rapport Markdown comparatif ───────────────────────────

def test_generates_comparative_markdown_report(fake_model, baseline_file, tmp_path):
    with patch("evaluate_final.YOLO", return_value=fake_model):
        out = evaluate_final(
            model_path="final/best.pt",
            data_yaml="data.yaml",
            baseline_metrics_path=baseline_file,
            project_dir=str(tmp_path),
        )

    assert os.path.exists(out["report_path"])
    content = open(out["report_path"]).read()
    assert "baseline" in content.lower() or "Baseline" in content
    assert "final"    in content.lower() or "Final" in content
    assert "0.92"     in content or "92" in content
    assert "0.80"     in content or "80" in content
