import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predictor import predict


def _make_fake_box(label_id: int, label_name: str, conf: float, coords: list):
    box = MagicMock()
    box.cls = [label_id]
    box.conf = [conf]
    box.xyxy = [coords]
    result = MagicMock()
    result.boxes = [box]
    result.names = {label_id: label_name}
    return result


# ── Test 1 : retourne les bonnes clés ────────────────────────────────────────

def test_predict_returns_list_of_dicts_with_correct_keys():
    box = MagicMock()
    box.cls = [0]
    box.conf = [0.92]
    box.xyxy = [MagicMock()]
    box.xyxy[0].tolist.return_value = [10.0, 20.0, 200.0, 300.0]

    fake_result = MagicMock()
    fake_result.boxes = [box]
    fake_result.names = {0: "conteneur"}

    fake_model = MagicMock()
    fake_model.return_value = [fake_result]

    with patch("predictor.YOLO", return_value=fake_model):
        results = predict("image.jpg", "best.pt")

    assert len(results) == 1
    assert set(results[0].keys()) == {"label", "confidence", "bbox"}


# ── Test 2 : liste vide si aucune détection ───────────────────────────────────

def test_predict_returns_empty_list_when_no_detections():
    fake_result = MagicMock()
    fake_result.boxes = []
    fake_model = MagicMock()
    fake_model.return_value = [fake_result]

    with patch("predictor.YOLO", return_value=fake_model):
        results = predict("image.jpg", "best.pt")

    assert results == []


# ── Test 3 : valeurs correctes depuis YOLO ────────────────────────────────────

def test_predict_returns_correct_label_confidence_bbox():
    box = MagicMock()
    box.cls = [2]
    box.conf = [0.87]
    box.xyxy = [MagicMock()]
    box.xyxy[0].tolist.return_value = [5.0, 10.0, 150.0, 250.0]

    fake_result = MagicMock()
    fake_result.boxes = [box]
    fake_result.names = {2: "plaque"}

    fake_model = MagicMock()
    fake_model.return_value = [fake_result]

    with patch("predictor.YOLO", return_value=fake_model):
        results = predict("image.jpg", "best.pt")

    assert results[0]["label"] == "plaque"
    assert abs(results[0]["confidence"] - 0.87) < 0.001
    assert results[0]["bbox"] == [5, 10, 150, 250]
