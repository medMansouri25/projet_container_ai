"""
ocr.py — Extraction du code BIC (ISO 6346) par EasyOCR
-------------------------------------------------------
Pipeline : crop conteneur → (rotation 90° si vertical) → EasyOCR
multi-passes (×1, ×2, ×3 + passe ciblée haut-droite) → assemblage des
fragments → normalisation par position → validation/réparation du
chiffre de contrôle.

Format BIC (ISO 6346) : 3 lettres propriétaire + catégorie (U/J/Z)
+ 6 chiffres de série + 1 chiffre de contrôle (affiché dans une case).
Le marquage figure sur les 4 faces, le plus souvent en haut à droite,
parfois vertical sur les côtés.

Corrections OCR position-aware (confusions documentées) :
  zone lettres  : 0→O 1→I 2→Z 5→S 8→B 6→G 4→A
  zone chiffres : O→0 Q→0 D→0 I→1 L→1 Z→2 S→5 B→8 G→6
Si les 10 premiers caractères sont lus mais le chiffre de contrôle est
absent ou incohérent, il est recalculé et proposé (flag corrected=True).
"""

import re

import cv2
import numpy as np

BIC_RE = re.compile(r"[A-Z]{4}\d{7}")
_LOOSE_RE = re.compile(r"[A-Z0-9]{10,11}")

ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "

# ISO 6346 : valeurs des lettres (les multiples de 11 sont sautés)
_LETTER_VALUES = {}
_v = 10
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    if _v % 11 == 0:
        _v += 1
    _LETTER_VALUES[_c] = _v
    _v += 1

_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "4": "A"}
_TO_DIGIT  = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2",
              "S": "5", "B": "8", "G": "6"}

_SCALES = (1, 2, 3)  # passes progressives comme TestYolo


def compute_check_digit(owner_serial: str) -> int:
    """Calcule le chiffre de contrôle ISO 6346 des 10 premiers caractères."""
    total = 0
    for i, ch in enumerate(owner_serial[:10]):
        value = _LETTER_VALUES[ch] if ch.isalpha() else int(ch)
        total += value * (2 ** i)
    return total % 11 % 10


def validate_check_digit(bic: str) -> bool:
    """Vérifie le chiffre de contrôle ISO 6346 d'un code BIC de 11 caractères."""
    bic = bic.replace(" ", "").upper()
    if len(bic) != 11 or not BIC_RE.fullmatch(bic):
        return False
    return compute_check_digit(bic[:10]) == int(bic[10])


def _normalize(candidate: str) -> str | None:
    """
    Normalise un candidat de 10-11 caractères selon la structure ISO 6346 :
    positions 0-3 forcées en lettres, positions 4+ forcées en chiffres.
    Retourne None si la structure reste invalide après correction.
    """
    letters = "".join(_TO_LETTER.get(c, c) for c in candidate[:4])
    digits = "".join(_TO_DIGIT.get(c, c) for c in candidate[4:])
    if not (letters.isalpha() and digits.isdigit()):
        return None
    return letters + digits


def _normalize_scored(candidate: str):
    """Normalise un candidat 10-11 chars et compte les substitutions.
    Retourne (normalisé, nb_substitutions) ou None si structure invalide."""
    subs = 0
    letters = ""
    for c in candidate[:4]:
        if c.isdigit():
            c2 = _TO_LETTER.get(c)
            if c2 is None:
                return None
            letters += c2
            subs += 1
        else:
            letters += c
    digits = ""
    for c in candidate[4:]:
        if c.isalpha():
            c2 = _TO_DIGIT.get(c)
            if c2 is None:
                return None
            digits += c2
            subs += 1
        else:
            digits += c
    return letters + digits, subs


def resolve_bic(texts) -> dict:
    """
    Cherche, normalise et valide/répare un code BIC dans des fragments OCR.
    Chaque candidat est **scoré** : substitutions de normalisation (×2),
    4e lettre hors U/J/Z (+10, la catégorie ISO 6346 d'un conteneur est U),
    chiffre de contrôle recalculé (+3). Le score le plus bas gagne — un
    propriétaire propre réparé bat un faux code "plausible" sur-normalisé.
    Les fragments sont assemblés en séquence ET en paires croisées (l'OCR
    peut renvoyer les lignes dans le désordre).
    Retourne {"bic": str|None, "valid": bool, "corrected": bool}.
    """
    cleaned = [re.sub(r"[^A-Z0-9]", "", t.upper()) for t in texts if t]
    cleaned = [c for c in cleaned if c]

    candidates = list(cleaned)
    for i in range(len(cleaned)):
        joined = ""
        for j in range(i, len(cleaned)):
            joined += cleaned[j]
            if len(joined) >= 10:
                candidates.append(joined)
    # paires croisées dans les deux sens (fragments hors ordre de lecture)
    for i, a in enumerate(cleaned):
        for j, b in enumerate(cleaned):
            if i != j and len(a) >= 4 and len(a + b) >= 10:
                candidates.append(a + b)

    best = None   # (score, bic, corrected)

    for cand in candidates:
        for m in _LOOSE_RE.finditer(cand):
            frag = m.group(0)
            for length in (11, 10):
                if len(frag) < length:
                    continue
                for start in range(0, len(frag) - length + 1):
                    scored = _normalize_scored(frag[start:start + length])
                    if scored is None:
                        continue
                    norm, subs = scored
                    penalty = subs * 2 + (0 if norm[3] in "UJZ" else 10)
                    if length == 11 and validate_check_digit(norm):
                        entry = (penalty, norm, False)
                    else:
                        repaired = norm[:10] + str(compute_check_digit(norm[:10]))
                        entry = (penalty + 3, repaired, True)
                    if best is None or entry[0] < best[0]:
                        best = entry

    if best:
        return {"bic": best[1], "valid": True, "corrected": best[2]}
    return {"bic": None, "valid": False, "corrected": False}


