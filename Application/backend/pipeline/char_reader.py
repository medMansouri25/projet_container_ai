"""
char_reader.py — Lecture du code BIC par détection de caractères (YOLO 36 classes)
----------------------------------------------------------------------------------
Architecture recommandée par le tuteur (OCR-par-détection) : un YOLO entraîné
sur 36 classes (0-9, A-Z) détecte ET reconnaît chaque caractère du code en une
passe. On regroupe les caractères en ordre de lecture, on assemble des fragments,
et on réutilise toute la logique ISO 6346 d'ocr.py (resolve_bic) pour valider /
réparer / résoudre le code.

Remplace la lecture brute d'EasyOCR ; EasyOCR reste le moteur de secours (app.py).
"""

import cv2

import ocr  # réutilise resolve_bic + validation ISO 6346


def _detections(image, model):
    """Retourne la liste des caractères détectés : (cx, cy, w, h, char, conf)."""
    dets = []
    for result in model(image, verbose=False):
        names = result.names
        for box in result.boxes:
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            char = names[int(box.cls[0])]
            conf = float(box.conf[0])
            dets.append((( x1 + x2) / 2, (y1 + y2) / 2,
                         x2 - x1, y2 - y1, char, conf))
    return dets


def _group_lines(dets, vertical):
    """
    Regroupe les caractères en lignes de lecture puis les ordonne.
    - horizontal : lignes = groupes de même y (haut→bas), triées par x dans la ligne
    - vertical empilé : colonnes = groupes de même x (gauche→droite), triées par y
    Retourne une liste de chaînes (une par ligne/colonne).
    """
    if not dets:
        return []
    if vertical:
        primary, secondary, size_idx = 0, 1, 2   # cluster sur x, ordonne sur y
    else:
        primary, secondary, size_idx = 1, 0, 3   # cluster sur y, ordonne sur x

    med_size = sorted(d[size_idx] for d in dets)[len(dets) // 2]
    tol = max(1.0, med_size * 0.6)

    groups = []
    for d in sorted(dets, key=lambda d: d[primary]):
        placed = False
        for g in groups:
            if abs(d[primary] - g["anchor"]) <= tol:
                g["items"].append(d)
                g["anchor"] = sum(x[primary] for x in g["items"]) / len(g["items"])
                placed = True
                break
        if not placed:
            groups.append({"anchor": d[primary], "items": [d]})

    groups.sort(key=lambda g: g["anchor"])
    lines = []
    for g in groups:
        ordered = sorted(g["items"], key=lambda d: d[secondary])
        lines.append("".join(d[4] for d in ordered))
    return lines


_model_cache = None


def _get_model(model_path):
    global _model_cache
    if _model_cache is None:
        from ultralytics import YOLO
        _model_cache = YOLO(model_path)
    return _model_cache


def read_bic(image, model=None, model_path=None, vertical: bool = False) -> dict:
    """
    Lit le code BIC d'un crop (zone du marquage) par détection de caractères.
    Retourne {"bic", "valid", "corrected", "confidence", "raw"}.
    """
    if model is None:
        model = _get_model(model_path)

    dets = _detections(image, model)
    if not dets:
        return {"bic": None, "valid": False, "corrected": False,
                "confidence": 0.0, "raw": []}

    lines = _group_lines(dets, vertical)
    res = ocr.resolve_bic(lines)
    conf = round(sum(d[5] for d in dets) / len(dets), 4)

    return {"bic": res["bic"], "valid": res["valid"],
            "corrected": res["corrected"], "confidence": conf, "raw": lines}
