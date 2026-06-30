import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from train_final import train_final


FAKE_HYPERPARAMS = {
    "lr0": 0.00812,
    "lrf": 0.01234,
    "momentum": 0.943,
    "weight_decay": 0.0004,
    "warmup_epochs": 2.5,
    "box": 7.5,
    "cls": 0.5,
    "mosaic": 1.0,
}


@pytest.fixture
def hyperparams_file(tmp_path):
    path = tmp_path / "best_hyperparams.json"
    path.write_text(json.dumps(FAKE_HYPERPARAMS))
    return str(path)


@pytest.fixture
def fake_train_result(tmp_path):
    save_dir = tmp_path / "final" / "weights"
    save_dir.mkdir(parents=True)
    best_pt = save_dir / "best.pt"
    best_pt.write_bytes(b"weights")

    result = MagicMock()
    result.save_dir = str(save_dir)
    result.results_dict = {
        "metrics/mAP50(B)":    0.92,
        "metrics/mAP50-95(B)": 0.71,
        "metrics/precision(B)": 0.94,
        "metrics/recall(B)":   0.89,
    }
    return result, str(best_pt)


@pytest.fixture
def fake_model(fake_train_result):
    result, _ = fake_train_result
    model = MagicMock()
    model.train.return_value = result
    return model


# ── Test 1 : charge les hyperparams depuis JSON et les passe à train() ────────

def test_passes_hyperparams_to_train(fake_model, hyperparams_file, tmp_path):
    with patch("train_final.YOLO", return_value=fake_model):
        train_final(
            data_yaml="data.yaml",
            base_model="yolo11m.pt",
            hyperparams_path=hyperparams_file,
            project_dir=str(tmp_path),
        )

    call_kwargs = fake_model.train.call_args.kwargs
    assert abs(call_kwargs.get("lr0") - 0.00812) < 0.0001
    assert abs(call_kwargs.get("momentum") - 0.943) < 0.001


# ── Test 2 : appelle YOLO avec epochs et patience corrects ────────────────────

def test_calls_yolo_with_epochs_and_patience(fake_model, hyperparams_file, tmp_path):
    with patch("train_final.YOLO", return_value=fake_model):
        train_final(
            data_yaml="data.yaml",
            base_model="yolo11m.pt",
            hyperparams_path=hyperparams_file,
            epochs=100,
            patience=20,
            project_dir=str(tmp_path),
        )

    call_kwargs = fake_model.train.call_args.kwargs
    assert call_kwargs.get("epochs") == 100
    assert call_kwargs.get("patience") == 20
    assert call_kwargs.get("device") == 0


# ── Test 3 : retourne métriques et model_path → best.pt ──────────────────────

def test_returns_metrics_and_best_pt(fake_model, fake_train_result, hyperparams_file, tmp_path):
    _, best_pt = fake_train_result
    with patch("train_final.YOLO", return_value=fake_model):
        out = train_final(
            data_yaml="data.yaml",
            base_model="yolo11m.pt",
            hyperparams_path=hyperparams_file,
            project_dir=str(tmp_path),
        )

    assert out["model_path"] == best_pt
    assert abs(out["mAP50"]    - 0.92) < 0.001
    assert abs(out["mAP50_95"] - 0.71) < 0.001
    assert abs(out["precision"] - 0.94) < 0.001
    assert abs(out["recall"]   - 0.89) < 0.001
