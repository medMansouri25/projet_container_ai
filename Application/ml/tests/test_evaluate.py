import os
import sys
import pytest
from unittest.mock import patch, MagicMock
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evaluate import evaluate


@pytest.fixture
def fake_val_result(tmp_path):
    """Simule le retour de model.val() ultralytics."""
    result = MagicMock()

    # Métriques globales
    result.box.map50 = 0.87
    result.box.map   = 0.62
    result.box.mp    = 0.91
    result.box.mr    = 0.83

    # Par classe : 3 classes factices
    result.box.maps = np.array([0.90, 0.85, 0.80])  # mAP50-95 par classe
    result.box.p    = np.array([[0.92, 0.88, 0.84]])  # precision (shape: [1, nc])
    result.box.r    = np.array([[0.89, 0.82, 0.78]])  # recall

    result.names = {0: "code", 1: "mark3", 2: "plaque"}
    result.save_dir = str(tmp_path / "eval")
    os.makedirs(result.save_dir, exist_ok=True)

    return result


@pytest.fixture
def fake_model(fake_val_result):
    model = MagicMock()
    model.val.return_value = fake_val_result
    return model


# ── Test 1 : métriques globales ───────────────────────────────────────────────

def test_returns_global_metrics(fake_model, tmp_path):
    with patch("evaluate.YOLO", return_value=fake_model):
        out = evaluate("best.pt", "data.yaml", project_dir=str(tmp_path))

    assert abs(out["mAP50"]    - 0.87) < 0.001
    assert abs(out["mAP50_95"] - 0.62) < 0.001
    assert abs(out["precision"] - 0.91) < 0.001
    assert abs(out["recall"]   - 0.83) < 0.001


# ── Test 2 : métriques par classe ─────────────────────────────────────────────

def test_returns_per_class_metrics(fake_model, tmp_path):
    with patch("evaluate.YOLO", return_value=fake_model):
        out = evaluate("best.pt", "data.yaml", project_dir=str(tmp_path))

    assert "per_class" in out
    assert "code"   in out["per_class"]
    assert "mark3"  in out["per_class"]
    assert "plaque" in out["per_class"]
    assert abs(out["per_class"]["code"]["mAP50_95"] - 0.90) < 0.001
    assert abs(out["per_class"]["code"]["precision"] - 0.92) < 0.001


# ── Test 3 : génère un rapport Markdown ──────────────────────────────────────

def test_generates_markdown_report(fake_model, tmp_path):
    with patch("evaluate.YOLO", return_value=fake_model):
        out = evaluate("best.pt", "data.yaml", project_dir=str(tmp_path))

    assert "report_path" in out
    assert os.path.exists(out["report_path"])
    assert out["report_path"].endswith(".md")


# ── Test 4 : rapport contient noms de classes et valeurs ─────────────────────

def test_report_contains_class_names_and_values(fake_model, tmp_path):
    with patch("evaluate.YOLO", return_value=fake_model):
        out = evaluate("best.pt", "data.yaml", project_dir=str(tmp_path))

    content = open(out["report_path"]).read()
    assert "code"   in content
    assert "mark3"  in content
    assert "plaque" in content
    assert "mAP50"  in content
    assert "0.87"   in content or "87" in content
