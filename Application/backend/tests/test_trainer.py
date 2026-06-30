import os
import shutil
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# Ajoute Application/ au path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from trainer import auto_annotate, prepare_raw_dataset, train
from predictor import predict


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_images_dir():
    """Crée un dossier temporaire avec 3 fausses images .jpg."""
    d = tempfile.mkdtemp()
    for name in ["img1.jpg", "img2.jpg", "img3.png"]:
        open(os.path.join(d, name), "wb").close()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def tmp_labels_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def tmp_output_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


# ── Test 1 : auto_annotate crée un .txt par image ────────────────────────────

def test_auto_annotate_creates_label_files(tmp_images_dir, tmp_labels_dir):
    count = auto_annotate(tmp_images_dir, tmp_labels_dir)
    assert count == 3
    for name in ["img1.txt", "img2.txt", "img3.txt"]:
        assert os.path.exists(os.path.join(tmp_labels_dir, name))


def test_auto_annotate_label_content_is_full_image_bbox(tmp_images_dir, tmp_labels_dir):
    auto_annotate(tmp_images_dir, tmp_labels_dir)
    label_path = os.path.join(tmp_labels_dir, "img1.txt")
    content = open(label_path).read().strip()
    assert content == "0 0.5 0.5 1.0 1.0"


# ── Test 2 : prepare_raw_dataset crée la structure YOLO ──────────────────────

def test_prepare_raw_dataset_creates_yolo_structure(tmp_images_dir, tmp_output_dir):
    yaml_path = prepare_raw_dataset(tmp_images_dir, "conteneur", tmp_output_dir)

    assert os.path.exists(yaml_path)
    assert os.path.isdir(os.path.join(tmp_output_dir, "train", "images"))
    assert os.path.isdir(os.path.join(tmp_output_dir, "train", "labels"))


def test_prepare_raw_dataset_yaml_has_correct_class(tmp_images_dir, tmp_output_dir):
    yaml_path = prepare_raw_dataset(tmp_images_dir, "conteneur", tmp_output_dir)
    content = open(yaml_path).read()
    assert "conteneur" in content
    assert "nc: 1" in content


def test_prepare_raw_dataset_copies_images(tmp_images_dir, tmp_output_dir):
    prepare_raw_dataset(tmp_images_dir, "casque", tmp_output_dir)
    copied = os.listdir(os.path.join(tmp_output_dir, "train", "images"))
    assert len(copied) == 3


# ── Test 3 : train appelle ultralytics et retourne les métriques ──────────────

def test_train_returns_structured_result(tmp_output_dir):
    fake_results = MagicMock()
    fake_results.results_dict = {
        "metrics/mAP50(B)": 0.87,
        "metrics/precision(B)": 0.91,
        "metrics/recall(B)": 0.83,
    }
    fake_results.save_dir = os.path.join(tmp_output_dir, "weights")
    os.makedirs(fake_results.save_dir, exist_ok=True)
    best_pt = os.path.join(fake_results.save_dir, "best.pt")
    open(best_pt, "wb").close()

    fake_model = MagicMock()
    fake_model.train.return_value = fake_results

    data_yaml = os.path.join(tmp_output_dir, "data.yaml")
    open(data_yaml, "w").write("nc: 1\nnames: ['conteneur']")

    with patch("trainer.YOLO", return_value=fake_model):
        result = train(
            data_yaml=data_yaml,
            base_model="yolo11m.pt",
            epochs=5,
            project_dir=tmp_output_dir,
        )

    assert result["model_path"] == best_pt
    assert abs(result["mAP50"] - 0.87) < 0.001
    assert abs(result["precision"] - 0.91) < 0.001
    assert abs(result["recall"] - 0.83) < 0.001
