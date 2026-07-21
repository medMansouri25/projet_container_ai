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
_LOOSE_RE = re.compile(r"[A-Z0-9?]{10,11}")

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
    '?' (caractère illisible) est conservé tel quel — il sera résolu par
    l'équation du chiffre de contrôle. La position 3 (catégorie ISO,
    presque toujours U) reçoit un prior : 0/O/Q/V/W → U.
    Retourne (normalisé, nb_substitutions) ou None si structure invalide."""
    subs = 0
    letters = ""
    for i, c in enumerate(candidate[:4]):
        if c == "?":
            letters += c
            continue
        if i == 3 and c not in "UJZ":
            if c in "0OQVW":
                letters += "U"
                subs += 1
                continue
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
        if c == "?":
            digits += c
            continue
        if c.isalpha():
            c2 = _TO_DIGIT.get(c)
            if c2 is None:
                return None
            digits += c2
            subs += 1
        else:
            digits += c
    return letters + digits, subs


_LETTER_PREF = "SCLMTAEUHINORGPBDFKWVXYZJQ"  # frequence approx. des prefixes


def _solve_unknown(norm: str):
    """Résout l'unique caractère '?' d'un code 11 chars via le chiffre de
    contrôle. Chiffres et position 3 : solution unique garantie. Lettres en
    position 0-2 : les valeurs espacées de 11 (ex B/L/V) donnent le même
    reste → jusqu'à 3 solutions, départagées par fréquence des lettres.
    Retourne (code, unique) ou None."""
    pos = norm.index("?")
    if pos < 4:
        charset = "UJZ" if pos == 3 else "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    else:
        charset = "0123456789"
    solutions = [norm[:pos] + ch + norm[pos + 1:] for ch in charset
                 if validate_check_digit(norm[:pos] + ch + norm[pos + 1:])]
    if not solutions:
        return None
    if len(solutions) == 1:
        return solutions[0], True
    solutions.sort(key=lambda s: _LETTER_PREF.index(s[pos])
                   if s[pos] in _LETTER_PREF else 99)
    return solutions[0], False


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
    cleaned = [re.sub(r"[^A-Z0-9?]", "", t.upper()) for t in texts if t]
    cleaned = [c for c in cleaned if c]
    # Exclure les fragments code taille ISO et leurs sous-fragments : "45G1",
    # "22G1" mais aussi les fragments partiels "5G", "G1", "5G1" (la marge
    # basse du crop peut inclure une partie seulement du code taille).
    # Critère : 1-4 chars, UN SEUL [A-Z] au milieu, reste = chiffres, token
    # mixte (pas purement alpha ni purement numérique → ne filtre pas les
    # lettres isolées du préfixe BIC ni les groupes de chiffres seuls).
    _SIZE_CODE = re.compile(r"^\d{0,2}[A-Z]\d{0,2}$")
    cleaned = [c for c in cleaned
               if not (1 <= len(c) <= 4 and _SIZE_CODE.fullmatch(c)
                       and not c.isdigit() and not c.isalpha())]

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
                    unknowns = norm.count("?")
                    if unknowns > 1:
                        continue
                    c4pen = 0 if norm[3] in "UJZ?" else 10
                    penalty = subs * 2 + c4pen
                    if unknowns == 1:
                        if length != 11:
                            continue
                        solved = _solve_unknown(norm)
                        if solved is None:
                            continue
                        code, unique = solved
                        # deduit par l'equation : sur si solution unique,
                        # sinon choix heuristique -> badge verification
                        entry = (penalty + (2 if unique else 4), code,
                                 not unique)
                    elif length == 11 and validate_check_digit(norm):
                        entry = (penalty, norm, False)
                    else:
                        repaired = norm[:10] + str(compute_check_digit(norm[:10]))
                        entry = (penalty + 3, repaired, True)
                    if best is None or entry[0] < best[0]:
                        best = entry

    if best:
        return {"bic": best[1], "valid": True, "corrected": best[2],
                "score": best[0]}
    return {"bic": None, "valid": False, "corrected": False, "score": 999}


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


def _sort_column_order(results, img_width):
    """Trie en colonnes (gauche→droite) puis haut→bas dans chaque colonne.
    Pour les marquages verticaux en caractères empilés : chaque caractère est
    détecté séparément et doit être assemblé colonne par colonne, sinon les
    colonnes voisines (ex : taille 22G1) s'intercalent par hauteur."""
    bin_w = max(1, int(img_width * 0.25))

    def key(r):
        try:
            xs = [p[0] for p in r[0]]
            ys = [p[1] for p in r[0]]
            return (min(xs) // bin_w, min(ys))
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


_TARGET_H = 160  # dimension minimale d'une zone avant OCR (petites zones YOLO)


def _ensure_height(img):
    """Agrandit les petits crops à une taille lisible : la plus petite
    dimension (hauteur pour un marquage horizontal, largeur pour un
    marquage vertical empilé) est portée à _TARGET_H."""
    small = min(img.shape[0], img.shape[1])
    if 0 < small < _TARGET_H:
        s = _TARGET_H / small
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


def _read_stacked_columns(image, reader) -> list:
    """
    Lecteur dédié aux marquages verticaux en caractères empilés (côtés de
    conteneur) : EasyOCR ne sait pas les segmenter seul.
    1. masque HSV de la peinture blanche (S faible, V fort)
    2. projection verticale → colonnes de texte
    3. projection horizontale par colonne → bande de chaque caractère
    4. OCR caractère par caractère
    Retourne une liste de chaînes (une par colonne, '?' si caractère illisible).
    """
    bw = _white_text_mask(image)
    H, W = bw.shape

    colsum = bw.sum(axis=0) / 255
    thr = max(2, 0.03 * H)
    cols, start = [], None
    for x in range(W):
        if colsum[x] > thr and start is None:
            start = x
        elif colsum[x] <= thr and start is not None:
            if x - start > 10:
                cols.append((start, x))
            start = None
    if start is not None and W - start > 10:
        cols.append((start, W))

    fragments = []
    for x1, x2 in cols[:4]:
        band = bw[:, x1:x2]
        rowsum = band.sum(axis=1) / 255
        rthr = max(2, 0.08 * (x2 - x1))
        chars, s = [], None
        for y in range(H):
            if rowsum[y] > rthr and s is None:
                s = y
            elif rowsum[y] <= rthr and s is not None:
                if y - s > 10:
                    chars.append((s, y))
                s = None
        if s is not None and H - s > 10:
            chars.append((s, H))
        if len(chars) < 4:      # colonne trop courte pour un code
            continue
        txt = ""
        for y1, y2 in chars:
            pad = 8
            ch = image[max(0, y1 - pad):min(H, y2 + pad),
                       max(0, x1 - pad):min(W, x2 + pad)]
            if ch.size == 0:
                txt += "?"
                continue
            s2 = max(1.0, 80.0 / ch.shape[0])
            ch = cv2.resize(ch, None, fx=s2, fy=s2, interpolation=cv2.INTER_CUBIC)
            r = reader.readtext(ch, allowlist=ALLOWLIST.strip())
            best_frag = max(r, key=lambda t: t[2])[1].replace(" ", "") if r else "?"
            txt += best_frag if best_frag else "?"
        fragments.append(txt)
    return fragments


def _white_text_mask(image):
    """Masque adaptatif de la peinture blanche (partagé colonnes/orientation)."""
    import numpy as np
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    S, V = hsv[:, :, 1], hsv[:, :, 2]
    bw = None
    for s_thr, v_thr in ((70, 140), (50, 180), (35, 210)):
        cand = ((S < s_thr) & (V > v_thr)).astype("uint8") * 255
        bw = cand
        if cand.mean() / 255 <= 0.10:
            break
    return cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def _detect_text_orientation(image):
    """
    Détermine l'orientation du TEXTE dans un crop (pas celle de la boîte :
    un marquage horizontal sur 2 lignes donne une boîte plus haute que
    large). Composantes connexes du masque blanc → les caractères
    s'alignent-ils davantage en lignes (horizontal) ou en colonnes
    (vertical empilé) ?
    Retourne 'horizontal', 'vertical' ou 'unknown'.
    """
    import numpy as np
    bw = _white_text_mask(image)
    n, _, stats, _ = cv2.connectedComponentsWithStats(bw)
    H, W = bw.shape
    boxes = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if 25 <= area <= 0.05 * H * W and h < 0.5 * H and w < 0.5 * W:
            boxes.append((x + w / 2, y + h / 2, w, h))
    if len(boxes) < 5:
        return "unknown"
    med_h = sorted(b[3] for b in boxes)[len(boxes) // 2]
    med_w = sorted(b[2] for b in boxes)[len(boxes) // 2]

    def max_group(values, tol):
        values = sorted(values)
        best = cur = 1
        anchor = values[0]
        for v in values[1:]:
            if v - anchor <= tol:
                cur += 1
                best = max(best, cur)
            else:
                anchor = v
                cur = 1
        return best

    rows = max_group([b[1] for b in boxes], med_h * 0.7)   # même ligne
    cols = max_group([b[0] for b in boxes], med_w * 0.7)   # même colonne
    if rows >= 4 and rows > cols:
        return "horizontal"
    if cols >= 4 and cols > rows:
        return "vertical"
    return "unknown"


def extract_bic(image, vertical: bool = False, reader=None,
                is_zone: bool = False, time_budget: float = 25.0) -> dict:
    """
    Extrait le code BIC d'un crop (conteneur entier ou zone BIC localisée).
    vertical=True → essaie les deux rotations 90° (le texte vertical se lit
    de haut en bas ou de bas en haut selon le côté du conteneur).
    is_zone=True → le crop EST déjà la zone du marquage (localisée par le
    modèle spécialiste) : inutile de balayer des sous-régions ou de forcer
    les grandes échelles — divise le nombre de passes par ~4 (crucial sur
    le VPS sans GPU où chaque lecture EasyOCR coûte ~1-2 s).
    time_budget : durée max en secondes ; à expiration, retourne le meilleur
    candidat trouvé jusqu'ici plutôt que d'épuiser toutes les passes.
    Stratégie : variantes de prétraitement × échelles × régions, arrêt dès
    qu'un BIC valide sans correction est lu, sinon vote majoritaire parmi
    les codes réparés.
    Retourne {"bic", "valid", "corrected", "confidence", "raw"}.
    """
    import time
    deadline = time.monotonic() + time_budget

    if reader is None:
        reader = _get_reader()

    # La forme de la boite ment souvent (marquage horizontal sur 2 lignes =
    # boite haute) : on tranche avec l'orientation reelle des caracteres
    if vertical:
        detected = _detect_text_orientation(image)
        if detected == "horizontal":
            vertical = False

    # Vertical : essayer d'abord SANS rotation (marquage en caractères
    # empilés, chacun droit — le cas le plus courant sur les côtés),
    # puis les deux rotations (texte réellement couché à 90°).
    orientations = [image]
    if vertical:
        orientations = [image,
                        cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
                        cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)]

    best = {"bic": None, "valid": False, "corrected": False,
            "confidence": 0.0, "raw": []}
    repaired_votes = {}   # bic réparé -> (meilleur score, occurrences, conf, raw)

    # Vertical : le lecteur de colonnes empilées d'abord (le cas standard
    # des cotes de conteneur, que la detection EasyOCR classique rate).
    # S'il produit un candidat coherent, il est PRIORITAIRE : les passes
    # par rotation lisent du bruit non deterministe sur ce type de marquage
    # et peuvent fabriquer un faux code plausible qui gagnerait le vote.
    if vertical:
        fragments = _read_stacked_columns(image, reader)
        if fragments:
            res = resolve_bic(fragments)
            if res["bic"] and res["score"] <= 10:
                return {"bic": res["bic"], "valid": res["valid"],
                        "corrected": res["corrected"], "confidence": 0.9,
                        "raw": fragments}
            if res["bic"]:
                repaired_votes[res["bic"]] = (res["score"], 1, 0.5,
                                              fragments, res["corrected"])
            best["raw"] = fragments

    scales = (1, 2) if is_zone else _SCALES

    def _timeout():
        return time.monotonic() > deadline

    for orient_idx, oriented in enumerate(orientations):
        # Les lectures sur image pivotee (caracteres couches) sont bruitees
        # et non deterministes : leurs candidats repares sont penalises pour
        # ne jamais battre une lecture faite a l'endroit
        rot_penalty = 6 if (vertical and orient_idx > 0) else 0
        # zone deja localisee : une seule region (le crop entier)
        regions = [(oriented, 1)] if is_zone else _regions(oriented)
        for region, base_scale in regions:
            if region.size == 0 or _timeout():
                continue
            region = _ensure_height(region)
            for variant in _variants(region):
                for scale in scales:
                    if _timeout():
                        break
                    s = scale * base_scale
                    img = variant if s == 1 else cv2.resize(
                        variant, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
                    results = reader.readtext(img, allowlist=ALLOWLIST)

                    orderings = [_sort_reading_order(results)]
                    if vertical:
                        orderings.append(_sort_column_order(results, img.shape[1]))

                    for ordered in orderings:
                        texts = [r[1] for r in ordered]
                        confs = [float(r[2]) for r in ordered]
                        if not best["raw"]:
                            best["raw"] = texts

                        res = resolve_bic(texts)
                        if res["bic"] is None:
                            continue

                        conf = round(sum(confs) / len(confs), 4) if confs else 0.0
                        if not res["corrected"] and res["score"] <= 2:
                            # BIC lu proprement (0-1 substitution, categorie
                            # U/J/Z) et chiffre de controle OK : definitif.
                            # Un candidat "valide" mais tres substitue peut
                            # etre un faux positif (1 chance sur 10) -> vote.
                            best.update(res, confidence=conf, raw=texts)
                            best.pop("score", None)
                            return best
                        score = res["score"] + rot_penalty
                        sc, n, c, r, corr = repaired_votes.get(
                            res["bic"], (score, 0, 0.0, texts,
                                         res["corrected"]))
                        repaired_votes[res["bic"]] = (
                            min(sc, score), n + 1, max(c, conf), r,
                            corr and res["corrected"])

    if repaired_votes:
        # meilleur score d'abord (candidat le plus propre), puis occurrences
        bic, (sc, n, conf, raw, corr) = min(
            repaired_votes.items(),
            key=lambda kv: (kv[1][0], -kv[1][1], -kv[1][2]))
        # un candidat au score eleve reste douteux meme si le calcul passe :
        # on force le badge "verifiez le code"
        best.update({"bic": bic, "valid": True,
                     "corrected": corr or sc > 2,
                     "confidence": conf, "raw": raw})

    return best
