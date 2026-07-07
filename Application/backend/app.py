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

    # OCR sur la zone NumeroBIC si le modele l'a trouvee (plus precis),
    # sinon repli sur le crop du conteneur entier.
    # roi_vertical = orientation de la ROI reellement lue (pour le badge).
    zone = det.get("bic_zone")
    roi_vertical = det["vertical"]
    if zone is not None:
        extraction = ocr.extract_bic(zone["crop"], vertical=zone["vertical"])
        roi_vertical = zone["vertical"]
        if not extraction["bic"]:
            extraction = ocr.extract_bic(det["crop"], vertical=det["vertical"])
            roi_vertical = det["vertical"]
    else:
        extraction = ocr.extract_bic(det["crop"], vertical=det["vertical"])

    annotated_name = os.path.basename(det["annotated_path"]) if det["annotated_path"] else name
    return render_template(
        "result.html",
        found=True,
        bic=extraction["bic"] or "",
        valid=extraction["valid"],
        corrected=extraction.get("corrected", False),
        bic_zone_found=zone is not None,
        ocr_confidence=extraction["confidence"],
        yolo_confidence=det["confidence"],
        vertical=roi_vertical,
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


@app.route("/scans/<int:scan_id>/delete", methods=["POST"])
def delete_scan(scan_id):
    db.delete_scan(scan_id)
    return redirect(url_for("history"))


@app.route("/scans/<int:scan_id>/update", methods=["POST"])
def update_scan(scan_id):
    bic = (request.form.get("bic") or "").replace(" ", "").upper()
    if bic:
        db.update_scan(scan_id, bic)
    return redirect(url_for("history"))


@app.route("/dashboard")
def dashboard():
    db.init_db()
    scans = db.list_scans(limit=1000)
    stats = _compute_stats(scans)
    return render_template("dashboard.html", **stats)


def _compute_stats(scans: list) -> dict:
    """KPIs et séries pour le dashboard (calculés côté Python)."""
    from datetime import date, timedelta
    from collections import Counter

    total = len(scans)
    valid_count = sum(1 for s in scans if ocr.validate_check_digit(s["bic"]))
    confs = [s["ocr_confidence"] for s in scans if s.get("ocr_confidence")]
    avg_conf = sum(confs) / len(confs) if confs else 0.0
    today = date.today()
    today_count = sum(1 for s in scans if s["created_at"].date() == today)

    # scans par jour (14 derniers jours)
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    per_day_counts = Counter(s["created_at"].date() for s in scans)
    max_day = max((per_day_counts.get(d, 0) for d in days), default=0) or 1
    per_day = [{
        "label": d.strftime("%d/%m"),
        "count": per_day_counts.get(d, 0),
        "pct": round(per_day_counts.get(d, 0) / max_day * 100),
    } for d in days]

    # top codes proprietaires (4 premieres lettres)
    owners = Counter(s["bic"][:4] for s in scans if len(s["bic"]) >= 4)
    top = owners.most_common(5)
    max_owner = top[0][1] if top else 1
    top_owners = [{"code": c, "count": n, "pct": round(n / max_owner * 100)}
                  for c, n in top]

    valid_pct = round(valid_count / total * 100) if total else 0
    return {
        "total": total,
        "valid_count": valid_count,
        "valid_pct": valid_pct,
        "invalid_count": total - valid_count,
        "avg_conf_pct": round(avg_conf * 100),
        "today_count": today_count,
        "per_day": per_day,
        "top_owners": top_owners,
    }


@app.route("/uploads/<path:name>")
def uploads(name):
    return send_from_directory(UPLOAD_FOLDER, name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
