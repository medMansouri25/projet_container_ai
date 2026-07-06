"""
ocr.py — Extraction du code BIC (ISO 6346) par EasyOCR
-------------------------------------------------------
Pipeline : crop conteneur → (rotation 90° si vertical) → EasyOCR
multi-passes (×1, ×2, ×3 comme TestYolo) → assemblage des fragments
→ regex BIC → validation du chiffre de contrôle.

Format BIC : 4 lettres + 6 chiffres + 1 chiffre de contrôle.
Exemple : MRKU3450182
"""

import re

import cv2
import numpy as np

BIC_RE = re.compile(r"[A-Z]{4}\d{7}")

# ISO 6346 : valeurs des lettres (les multiples de 11 sont sautés)
_LETTER_VALUES = {}
_v = 10
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    if _v % 11 == 0:
        _v += 1
    _LETTER_VALUES[_c] = _v
    _v += 1

_SCALES = (1, 2, 3)  # passes progressives comme TestYolo


def validate_check_digit(bic: str) -> bool:
    """Vérifie le chiffre de contrôle ISO 6346 d'un code BIC de 11 caractères."""
    bic = bic.replace(" ", "").upper()
    if len(bic) != 11 or not BIC_RE.fullmatch(bic):
        return False
    total = 0
    for i, ch in enumerate(bic[:10]):
        value = _LETTER_VALUES[ch] if ch.isalpha() else int(ch)
        total += value * (2 ** i)
    check = total % 11 % 10
    return check == int(bic[10])


def find_bic(texts) -> str | None:
    """
    Cherche un code BIC dans des fragments OCR.
    Essaie chaque fragment seul puis la concaténation de tous
    (l'OCR coupe souvent 'MRKU' / '345018' / '2' en morceaux).
    """
    cleaned = [re.sub(r"[^A-Z0-9]", "", t.upper()) for t in texts]
    candidates = list(cleaned) + ["".join(cleaned)]

    # Fenêtre glissante sur les concaténations successives
    for i in range(len(cleaned)):
        joined = ""
        for j in range(i, len(cleaned)):
            joined += cleaned[j]
            candidates.append(joined)

    for cand in candidates:
        m = BIC_RE.search(cand)
        if m:
            return m.group(0)
    return None


_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["en"], verbose=False)
    return _reader


def extract_bic(image, vertical: bool = False, reader=None) -> dict:
    """
    Extrait le code BIC d'un crop de conteneur (image BGR numpy).
    vertical=True → rotation 90° horaire avant OCR (texte vertical).
    Retourne {"bic": str|None, "valid": bool, "confidence": float, "raw": [str]}.
    """
    if reader is None:
        reader = _get_reader()

    if vertical:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)

    best = {"bic": None, "valid": False, "confidence": 0.0, "raw": []}

    for scale in _SCALES:
        img = image if scale == 1 else cv2.resize(
            image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )
        results = reader.readtext(img)  # [(bbox, text, conf), ...]
        texts = [r[1] for r in results]
        confs = [float(r[2]) for r in results]
        best["raw"] = texts

        bic = find_bic(texts)
        if bic:
            best["bic"] = bic
            best["valid"] = validate_check_digit(bic)
            best["confidence"] = round(sum(confs) / len(confs), 4) if confs else 0.0
            if best["valid"]:
                return best  # BIC valide -> pas besoin des passes suivantes

    return best
