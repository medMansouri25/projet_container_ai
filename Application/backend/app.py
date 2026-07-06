"""
app.py — SmartContainer_AI : scanner de code BIC (ISO 6346)
------------------------------------------------------------
Routes :
  GET  /                  page scanner (upload drag & drop + caméra)
  POST /scan              image → YOLO (Conteneur) → crop → EasyOCR → result.html
  POST /confirm           enregistre le BIC (corrigé ou non) dans Neon → /history
  GET  /history           liste des scans confirmés
  GET  /uploads/<name>    sert les images uploadées/annotées

Pipeline : backend/pipeline/detector.py (YOLO best_vN) + pipeline/ocr.py (EasyOCR).
Persistance : backend/db.py (PostgreSQL Neon via DATABASE_URL).

Lancement : python app.py  →  http://localhost:5000
"""

import os
import sys
import uuid

from flask import Flask, request, render_template, redirect, url_for, send_from_directory

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pipeline"))

import db
import detector
import ocr

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scan", methods=["POST"])
def scan():
    file = request.files.get("image")
    if not file or not file.filename:
        return render_template("index.html", error="Aucune image recue."), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        return render_template("index.html", error=f"Format non supporte : {ext}"), 400

    name = f"{uuid.uuid4().hex[:12]}{ext}"
    image_path = os.path.join(UPLOAD_FOLDER, name)
    file.save(image_path)

    det = detector.detect_container(image_path, annotated_dir=UPLOAD_FOLDER)

    if not det["found"]:
        return render_template(
            "result.html",
            found=False,
            image_url=url_for("uploads", name=name),
            image_name=name,
        )

    extraction = ocr.extract_bic(det["crop"], vertical=det["vertical"])

    annotated_name = os.path.basename(det["annotated_path"]) if det["annotated_path"] else name
    return render_template(
        "result.html",
        found=True,
        bic=extraction["bic"] or "",
        valid=extraction["valid"],
        corrected=extraction.get("corrected", False),
        ocr_confidence=extraction["confidence"],
        yolo_confidence=det["confidence"],
        vertical=det["vertical"],
        raw_text=" | ".join(extraction["raw"]),
        image_url=url_for("uploads", name=annotated_name),
        image_name=name,
    )


@app.route("/confirm", methods=["POST"])
def confirm():
    bic = (request.form.get("bic") or "").replace(" ", "").upper()
    if not bic:
        return redirect(url_for("index"))
    confidence = request.form.get("ocr_confidence", type=float)
    image_name = request.form.get("image_name")
    image_path = f"uploads/{image_name}" if image_name else None

    db.init_db()
    db.save_scan(bic, confidence, image_path)
    return redirect(url_for("history"))


@app.route("/history")
def history():
    db.init_db()
    scans = db.list_scans(limit=100)
    for s in scans:
        s["valid"] = ocr.validate_check_digit(s["bic"])
        s["image_url"] = (
            url_for("uploads", name=os.path.basename(s["image_path"]))
            if s.get("image_path") else None
        )
    return render_template("history.html", scans=scans)


@app.route("/uploads/<path:name>")
def uploads(name):
    return send_from_directory(UPLOAD_FOLDER, name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
