import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tune import tune


FAKE_BEST_HYPERPARAMS = {
    "lr0": 0.00812,
    "lrf": 0.01234,
    "momentum": 0.943,
    "weight_decay": 0.0004,
    "warmup_epochs": 2.5,
    "box": 7.5,
    "cls": 0.5,
    "hsv_h": 0.015,
    "hsv_s": 0.7,
    "hsv_v": 0.4,
    "degrees": 0.0,
    "translate": 0.1,
    "scale": 0.5,
    "mosaic": 1.0,
}


@pytest.fixture
def fake_model():
    model = MagicMock()
    model.tune.return_value = FAKE_BEST_HYPERPARAMS
    return model


# ── Test 1 : appelle tune() avec les bons paramètres ─────────────────────────

def test_calls_tune_with_correct_params(fake_model, tmp_path):
    with patch("tune.YOLO", return_value=fake_model):
        tune(
            model_path="best.pt",
            data_yaml="data.yaml",
            iterations=30,
            epochs=30,
            device=0,
            project_dir=str(tmp_path),
        )

    call_kwargs = fake_model.tune.call_args.kwargs
    assert call_kwargs.get("iterations") == 30
    assert call_kwargs.get("epochs") == 30
    assert call_kwargs.get("device") == 0


# ── Test 2 : sauvegarde les hyperparams en JSON ───────────────────────────────

def test_saves_best_hyperparams_to_json(fake_model, tmp_path):
    with patch("tune.YOLO", return_value=fake_model):
        out = tune("best.pt", "data.yaml", project_dir=str(tmp_path))

    assert "config_path" in out
    assert os.path.exists(out["config_path"])
    saved = json.load(open(out["config_path"]))
    assert abs(saved["lr0"] - 0.00812) < 0.0001
    assert abs(saved["momentum"] - 0.943) < 0.001


# ── Test 3 : retourne best_hyperparams et config_path ────────────────────────

def test_returns_best_hyperparams_and_config_path(fake_model, tmp_path):
    with patch("tune.YOLO", return_value=fake_model):
        out = tune("best.pt", "data.yaml", project_dir=str(tmp_path))

    assert "best_hyperparams" in out
    assert "config_path" in out
    assert out["best_hyperparams"]["momentum"] == FAKE_BEST_HYPERPARAMS["momentum"]
    assert out["config_path"].endswith(".json")
