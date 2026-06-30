"""
app.py — Serveur Flask (point d'entrée de l'API web)
-----------------------------------------------------
Expose les routes HTTP du pipeline YOLO via une interface web :

  GET  /                  → page galerie (sélection images + lancement entraînement)
  GET  /predict-page      → page prédiction (upload image + affichage bbox)
  POST /upload            → upload d'images dans uploads/
  GET  /gallery           → liste des images uploadées
  GET  /uploads/<name>    → servir une image uploadée
  POST /train             → lancer le fine-tuning YOLO en thread daemon
  GET  /train/status      → état de l'entraînement (polling JSON)
  POST /predict           → inférence sur une image avec le modèle entraîné

Dépendances internes :
  - backend/trainer.py   : logique d'entraînement
  - backend/predictor.py : logique d'inférence

Lancement : python app.py  →  http://localhost:5000
"""

import os
import threading
import tempfile

from flask import Flask, request, jsonify, send_from_directory, render_template

import predictor
import trainer

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
MODELS_FOLDER = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MODELS_FOLDER, exist_ok=True)

app.config.setdefault("UPLOAD_FOLDER", UPLOAD_FOLDER)
app.config.setdefault("MODELS_FOLDER", MODELS_FOLDER)

train_state = {
    "status": "idle",   # idle | running | done | error
    "metrics": {},
    "model_path": None,
    "error": None,
}


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("gallery.html")


@app.route("/predict-page")
def predict_page():
    return render_template("predict.html")


# ── Upload ────────────────────────────────────────────────────────────────────

@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    saved = []
    upload_dir = app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    for f in files:
        dest = os.path.join(upload_dir, f.filename)
        f.save(dest)
        saved.append(f.filename)
    return jsonify({"files": saved})


# ── Gallery ───────────────────────────────────────────────────────────────────

@app.route("/gallery", methods=["GET"])
def gallery():
    upload_dir = app.config["UPLOAD_FOLDER"]
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images = [
        f for f in os.listdir(upload_dir)
        if os.path.splitext(f)[1].lower() in exts
    ] if os.path.isdir(upload_dir) else []
    return jsonify({"images": images})


@app.route("/uploads/<filename>")
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ── Train ─────────────────────────────────────────────────────────────────────

def _run_training(class_name: str, selected: list[str], mode: str):
    train_state["status"] = "running"
    try:
        upload_dir = app.config["UPLOAD_FOLDER"]
        models_dir = app.config["MODELS_FOLDER"]
        base_model = os.path.join(
            os.path.dirname(__file__), "..", "..", "TestYolo", "yolo11m.pt"
        )

        if mode == "dataset":
            data_yaml = os.path.join(
                os.path.dirname(__file__), "..", "data", "data.yaml"
            )
        else:
            tmp_dir = tempfile.mkdtemp()
            import shutil
            for fname in selected:
                src = os.path.join(upload_dir, fname)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(tmp_dir, fname))
            dataset_dir = os.path.join(models_dir, "dataset")
            data_yaml = trainer.prepare_raw_dataset(tmp_dir, class_name, dataset_dir)

        result = trainer.train(
            data_yaml=data_yaml,
            base_model=base_model,
            epochs=50,
            project_dir=models_dir,
        )
        train_state["model_path"] = result["model_path"]
        train_state["metrics"] = result
        train_state["status"] = "done"
    except Exception as e:
        train_state["status"] = "error"
        train_state["error"] = str(e)


@app.route("/train", methods=["POST"])
def train():
    if train_state["status"] == "running":
        return jsonify({"error": "Training already in progress"}), 409

    body = request.get_json() or {}
    class_name = body.get("class_name", "objet")
    selected = body.get("selected", [])
    mode = body.get("mode", "raw")

    t = threading.Thread(
        target=_run_training,
        args=(class_name, selected, mode),
        daemon=True,
    )
    t.start()
    return jsonify({"status": "started"})


@app.route("/train/status", methods=["GET"])
def train_status():
    return jsonify(train_state)


# ── Predict ───────────────────────────────────────────────────────────────────

@app.route("/predict", methods=["POST"])
def predict():
    model_path = train_state.get("model_path")
    if not model_path:
        return jsonify({"error": "No trained model available"}), 400

    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file provided"}), 400

    tmp_path = os.path.join(tempfile.gettempdir(), f.filename)
    f.save(tmp_path)
    detections = predictor.predict(tmp_path, model_path)
    os.remove(tmp_path)
    return jsonify({"detections": detections})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