def find_bic(texts) -> str | None:
    """Compat : retourne le BIC trouvé (corrigé ou non), sinon None."""
    return resolve_bic(texts)["bic"]


def _sort_reading_order(results):
    """Trie les détections EasyOCR en ordre de lecture (haut→bas, gauche→droite).
    EasyOCR ne garantit pas l'ordre — indispensable pour assembler le BIC."""
    def key(r):
        try:
            xs = [p[0] for p in r[0]]
            ys = [p[1] for p in r[0]]
            return (min(ys), min(xs))
        except (TypeError, IndexError):
            return (0, 0)
    try:
        return sorted(results, key=key)
    except Exception:
        return results


_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["en"], verbose=False)
    return _reader


def _regions(image):
    """Zones à OCRiser : image entière, puis haut-droite (emplacement normalisé
    du marquage), puis bande supérieure."""
    h, w = image.shape[:2]
    yield image, 1
    yield image[0:int(h * 0.45), int(w * 0.40):w], 3   # haut-droite agrandi
    yield image[0:int(h * 0.35), 0:w], 2               # bande superieure


_TARGET_H = 160  # hauteur minimale d'une zone avant OCR (petites zones YOLO)


def _ensure_height(img):
    """Agrandit les petits crops (zone BIC ~30px de haut) à une hauteur lisible."""
    h = img.shape[0]
    if 0 < h < _TARGET_H:
        s = _TARGET_H / h
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    return img


def _variants(image):
    """Variantes de prétraitement : brute, CLAHE (contraste local), Otsu binaire
    (texte force en sombre sur clair). Chaque variante peut réussir là où les
    autres échouent selon peinture/rouille/éclairage."""
    yield image
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    yield cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR)
    _, th = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if th.mean() < 127:
        th = 255 - th
    yield cv2.cvtColor(th, cv2.COLOR_GRAY2BGR)


def extract_bic(image, vertical: bool = False, reader=None) -> dict:
    """
    Extrait le code BIC d'un crop (conteneur entier ou zone BIC localisée).
    vertical=True → essaie les deux rotations 90° (le texte vertical se lit
    de haut en bas ou de bas en haut selon le côté du conteneur).
    Stratégie : variantes de prétraitement × échelles × régions, arrêt dès
    qu'un BIC valide sans correction est lu, sinon vote majoritaire parmi
    les codes réparés.
    Retourne {"bic", "valid", "corrected", "confidence", "raw"}.
    """
    if reader is None:
        reader = _get_reader()

    orientations = [image]
    if vertical:
        orientations = [cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
                        cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)]

    best = {"bic": None, "valid": False, "corrected": False,
            "confidence": 0.0, "raw": []}
    repaired_votes = {}   # bic répa ré -> (occurrences, conf, raw)

    for oriented in orientations:
        for region, base_scale in _regions(oriented):
            if region.size == 0:
                continue
            region = _ensure_height(region)
            for variant in _variants(region):
                for scale in _SCALES:
                    s = scale * base_scale
                    img = variant if s == 1 else cv2.resize(
                        variant, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
                    results = reader.readtext(img, allowlist=ALLOWLIST)
                    results = _sort_reading_order(results)
                    texts = [r[1] for r in results]
                    confs = [float(r[2]) for r in results]
                    if not best["raw"]:
                        best["raw"] = texts

                    res = resolve_bic(texts)
                    if res["bic"] is None:
                        continue

                    conf = round(sum(confs) / len(confs), 4) if confs else 0.0
                    if not res["corrected"]:
                        # BIC valide tel quel : reponse definitive
                        best.update(res, confidence=conf, raw=texts)
                        return best
                    n, c, r = repaired_votes.get(res["bic"], (0, 0.0, texts))
                    repaired_votes[res["bic"]] = (n + 1, max(c, conf), r)

    if repaired_votes:
        # vote majoritaire parmi les codes repares (puis meilleure confiance)
        bic, (n, conf, raw) = max(repaired_votes.items(),
                                  key=lambda kv: (kv[1][0], kv[1][1]))
        best.update({"bic": bic, "valid": True, "corrected": True,
                     "confidence": conf, "raw": raw})

    return best
