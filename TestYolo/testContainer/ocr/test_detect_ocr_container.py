import os
import pytest
from detect_ocr_container import run_ocr, save_annotated_image

BASE = os.path.dirname(__file__)
IMAGES_DIR = os.path.join(BASE, "..", "images")
IMAGE1 = os.path.join(IMAGES_DIR, "image1.jpg")
CONF_THRESHOLD = 0.3
LANGUAGES = ["en", "fr"]


# --- Behavior 1: chaque résultat a les champs requis ---

def test_run_ocr_returns_expected_fields():
    results = run_ocr(IMAGE1, LANGUAGES, CONF_THRESHOLD)
    assert len(results) > 0, "Aucun texte détecté sur image1.jpg"
    for r in results:
        assert "text" in r
        assert "confidence" in r
        assert "bbox" in r


# --- Behavior 2: seuil de confiance appliqué ---

def test_run_ocr_filters_below_threshold():
    results = run_ocr(IMAGE1, LANGUAGES, CONF_THRESHOLD)
    for r in results:
        assert r["confidence"] >= CONF_THRESHOLD


# --- Behavior 3: Numéro ISO détecté sur image1.jpg (GVTU 208644 9) ---

def test_run_ocr_detects_iso_number():
    results = run_ocr(IMAGE1, LANGUAGES, CONF_THRESHOLD)
    all_text = " ".join(r["text"].upper() for r in results)
    # Le Numéro ISO est GVTU 208644 9 — on vérifie qu'au moins une partie est lue
    iso_parts = ["GVTU", "208644", "208", "644"]
    detected = any(part in all_text for part in iso_parts)
    assert detected, f"Numéro ISO non détecté. Textes trouvés : {all_text}"


# --- Behavior 4: save_annotated_image crée le fichier de sortie ---

def test_save_annotated_image_creates_file(tmp_path):
    output = str(tmp_path / "resultat_image1_OCR.png")
    results = run_ocr(IMAGE1, LANGUAGES, CONF_THRESHOLD)
    save_annotated_image(IMAGE1, results, output)
    assert os.path.exists(output)
    assert os.path.getsize(output) > 0
