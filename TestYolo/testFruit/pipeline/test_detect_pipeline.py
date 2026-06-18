import os
import pytest
from detect_pipeline import run_pipeline, save_pipeline_result

BASE = os.path.dirname(__file__)
POMME = os.path.join(BASE, "..", "images", "pomme.png")
YOLO_MODEL = os.path.join(BASE, "..", "..", "yolo11m.pt")
LANGUAGES = ["en", "fr"]
OCR_THRESHOLD = 0.5


# --- Behavior 1: chaque détection a les champs requis ---

def test_pipeline_detection_has_required_fields():
    detections = run_pipeline(POMME, YOLO_MODEL, LANGUAGES, OCR_THRESHOLD)
    assert len(detections) > 0, "Aucune detection YOLO sur pomme.png"
    for d in detections:
        assert "class" in d
        assert "yolo_confidence" in d
        assert "bbox" in d
        assert "ocr_results" in d


# --- Behavior 2: ocr_results est une liste ---

def test_pipeline_ocr_results_is_list():
    detections = run_pipeline(POMME, YOLO_MODEL, LANGUAGES, OCR_THRESHOLD)
    for d in detections:
        assert isinstance(d["ocr_results"], list)


# --- Behavior 3: chaque ocr_result a text, confidence, bbox ---

def test_pipeline_ocr_result_fields():
    detections = run_pipeline(POMME, YOLO_MODEL, LANGUAGES, OCR_THRESHOLD)
    for d in detections:
        for r in d["ocr_results"]:
            assert "text" in r
            assert "confidence" in r
            assert "bbox" in r


# --- Behavior 4: save_pipeline_result crée le fichier de sortie ---

def test_save_pipeline_result_creates_file(tmp_path):
    output = str(tmp_path / "resultat_pomme_pipeline.png")
    detections = run_pipeline(POMME, YOLO_MODEL, LANGUAGES, OCR_THRESHOLD)
    save_pipeline_result(POMME, detections, output)
    assert os.path.exists(output)
    assert os.path.getsize(output) > 0
