import os
import sys
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analyze_dataset import analyze_dataset


@pytest.fixture
def fake_dataset(tmp_path):
    """
    train : 3 images (img1 avec label, img2 sans label, img3 avec label)
            2 labels (img1, img3) + 1 orphan label (orphan)
            img1 : 2 bbox classe 0, img3 : 1 bbox classe 1
    valid : 2 images (v1 avec label, v2 sans label), 1 label (v1)
    test  : 1 image + 1 label (t1)
    data.yaml : nc=2, names=[alpha, beta]
    """
    def make_img(path, w, h):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Image.new("RGB", (w, h)).save(path)

    def make_label(path, lines):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write("\n".join(lines))

    # train
    make_img(str(tmp_path / "train" / "images" / "img1.jpg"), 640, 480)
    make_img(str(tmp_path / "train" / "images" / "img2.jpg"), 320, 240)
    make_img(str(tmp_path / "train" / "images" / "img3.jpg"), 800, 600)
    make_label(str(tmp_path / "train" / "labels" / "img1.txt"), ["0 0.5 0.5 0.9 0.9", "0 0.2 0.2 0.3 0.3"])
    make_label(str(tmp_path / "train" / "labels" / "img3.txt"), ["1 0.5 0.5 0.8 0.8"])
    make_label(str(tmp_path / "train" / "labels" / "orphan.txt"), ["0 0.1 0.1 0.2 0.2"])

    # valid
    make_img(str(tmp_path / "valid" / "images" / "v1.jpg"), 640, 640)
    make_img(str(tmp_path / "valid" / "images" / "v2.jpg"), 640, 640)
    make_label(str(tmp_path / "valid" / "labels" / "v1.txt"), ["1 0.5 0.5 0.4 0.4"])

    # test
    make_img(str(tmp_path / "test" / "images" / "t1.jpg"), 1280, 720)
    make_label(str(tmp_path / "test" / "labels" / "t1.txt"), ["0 0.5 0.5 0.6 0.6"])

    # data.yaml
    (tmp_path / "data.yaml").write_text(
        "nc: 2\nnames: ['alpha', 'beta']\n"
        "train: train/images\nval: valid/images\ntest: test/images\n"
    )
    return str(tmp_path)


@pytest.fixture
def dataset_with_invalid_index(tmp_path):
    """Label avec un indice de classe 5 alors que nc=2."""
    os.makedirs(str(tmp_path / "train" / "images"), exist_ok=True)
    os.makedirs(str(tmp_path / "train" / "labels"), exist_ok=True)
    Image.new("RGB", (640, 480)).save(str(tmp_path / "train" / "images" / "bad.jpg"))
    open(str(tmp_path / "train" / "labels" / "bad.txt"), "w").write("5 0.5 0.5 0.9 0.9")
    (tmp_path / "data.yaml").write_text("nc: 2\nnames: ['alpha','beta']\ntrain: train/images\n")
    return str(tmp_path)


# ── Test 1 : compte images et labels par split ───────────────────────────────

def test_counts_images_and_labels_per_split(fake_dataset):
    report = analyze_dataset(fake_dataset)
    assert report["splits"]["train"]["images"] == 3
    assert report["splits"]["train"]["labels"] == 3   # img1, img3, orphan
    assert report["splits"]["valid"]["images"] == 2
    assert report["splits"]["valid"]["labels"] == 1
    assert report["splits"]["test"]["images"] == 1
    assert report["splits"]["test"]["labels"] == 1


# ── Test 2 : détecte orphelins ───────────────────────────────────────────────

def test_detects_images_without_label(fake_dataset):
    report = analyze_dataset(fake_dataset)
    assert report["splits"]["train"]["no_label"] == 1   # img2
    assert report["splits"]["valid"]["no_label"] == 1   # v2


def test_detects_labels_without_image(fake_dataset):
    report = analyze_dataset(fake_dataset)
    assert report["splits"]["train"]["no_image"] == 1   # orphan


# ── Test 3 : compte bbox par classe ─────────────────────────────────────────

def test_counts_bbox_per_class(fake_dataset):
    report = analyze_dataset(fake_dataset)
    # train : classe 0 → 2 (img1) + 1 (orphan) = 3 ; classe 1 → 1 (img3)
    # valid : classe 1 → 1 ; test : classe 0 → 1
    assert report["classes"][0]["bbox_count"] == 4   # 3 train + 1 test
    assert report["classes"][1]["bbox_count"] == 2   # 1 train + 1 valid
    assert report["classes"][0]["name"] == "alpha"
    assert report["classes"][1]["name"] == "beta"


# ── Test 4 : détecte indices invalides ──────────────────────────────────────

def test_detects_invalid_class_indices(dataset_with_invalid_index):
    report = analyze_dataset(dataset_with_invalid_index)
    assert report["nc_valid"] is False
    assert len(report["invalid_indices"]) == 1
    assert report["invalid_indices"][0]["index"] == 5


def test_valid_indices_pass(fake_dataset):
    report = analyze_dataset(fake_dataset)
    assert report["nc_valid"] is True
    assert report["invalid_indices"] == []


# ── Test 5 : tailles d'images ────────────────────────────────────────────────

def test_reports_image_sizes(fake_dataset):
    report = analyze_dataset(fake_dataset)
    sizes = report["image_sizes"]
    assert sizes["min_w"] == 320
    assert sizes["max_w"] == 1280
    assert sizes["min_h"] == 240
    assert sizes["max_h"] == 720
    assert sizes["total"] == 6   # 3 train + 2 valid + 1 test
