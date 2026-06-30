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
    flask_app.train_state["status"] = "idle"
    flask_app.train_state["model_path"] = None
    with flask_app.app.test_client() as c:
        yield c


def test_predict_page_returns_200(client):
    resp = client.get("/predict-page")
    assert resp.status_code == 200


def test_predict_page_has_file_input(client):
    html = client.get("/predict-page").data.decode()
    assert 'type="file"' in html


def test_predict_page_has_canvas(client):
    html = client.get("/predict-page").data.decode()
    assert "<canvas" in html


def test_predict_page_has_detections_zone(client):
    html = client.get("/predict-page").data.decode()
    assert 'id="detections"' in html


def test_predict_page_has_link_back_to_gallery(client):
    html = client.get("/predict-page").data.decode()
    assert 'href="/"' in html
