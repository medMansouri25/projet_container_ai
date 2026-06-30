import io
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as flask_app


@pytest.fixture
def client(tmp_path):
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    flask_app.app.config["MODELS_FOLDER"] = str(tmp_path / "models")
    os.makedirs(flask_app.app.config["UPLOAD_FOLDER"], exist_ok=True)
    flask_app.train_state["status"] = "idle"
    flask_app.train_state["model_path"] = None
    with flask_app.app.test_client() as c:
        yield c


# ── Test 1 : GET / sert la page galerie ──────────────────────────────────────

def test_gallery_page_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_gallery_page_contains_file_input(client):
    resp = client.get("/")
    html = resp.data.decode()
    assert 'type="file"' in html


def test_gallery_page_contains_class_name_input(client):
    resp = client.get("/")
    html = resp.data.decode()
    assert 'id="class-name"' in html or 'name="class_name"' in html


def test_gallery_page_contains_train_button(client):
    resp = client.get("/")
    html = resp.data.decode()
    assert "train" in html.lower() or "entraîner" in html.lower()


def test_gallery_page_contains_image_grid(client):
    resp = client.get("/")
    html = resp.data.decode()
    assert 'id="image-grid"' in html


# ── Test 2 : lien vers /predict page ─────────────────────────────────────────

def test_gallery_page_has_link_to_predict(client):
    resp = client.get("/")
    html = resp.data.decode()
    assert "/predict-page" in html or "predict" in html.lower()
