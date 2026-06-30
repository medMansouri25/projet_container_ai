import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predict import predict


def make_fake_box(cls_id, cls_name, conf, coords):
    box = MagicMock()
    box.cls = [cls_id]
    box.conf = [conf]
    box.xyxy = [MagicMock()]
    box.xyxy[0].tolist.return_value = coords
    result = MagicMock()
    result.boxes = [box]
    result.names = {cls_id: cls_name}
    return result


@pytest.fixture
def fake_image(tmp_path):
    path = str(tmp_path / "test.jpg")
    Image.new("RGB", (640, 480), color=(100, 150, 200)).save(path)
    return path


@pytest.fixture
def fake_model_with_detections():
    fake_result = make_fake_box(0, "conteneur", 0.91, [10.0, 20.0, 200.0, 300.0])
    model = MagicMock()
    model.return_value = [fake_result]
    return model


@pytest.fixture
def fake_model_no_detections():
    fake_result = MagicMock()
    fake_result.boxes = []
    fake_result.names = {}
    model = MagicMock()
    model.return_value = [fake_result]
    return model


# ── Test 1 : retourne détections avec les bonnes clés ────────────────────────

def test_returns_detections_with_correct_keys(fake_model_with_detections, fake_image, tmp_path):
    with patch("predict.YOLO", return_value=fake_model_with_detections):
        results = predict(fake_image, "best.pt", save_dir=str(tmp_path))

    assert len(results) == 1
    det = results[0]["detections"][0]
    assert det["label"] == "conteneur"
    assert abs(det["confidence"] - 0.91) < 0.001
    assert det["bbox"] == [10, 20, 200, 300]


# ── Test 2 : sauvegarde image annotée ────────────────────────────────────────

def test_saves_annotated_image(fake_model_with_detections, fake_image, tmp_path):
    with patch("predict.YOLO", return_value=fake_model_with_detections):
        results = predict(fake_image, "best.pt", save_dir=str(tmp_path))

    assert results[0]["output_path"] is not None
    assert os.path.exists(results[0]["output_path"])


# ── Test 3 : liste vide si aucune détection ───────────────────────────────────

def test_returns_empty_detections_when_nothing_found(fake_model_no_detections, fake_image, tmp_path):
    with patch("predict.YOLO", return_value=fake_model_no_detections):
        results = predict(fake_image, "best.pt", save_dir=str(tmp_path))

    assert results[0]["detections"] == []


# ── Test 4 : accepte une liste de plusieurs images ───────────────────────────

def test_accepts_multiple_images(fake_model_with_detections, tmp_path):
    img1 = str(tmp_path / "img1.jpg")
    img2 = str(tmp_path / "img2.jpg")
    Image.new("RGB", (320, 240)).save(img1)
    Image.new("RGB", (320, 240)).save(img2)

    with patch("predict.YOLO", return_value=fake_model_with_detections):
        results = predict([img1, img2], "best.pt", save_dir=str(tmp_path))

    assert len(results) == 2
    assert results[0]["image"] == img1
    assert results[1]["image"] == img2
