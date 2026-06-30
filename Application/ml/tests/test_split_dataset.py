import os
import sys
import shutil
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from split_dataset import split_dataset


@pytest.fixture
def fake_dataset(tmp_path):
    """
    Crée 100 paires image/label réparties dans train/valid/test
    avec le split existant quelconque (on va le recalculer).
    """
    total = 100
    splits = {"train": 70, "valid": 20, "test": 10}
    idx = 0
    for split, n in splits.items():
        img_dir = tmp_path / split / "images"
        lbl_dir = tmp_path / split / "labels"
        img_dir.mkdir(parents=True)
        lbl_dir.mkdir(parents=True)
        for _ in range(n):
            name = f"img_{idx:04d}"
            Image.new("RGB", (64, 64)).save(str(img_dir / f"{name}.jpg"))
            (lbl_dir / f"{name}.txt").write_text("0 0.5 0.5 1.0 1.0")
            idx += 1

    (tmp_path / "data.yaml").write_text(
        "train: train/images\nval: valid/images\ntest: test/images\n"
        "nc: 1\nnames: ['objet']\n"
    )
    return str(tmp_path)


# ── Test 1 : proportions 70/20/10 respectées ─────────────────────────────────

def test_respects_split_ratios(fake_dataset):
    report = split_dataset(fake_dataset, train_ratio=0.70, valid_ratio=0.20, test_ratio=0.10)
    assert abs(report["train"] - 70) <= 1
    assert abs(report["valid"] - 20) <= 1
    assert abs(report["test"]  - 10) <= 1


# ── Test 2 : aucune image perdue ─────────────────────────────────────────────

def test_no_images_lost(fake_dataset):
    report = split_dataset(fake_dataset)
    assert report["total"] == 100
    assert report["train"] + report["valid"] + report["test"] == 100


# ── Test 3 : chaque image a son label dans le bon split ──────────────────────

def test_each_image_has_matching_label(fake_dataset):
    split_dataset(fake_dataset)
    for split in ("train", "valid", "test"):
        img_dir = os.path.join(fake_dataset, split, "images")
        lbl_dir = os.path.join(fake_dataset, split, "labels")
        imgs = {os.path.splitext(f)[0] for f in os.listdir(img_dir)}
        lbls = {os.path.splitext(f)[0] for f in os.listdir(lbl_dir)}
        assert imgs == lbls, f"[{split}] images et labels désalignés"


# ── Test 4 : data.yaml mis à jour ────────────────────────────────────────────

def test_updates_data_yaml(fake_dataset):
    split_dataset(fake_dataset)
    content = open(os.path.join(fake_dataset, "data.yaml")).read()
    assert "train" in content
    assert "valid" in content or "val" in content
    assert "test"  in content
