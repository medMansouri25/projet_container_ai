"""
app.py — SmartContainer_AI : scanner de code BIC (ISO 6346)
------------------------------------------------------------
Routes HTML (app servie par le VPS) :
  GET  /                  page scanner (upload drag & drop + caméra)
  POST /scan              image → YOLO (Conteneur) → crop → EasyOCR → result.html
  POST /confirm           enregistre le BIC (corrigé ou non) dans Neon → /history
  GET  /history           liste des scans confirmés
  GET  /dashboard         KPIs et graphiques
  GET  /uploads/<name>    sert les images uploadées/annotées

API JSON (consommée par le front statique déployé sur Vercel) :
  POST /api/scan          multipart image → résultat du pipeline en JSON
  POST /api/confirm       {bic, ocr_confidence, image_name} → {id}
  GET  /api/history       liste des scans en JSON
  GET  /api/dashboard     statistiques en JSON
  POST /api/scans/<id>/delete | /update

Pipeline : backend/pipeline/detector.py (YOLO best_vN) + pipeline/ocr.py (EasyOCR).
Persistance : backend/db.py (PostgreSQL Neon via DATABASE_URL).

Lancement : python app.py  →  http://localhost:5000
"""

import os
import sys
import uuid

from flask import (Flask, request, render_template, redirect, url_for,
                   send_from_directory, jsonify)
from werkzeug.middleware.proxy_fix import ProxyFix

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pipeline"))

import db
import detector
import ocr
import char_reader
import plaque

app = Flask(__name__)
# Derriere le tunnel Cloudflare : respecter Host / X-Forwarded-Proto pour
# que les URLs absolues (_external=True) pointent vers le domaine public
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


@app.after_request
def cors(response):
    """CORS ouvert sur l'API et les modèles ONNX (front statique Vercel)."""
    if (request.path.startswith("/api/")
            or request.path.startswith("/uploads/")
            or request.path.startswith("/models/")):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

MAX_IMAGE_SIDE = 1600  # les photos 12 MP des telephones ralentissent tout


def _limit_image_size(image_path: str) -> None:
    """Redimensionne l'image sur disque si son grand cote depasse la limite.
    YOLO et l'OCR n'ont pas besoin de plus, et chaque etape en profite."""
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return
    h, w = img.shape[:2]
    big = max(h, w)
    if big > MAX_IMAGE_SIDE:
        s = MAX_IMAGE_SIDE / big
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        cv2.imwrite(image_path, img)


def _warmup():
    """Charge les modeles (YOLO x2 + EasyOCR) au demarrage du conteneur :
    le premier scan d'un utilisateur ne paie plus ~60s de chargement."""
    try:
        import numpy as np
        import cv2
        img = np.zeros((320, 320, 3), dtype=np.uint8)
        p = os.path.join(UPLOAD_FOLDER, "_warmup.jpg")
        cv2.imwrite(p, img)
        detector.detect_container(p)
        ocr._get_reader().readtext(img)
        os.remove(p)
        print("Warmup termine : modeles charges en memoire")
    except Exception as e:
        print(f"Warmup echoue (non bloquant) : {e}")


