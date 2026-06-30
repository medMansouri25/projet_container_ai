import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from train_baseline import train_baseline


@pytest.fixture
def fake_train_result(tmp_path):
    """Simule le résultat ultralytics model.train()."""
    save_dir = tmp_path / "baseline" / "weights"
    save_dir.mkdir(parents=True)
    best_pt = save_dir / "best.pt"
    best_pt.write_bytes(b"fake-weights")

    result = MagicMock()
    result.save_dir = str(save_dir)
    result.results_dict = {
        "metrics/mAP50(B)":    0.87,
        "metrics/mAP50-95(B)": 0.62,
        "metrics/precision(B)": 0.91,
        "metrics/recall(B)":   0.83,
    }
    return result, str(best_pt)


# ── Test 1 : retourne toutes les métriques attendues ─────────────────────────

def test_returns_all_expected_metrics(fake_train_result, tmp_path):
    fake_result, best_pt = fake_train_result
    fake_model = MagicMock()
    fake_model.train.return_value = fake_result

    with patch("train_baseline.YOLO", return_value=fake_model):
        out = train_baseline(
            data_yaml="data.yaml",
            base_model="yolo11m.pt",
            epochs=50,
            project_dir=str(tmp_path),
        )

    assert set(out.keys()) >= {"model_path", "mAP50", "mAP50_95", "precision", "recall"}
    assert abs(out["mAP50"] - 0.87) < 0.001
    assert abs(out["mAP50_95"] - 0.62) < 0.001
    assert abs(out["precision"] - 0.91) < 0.001
    assert abs(out["recall"] - 0.83) < 0.001


# ── Test 2 : model_path pointe vers best.pt ──────────────────────────────────

def test_model_path_points_to_best_pt(fake_train_result, tmp_path):
    fake_result, best_pt = fake_train_result
    fake_model = MagicMock()
    fake_model.train.return_value = fake_result

    with patch("train_baseline.YOLO", return_value=fake_model):
        out = train_baseline("data.yaml", "yolo11m.pt", project_dir=str(tmp_path))

    assert out["model_path"] == best_pt
    assert out["model_path"].endswith("best.pt")


# ── Test 3 : appelle YOLO avec patience et device ────────────────────────────

def test_calls_yolo_with_patience_and_device(fake_train_result, tmp_path):
    fake_result, _ = fake_train_result
    fake_model = MagicMock()
    fake_model.train.return_value = fake_result

    with patch("train_baseline.YOLO", return_value=fake_model) as mock_yolo:
        train_baseline(
            data_yaml="data.yaml",
            base_model="yolo11m.pt",
            epochs=50,
            patience=10,
            device=0,
            project_dir=str(tmp_path),
        )

    call_kwargs = fake_model.train.call_args.kwargs
    assert call_kwargs.get("patience") == 10
    assert call_kwargs.get("device") == 0
    assert call_kwargs.get("epochs") == 50
