import os
import sys
import shutil
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from clean_dataset import clean_dataset


@pytest.fixture
def fake_dataset(tmp_path):
    """
    Crée un mini dataset YOLO avec des orphelins intentionnels :
      train/images : img1.jpg (avec label), img2.jpg (SANS label), img3.jpg (avec label)
      train/labels : img1.txt, img3.txt, orphan.txt (SANS image)
      valid/images : v1.jpg (avec label), v2.jpg (SANS label)
      valid/labels : v1.txt
      test/images  : t1.jpg
      test/labels  : t1.txt
      data.yaml    : nc: 10 (erroné)
    """
    splits = {
        "train": {"images": ["img1.jpg", "img2.jpg", "img3.jpg"], "labels": ["img1.txt", "img3.txt", "orphan.txt"]},
        "valid": {"images": ["v1.jpg", "v2.jpg"],                  "labels": ["v1.txt"]},
        "test":  {"images": ["t1.jpg"],                             "labels": ["t1.txt"]},
    }
    for split, contents in splits.items():
        img_dir = tmp_path / split / "images"
        lbl_dir = tmp_path / split / "labels"
        img_dir.mkdir(parents=True)
        lbl_dir.mkdir(parents=True)
        for f in contents["images"]:
            (img_dir / f).write_bytes(b"fake")
        for f in contents["labels"]:
            (lbl_dir / f).write_text("0 0.5 0.5 1.0 1.0")

    yaml_path = tmp_path / "data.yaml"
    yaml_path.write_text(
        "train: train/images\nval: valid/images\ntest: test/images\n"
        "nc: 10\nnames: ['code','mark2-2','mark3','mark5-1','mark5-2',"
        "'mark6-1','mark8','mark9','type','weight','plaque']\n"
    )
    return str(tmp_path)


# ── Test 1 : supprime images sans label ──────────────────────────────────────

def test_removes_images_without_label(fake_dataset):
    clean_dataset(fake_dataset)
    # img2.jpg n'a pas de label → doit être supprimée
    assert not os.path.exists(os.path.join(fake_dataset, "train", "images", "img2.jpg"))
    # img1.jpg a un label → doit rester
    assert os.path.exists(os.path.join(fake_dataset, "train", "images", "img1.jpg"))


def test_removes_valid_images_without_label(fake_dataset):
    clean_dataset(fake_dataset)
    # v2.jpg n'a pas de label → doit être supprimée
    assert not os.path.exists(os.path.join(fake_dataset, "valid", "images", "v2.jpg"))
    # v1.jpg a un label → doit rester
    assert os.path.exists(os.path.join(fake_dataset, "valid", "images", "v1.jpg"))


# ── Test 2 : supprime labels sans image ──────────────────────────────────────

def test_removes_labels_without_image(fake_dataset):
    clean_dataset(fake_dataset)
    # orphan.txt n'a pas d'image → doit être supprimé
    assert not os.path.exists(os.path.join(fake_dataset, "train", "labels", "orphan.txt"))
    # img1.txt a une image → doit rester
    assert os.path.exists(os.path.join(fake_dataset, "train", "labels", "img1.txt"))


# ── Test 3 : corrige nc dans data.yaml ───────────────────────────────────────

def test_fixes_nc_in_yaml(fake_dataset):
    clean_dataset(fake_dataset)
    content = open(os.path.join(fake_dataset, "data.yaml")).read()
    assert "nc: 11" in content
    assert "nc: 10" not in content


# ── Test 4 : rapport avec comptages corrects ─────────────────────────────────

def test_returns_report_with_correct_counts(fake_dataset):
    report = clean_dataset(fake_dataset)
    assert report["removed_images"] == 2   # img2.jpg + v2.jpg
    assert report["removed_labels"] == 1   # orphan.txt
    assert report["nc_fixed"] is True
