import os
import pytest
from detect_ocr import run_ocr, save_annotated_image

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "images")
POMME = os.path.join(IMAGES_DIR, "pomme.png")
ORANGE = os.path.join(IMAGES_DIR, "orange.png")
BANANE = os.path.join(IMAGES_DIR, "banane.png")
CONF_THRESHOLD = 0.5
LANGUAGES = ["en", "fr"]


# --- Behavior 1: chaque résultat a les champs requis ---

def test_run_ocr_returns_expected_fields():
    results = run_ocr(POMME, LANGUAGES, CONF_THRESHOLD)
    for r in results:
        assert "text" in r
        assert "confidence" in r
        assert "bbox" in r


# --- Behavior 2: seuil de confiance appliqué ---

def test_run_ocr_filters_below_threshold():
    results = run_ocr(POMME, LANGUAGES, CONF_THRESHOLD)
    for r in results:
        assert r["confidence"] >= CONF_THRESHOLD


# --- Behavior 3: au moins un texte détecté sur pomme.png ---

def test_run_ocr_detects_text_on_pomme():
    results = run_ocr(POMME, LANGUAGES, CONF_THRESHOLD)
    assert len(results) > 0, "Aucun texte détecté sur pomme.png"


# --- Behavior 4: save_annotated_image crée le fichier de sortie ---

def test_save_annotated_image_creates_file(tmp_path):
    output = str(tmp_path / "resultat_pomme_OCR.png")
    results = run_ocr(POMME, LANGUAGES, CONF_THRESHOLD)
    save_annotated_image(POMME, results, output)
    assert os.path.exists(output), "Le fichier annoté n'a pas été créé"
    assert os.path.getsize(output) > 0, "Le fichier annoté est vide"
