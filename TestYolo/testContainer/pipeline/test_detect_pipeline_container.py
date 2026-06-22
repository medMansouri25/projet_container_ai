import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(__file__))
from detect_pipeline_container import run_pipeline, save_pipeline_result

BASE       = os.path.dirname(__file__)
IMAGE1     = os.path.join(BASE, "..", "images", "image1.jpg")   # GVTU 208644 9
YOLO_MODEL = os.path.join(BASE, "..", "..", "yolo11m.pt")
LANGUAGES  = ["en", "fr"]
THRESHOLD  = 0.5


# ── Behavior 1 : tracer bullet ─────────────────────────────────────────────

def test_run_pipeline_returns_nonempty_list():
    results = run_pipeline(IMAGE1, YOLO_MODEL, LANGUAGES, THRESHOLD)
    assert isinstance(results, list)
    assert len(results) > 0


# ── Behavior 2 : contrat d'interface ───────────────────────────────────────

def test_run_pipeline_entries_have_required_fields():
    results = run_pipeline(IMAGE1, YOLO_MODEL, LANGUAGES, THRESHOLD)
    for d in results:
        assert "class" in d
        assert "yolo_confidence" in d
        assert "bbox" in d
        assert "ocr_results" in d
        assert isinstance(d["bbox"], list) and len(d["bbox"]) == 4
        assert isinstance(d["ocr_results"], list)


# ── Behavior 3 : fallback full_image toujours présent ──────────────────────

def test_run_pipeline_always_has_full_image_entry():
    results = run_pipeline(IMAGE1, YOLO_MODEL, LANGUAGES, THRESHOLD)
    classes = [d["class"] for d in results]
    assert "full_image" in classes


# ── Behavior 4 : Numéro ISO détecté via la pipeline ────────────────────────

def test_run_pipeline_detects_iso_number():
    results = run_pipeline(IMAGE1, YOLO_MODEL, LANGUAGES, THRESHOLD)
    all_text = " ".join(
        r["text"].upper()
        for d in results
        for r in d["ocr_results"]
    )
    iso_parts = ["GVTU", "208644", "208", "644"]
    assert any(part in all_text for part in iso_parts), (
        f"Numéro ISO non détecté dans la pipeline. Textes : {all_text}"
    )


# ── Behavior 5 : save_pipeline_result crée le fichier de sortie ────────────

def test_save_pipeline_result_creates_file(tmp_path):
    results  = run_pipeline(IMAGE1, YOLO_MODEL, LANGUAGES, THRESHOLD)
    output   = str(tmp_path / "resultat_image1_pipeline.png")
    save_pipeline_result(IMAGE1, results, output)
    assert os.path.exists(output)
    assert os.path.getsize(output) > 0