import threading
threading.Thread(target=_warmup, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


def _extract_bic(crop, vertical, is_zone):
    """
    Lit le code BIC d'un crop. Moteur principal : EasyOCR (éprouvé, robuste
    sur les codes conteneurs dégradés). Secours : YOLO caractère (architecture
    du tuteur) — sollicité uniquement si EasyOCR ne lit rien, ce qui évite
    tout risque de faux code (le char ne s'impose jamais à EasyOCR).
    Le champ "engine" indique quel moteur a fourni le résultat.
    """
    res = ocr.extract_bic(crop, vertical=vertical, is_zone=is_zone)
    res["engine"] = "easyocr"
    if res["bic"]:
        return res

    char_model = detector._get_char_model(detector.DEFAULT_MODELS_DIR)
    if char_model is not None:
        c = char_reader.read_bic(crop, model=char_model, vertical=vertical)
        if c["bic"]:
            c["engine"] = "char"
            return c
    return res


def _run_scan(file, external: bool = False):
    """
    Pipeline complet sur un fichier uploadé. Retourne (payload, erreur).
    payload est un dict commun aux rendus HTML et JSON ;
    external=True génère des URLs absolues (front hébergé ailleurs).
    """
    if not file or not file.filename:
        return None, "Aucune image recue."
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        return None, f"Format non supporte : {ext}"

    name = f"{uuid.uuid4().hex[:12]}{ext}"
    image_path = os.path.join(UPLOAD_FOLDER, name)
    file.save(image_path)
    _limit_image_size(image_path)

    det = detector.detect_container(image_path, annotated_dir=UPLOAD_FOLDER)
    zone = det.get("bic_zone")

    def img_url(n):
        return url_for("uploads", name=n, _external=external)

    # Abandon uniquement si NI conteneur NI zone BIC : un gros plan sur le
    # marquage (conteneur hors cadre) reste lisible via la zone seule.
    if not det["found"] and zone is None:
        return {"found": False, "image_url": img_url(name),
                "image_name": name}, None

    # Lecture : YOLO caractere (architecture tuteur) en principal, EasyOCR
    # en secours. roi_vertical = orientation de la ROI reellement lue.
    roi_vertical = det["vertical"]
    if zone is not None:
        extraction = _extract_bic(zone["crop"], zone["vertical"], is_zone=True)
        roi_vertical = zone["vertical"]
        if not extraction["bic"] and det["found"]:
            extraction = _extract_bic(det["crop"], det["vertical"], is_zone=False)
            roi_vertical = det["vertical"]
    else:
        extraction = _extract_bic(det["crop"], det["vertical"], is_zone=False)

    annotated_name = os.path.basename(det["annotated_path"]) if det["annotated_path"] else name
    return {
        "found": True,
        "container_found": det["found"],
        "bic": extraction["bic"] or "",
        "valid": extraction["valid"],
        "corrected": extraction.get("corrected", False),
        "bic_zone_found": zone is not None,
        "ocr_confidence": extraction["confidence"],
        "yolo_confidence": det["confidence"],
        "vertical": roi_vertical,
        "raw_text": " | ".join(extraction["raw"]),
        "image_url": img_url(annotated_name),
        "image_name": name,
    }, None


def _run_scan_plaque(file, external: bool = False):
    """
    Pipeline plaque : image → YOLO (zone plaque) → EasyOCR arabe → format
    marocain. Miroir de _run_scan pour le service Plaque. Retourne
    (payload, erreur). Le payload est commun HTML/JSON.
    """
    if not file or not file.filename:
        return None, "Aucune image recue."
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        return None, f"Format non supporte : {ext}"

    name = f"{uuid.uuid4().hex[:12]}{ext}"
    image_path = os.path.join(UPLOAD_FOLDER, name)
    file.save(image_path)
    _limit_image_size(image_path)

    det = detector.detect_plaque(image_path, annotated_dir=UPLOAD_FOLDER)

    def img_url(n):
        return url_for("uploads", name=n, _external=external)

    if not det["found"]:
        # modele absent (entrainement non lance) ou aucune plaque detectee
        reason = ("modele plaque absent : lancez trainImmat.bat"
                  if det["model_path"] is None else "aucune plaque detectee")
        return {"found": False, "reason": reason,
                "image_url": img_url(name), "image_name": name}, None

    extraction = plaque.extract_plaque(det["crop"])
    annotated_name = (os.path.basename(det["annotated_path"])
                      if det["annotated_path"] else name)
    return {
        "found": True,
        "plaque": extraction["plaque"] or "",
        "valid": extraction["valid"],
        "left": extraction["left"],
        "letter": extraction["letter"],
        "right": extraction["right"],
        "ocr_confidence": extraction["confidence"],
        "yolo_confidence": det["confidence"],
        "raw_text": " | ".join(extraction["raw"]),
        "image_url": img_url(annotated_name),
        "image_name": name,
    }, None


@app.route("/api/scan-plaque", methods=["POST"])
def api_scan_plaque():
    payload, error = _run_scan_plaque(request.files.get("image"), external=True)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(payload)


@app.route("/scan", methods=["POST"])
def scan():
    payload, error = _run_scan(request.files.get("image"))
    if error:
        return render_template("index.html", error=error), 400
    return render_template("result.html", **payload)


@app.route("/api/scan", methods=["POST"])
def api_scan():
    payload, error = _run_scan(request.files.get("image"), external=True)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(payload)


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


# ── API JSON (front statique Vercel) ─────────────────────────────────────


@app.route("/api/confirm", methods=["POST"])
def api_confirm():
    data = request.get_json(silent=True) or request.form
    bic = (data.get("bic") or "").replace(" ", "").upper()
    if not bic:
        return jsonify({"error": "bic manquant"}), 400
    confidence = data.get("ocr_confidence")
    confidence = float(confidence) if confidence not in (None, "") else None
    image_name = data.get("image_name")
    image_path = f"uploads/{image_name}" if image_name else None
    db.init_db()
    scan_id = db.save_scan(bic, confidence, image_path)
    return jsonify({"id": scan_id, "bic": bic})


@app.route("/api/history")
def api_history():
    db.init_db()
    scans = db.list_scans(limit=100)
    for s in scans:
        s["valid"] = ocr.validate_check_digit(s["bic"])
        s["image_url"] = (
            url_for("uploads", name=os.path.basename(s["image_path"]),
                    _external=True)
            if s.get("image_path") else None
        )
        s["created_at"] = s["created_at"].isoformat()
    return jsonify({"scans": scans})


@app.route("/api/dashboard")
def api_dashboard():
    db.init_db()
    stats = _compute_stats(db.list_scans(limit=1000))
    try:
        db.init_dossier_db()
        stats["dossiers"] = db.dossier_stats()
    except Exception as e:
        print(f"[dashboard] dossier_stats error: {e}")
        stats["dossiers"] = {"total": 0, "en_attente": 0, "valide": 0,
                             "abandonne": 0, "complets": 0}
    return jsonify(stats)


@app.route("/api/ocr-crop", methods=["POST", "OPTIONS"])
def api_ocr_crop():
    """Reçoit un crop BIC extrait par le client (ONNX local) et renvoie uniquement
    l'OCR. Réduit la charge VPS : seul ~5% de l'image transite sur le réseau.
    Essaie horizontal puis vertical pour couvrir les deux orientations."""
    if request.method == "OPTIONS":
        return "", 204
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "image manquante"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        ext = ".jpg"
    name = f"{uuid.uuid4().hex[:12]}{ext}"
    image_path = os.path.join(UPLOAD_FOLDER, name)
    file.save(image_path)

    import cv2
    crop = cv2.imread(image_path)
    if crop is None:
        return jsonify({"error": "image illisible"}), 400

    # Essayer horizontal d'abord, puis vertical si rien trouvé
    res = ocr.extract_bic(crop, vertical=False, is_zone=True)
    if not res["bic"]:
        res_v = ocr.extract_bic(crop, vertical=True, is_zone=True)
        if res_v["bic"]:
            res = res_v

    return jsonify({
        "bic": res["bic"] or "",
        "valid": res["valid"],
        "ocr_confidence": res["confidence"],
        "raw_text": " | ".join(res["raw"]),
        "image_name": name,
        "image_url": url_for("uploads", name=name, _external=True),
    })


@app.route("/api/ocr-plaque-crop", methods=["POST", "OPTIONS"])
def api_ocr_plaque_crop():
    """Reçoit un crop plaque extrait par le client (ONNX local) et renvoie
    uniquement l'OCR. Miroir de /api/ocr-crop pour les plaques marocaines."""
    if request.method == "OPTIONS":
        return "", 204
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "image manquante"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        ext = ".jpg"
    name = f"{uuid.uuid4().hex[:12]}{ext}"
    image_path = os.path.join(UPLOAD_FOLDER, name)
    file.save(image_path)

    import cv2
    crop = cv2.imread(image_path)
    if crop is None:
        return jsonify({"error": "image illisible"}), 400

    extraction = plaque.extract_plaque(crop)
    return jsonify({
        "plaque":         extraction.get("plaque") or "",
        "valid":          extraction.get("valid", False),
        "ocr_confidence": extraction.get("confidence"),
        "raw_text":       " | ".join(extraction.get("raw", [])),
        "image_name":     name,
        "image_url":      url_for("uploads", name=name, _external=True),
    })


@app.route("/api/scans/<int:scan_id>/delete", methods=["POST"])
def api_delete_scan(scan_id):
    db.delete_scan(scan_id)
    return jsonify({"deleted": scan_id})


@app.route("/api/scans/<int:scan_id>/update", methods=["POST"])
def api_update_scan(scan_id):
    data = request.get_json(silent=True) or request.form
    bic = (data.get("bic") or "").replace(" ", "").upper()
    if not bic:
        return jsonify({"error": "bic manquant"}), 400
    db.update_scan(scan_id, bic)
    return jsonify({"updated": scan_id, "bic": bic})


# ── Dossier de passage (V2 — orchestrateur métier) ───────────────────────
# Ces endpoints persistent des valeurs DÉJÀ confirmées par l'agent (les
# propositions viennent de /api/scan et /api/scan-plaque). Les services IA
# restent séparés du métier (I3 + prépare le split microservices).


@app.route("/api/dossiers", methods=["POST"])
def api_create_dossier():
    """Ouvre un passage (statut en_attente). Corps : {source, voie?}."""
    data = request.get_json(silent=True) or {}
    db.init_dossier_db()
    dossier_id = db.create_dossier(data.get("source"), data.get("voie"))
    return jsonify({"id": dossier_id, "statut": "en_attente"}), 201


@app.route("/api/dossiers/<int:dossier_id>/conteneur", methods=["POST"])
def api_dossier_conteneur(dossier_id):
    """Rattache le conteneur confirmé + garde la preuve brute (Detection)."""
    data = request.get_json(silent=True) or request.form
    code_iso = (data.get("code_iso") or "").replace(" ", "").upper()
    if not code_iso:
        return jsonify({"error": "code_iso manquant"}), 400
    db.set_conteneur(dossier_id, code_iso, data.get("dimension"))
    db.add_detection(dossier_id, "conteneur", code_iso,
                     confidence=_as_float(data.get("ocr_confidence")),
                     bbox=data.get("bbox"), image_path=_image_path(data.get("image_name")))
    return jsonify({"dossier_id": dossier_id, "conteneur": code_iso})


@app.route("/api/dossiers/<int:dossier_id>/plaque", methods=["POST"])
def api_dossier_plaque(dossier_id):
    """Rattache la plaque confirmée + garde la preuve brute (Detection)."""
    data = request.get_json(silent=True) or request.form
    immat = (data.get("immatriculation") or "").strip()
    if not immat:
        return jsonify({"error": "immatriculation manquante"}), 400
    db.set_camion(dossier_id, immat)
    db.add_detection(dossier_id, "plaque", immat,
                     confidence=_as_float(data.get("ocr_confidence")),
                     bbox=data.get("bbox"), image_path=_image_path(data.get("image_name")))
    return jsonify({"dossier_id": dossier_id, "immatriculation": immat})


@app.route("/api/dossiers/<int:dossier_id>/validate", methods=["POST"])
def api_dossier_validate(dossier_id):
    """Valide un dossier. 400 si vide (règle métier dans db.validate_dossier)."""
    if not db.validate_dossier(dossier_id):
        return jsonify({"error": "dossier vide : au moins une entité requise"}), 400
    return jsonify({"dossier_id": dossier_id, "statut": "valide"})


@app.route("/api/dossiers/<int:dossier_id>/abandon", methods=["POST"])
def api_dossier_abandon(dossier_id):
    db.abandon_dossier(dossier_id)
    return jsonify({"dossier_id": dossier_id, "statut": "abandonne"})


@app.route("/api/dossiers/<int:dossier_id>", methods=["DELETE"])
def api_delete_dossier(dossier_id):
    """Supprime définitivement un dossier et toutes ses entités (CASCADE)."""
    db.init_dossier_db()
    db.delete_dossier(dossier_id)
    return jsonify({"deleted": dossier_id})


@app.route("/api/dossiers/<int:dossier_id>/update", methods=["POST"])
def api_update_dossier(dossier_id):
    """Met à jour le BIC (code_iso) et/ou l'immatriculation d'un dossier."""
    db.init_dossier_db()
    data = request.get_json(silent=True) or {}
    if "code_iso" in data and data["code_iso"]:
        db.set_conteneur(dossier_id, data["code_iso"].strip().upper())
    if "immatriculation" in data and data["immatriculation"]:
        db.set_camion(dossier_id, data["immatriculation"].strip())
    dossier = db.get_dossier(dossier_id)
    if dossier:
        for k in ("created_at", "validated_at"):
            if dossier.get(k):
                dossier[k] = dossier[k].isoformat()
    return jsonify({"dossier_id": dossier_id, "dossier": dossier})


@app.route("/api/dossiers", methods=["GET"])
def api_list_dossiers():
    """Liste les dossiers, filtrable par ?statut= et ?include_entities=1 (avec entités)."""
    statut = request.args.get("statut")
    include_entities = request.args.get("include_entities") in ("1", "true")
    db.init_dossier_db()
    if include_entities:
        dossiers = db.list_dossiers_with_entities(statut=statut, limit=100)
    else:
        dossiers = db.list_dossiers(statut=statut, limit=100)
    for d in dossiers:
        for k in ("created_at", "validated_at"):
            if d.get(k) is not None and hasattr(d[k], "isoformat"):
                d[k] = d[k].isoformat()
    return jsonify({"dossiers": dossiers})


@app.route("/api/dossiers/<int:dossier_id>", methods=["GET"])
def api_get_dossier(dossier_id):
    dossier = db.get_dossier(dossier_id)
    if dossier is None:
        return jsonify({"error": "dossier introuvable"}), 404
    for k in ("created_at", "validated_at"):
        if dossier.get(k) is not None and hasattr(dossier[k], "isoformat"):
            dossier[k] = dossier[k].isoformat()
    return jsonify(dossier)


def _as_float(v):
    return float(v) if v not in (None, "") else None


def _image_path(image_name):
    return f"uploads/{image_name}" if image_name else None


def _serialize_dossier(d: dict) -> dict:
    """Convertit les timestamps en ISO string pour la sérialisation JSON."""
    if d is None:
        return d
    for k in ("created_at", "validated_at"):
        if d.get(k) is not None and hasattr(d[k], "isoformat"):
            d[k] = d[k].isoformat()
    for det in d.get("detections", []):
        if det.get("timestamp") and hasattr(det["timestamp"], "isoformat"):
            det["timestamp"] = det["timestamp"].isoformat()
    return d


@app.route("/api/passage/confirmer", methods=["POST"])
def api_passage_confirmer():
    """Endpoint de confort Mission 6 : confirme une entité dans un dossier
    en un seul appel.  Corps : {target, valeur, dossier_id?, confidence?}
    - Si dossier_id absent → crée un dossier (source='capture').
    - Rattache l'entité (conteneur ou camion) au dossier.
    - Retourne {dossier_id, dossier} (dossier agrégé complet).
    """
    db.init_dossier_db()
    data = request.get_json(silent=True) or {}
    target = data.get("target")
    valeur = (data.get("valeur") or "").strip()
    dossier_id = data.get("dossier_id")
    confidence = _as_float(data.get("confidence"))

    if target not in ("conteneur", "plaque"):
        return jsonify({"error": "target invalide : conteneur ou plaque"}), 400
    if not valeur:
        return jsonify({"error": "valeur manquante"}), 400

    if not dossier_id:
        dossier_id = db.create_dossier(source="capture")

    if target == "conteneur":
        code = valeur.replace(" ", "").upper()
        db.set_conteneur(dossier_id, code)
        db.add_detection(dossier_id, "conteneur", code, confidence)
    else:
        db.set_camion(dossier_id, valeur)
        db.add_detection(dossier_id, "plaque", valeur, confidence)

    dossier = db.get_dossier(dossier_id)
    return jsonify({"dossier_id": dossier_id, "dossier": _serialize_dossier(dossier)})


def _compute_stats(scans: list) -> dict:
    """KPIs et séries pour le dashboard (calculés côté Python)."""
    from datetime import date, timedelta, datetime, timezone
    MOROCCO = timezone(timedelta(hours=1))
    from collections import Counter

    total = len(scans)
    valid_count = sum(1 for s in scans if ocr.validate_check_digit(s["bic"]))
    confs = [s["ocr_confidence"] for s in scans if s.get("ocr_confidence")]
    avg_conf = sum(confs) / len(confs) if confs else 0.0
    today = datetime.now(MOROCCO).date()
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


# Modèles ONNX pour le navigateur (onnxruntime-web).
# conteneur.onnx → conteneur_browser/best_v2.onnx (1 classe caisse conteneur, mAP50 85.7%)
# plaque.onnx    → plaque/best_v1.onnx (1 classe immatriculation)
# bic.onnx       → bic_browser/best_v1.onnx (1 classe NumeroBIC)
_ONNX_MAP = {
    "conteneur.onnx": os.path.join(
        os.path.dirname(__file__), "..", "..", "Application", "models", "conteneur_browser", "best_v2.onnx"),
    "plaque.onnx": os.path.join(
        os.path.dirname(__file__), "..", "..", "Application", "models", "plaque", "best_v1.onnx"),
    "bic.onnx": os.path.join(
        os.path.dirname(__file__), "..", "..", "Application", "models", "bic_browser", "best_v1.onnx"),
}


@app.route("/models/<name>")
def serve_model(name):
    """Sert les modèles ONNX au front Vercel (via SW cache)."""
    path = _ONNX_MAP.get(name)
    if not path or not os.path.exists(os.path.abspath(path)):
        return f"Modèle {name} introuvable", 404
    directory = os.path.abspath(os.path.dirname(path))
    return send_from_directory(directory, os.path.basename(path),
                               mimetype="application/octet-stream")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
