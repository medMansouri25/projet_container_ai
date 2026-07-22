"""
plaque.py — Lecture de la plaque d'immatriculation marocaine par EasyOCR
-------------------------------------------------------------------------
Pendant de ocr.py (BIC) pour l'API Plaque. Le modèle YOLO localise la zone
plaque (models/plaque/best_vN.pt) ; ce module lit son contenu et le normalise
au FORMAT marocain.

Format d'une plaque marocaine (gauche → droite) :
    <série 1-5 chiffres>  <lettre arabe de catégorie>  <code région 1-2 chiffres>
Ex. : « 12345 - أ - 6 ». Le champ pré-rempli présenté à l'agent suit cette
forme, exactement comme le champ BIC (l'IA propose, l'humain dispose, SPEC §11).

⚠️ Contrairement au BIC, il n'existe PAS de clé de contrôle mathématique : la
« validité » est une validation de FORME (structure chiffres-lettre-chiffres),
pas une preuve. Un champ jugé « valide » reste soumis à la validation humaine.

⚠️ Lettre arabe : EasyOCR lit de façon fiable les chiffres latins de la plaque,
mais une lettre arabe isolée et stylisée est peu fiable. Quand elle n'est pas
reconnue, elle est laissée à « ? » dans le champ pré-rempli, à confirmer par
l'agent. Le jeu de lettres inclut ط (nouvelles séries) même si le dataset de
détection en manque encore — voir prepare_plaque_dataset.py.
"""

import re

# Lettres de catégorie des plaques marocaines (extensible). On inclut les
# variantes de l'alif (أ إ آ ا) car l'OCR les confond. ط = nouvelles séries.
MOROCCAN_LETTERS = {
    "ا", "أ", "إ", "آ",   # alif et variantes (série « a »)
    "ب",                    # ba
    "ج",                    # jim
    "د",                    # dal
    "ه",                    # ha
    "و",                    # waw
    "ط",                    # Ta — nouvelles séries (manque dans le dataset)
    "ح",                    # ha (hutta)
    "ش",                    # shin — police
    "م",                    # mim — usage spécial
}

# Plage Unicode arabe (pour repérer une lettre quelconque dans un fragment OCR)
_ARABIC = r"؀-ۿ"
_UNKNOWN_LETTER = "?"

_DIGITS = "0123456789"


def _clean(fragment: str) -> str:
    """Ne garde que les chiffres et les caractères arabes d'un fragment OCR."""
    return re.sub(rf"[^0-9{_ARABIC}]", "", fragment or "")


def _find_letter(text: str):
    """Retourne (lettre, index) de la première lettre arabe du texte, ou
    (None, -1). Une lettre connue prime sur une lettre arabe inconnue."""
    known_idx = -1
    any_char, any_idx = None, -1
    for i, ch in enumerate(text):
        if "؀" <= ch <= "ۿ":
            if ch in MOROCCAN_LETTERS:
                return ch, i
            if any_char is None:
                any_char, any_idx = ch, i
    return any_char, any_idx if any_char else -1


def resolve_plaque(texts) -> dict:
    """
    Assemble et normalise une plaque marocaine à partir de fragments OCR.

    Les fragments sont supposés triés gauche→droite par X (fait dans
    extract_plaque avant l'appel). On identifie le fragment lettre par
    priorité : lettre arabe connue non-alif > alif > toute lettre arabe.
    Les barres verticales de la plaque sont souvent lues comme ا (alif) :
    on les déprioritise pour que la vraie lettre de catégorie (ب ج ط …)
    l'emporte même quand elle est dans le même token.

    Les fragments situés avant le fragment lettre donnent la série (gauche),
    ceux situés après donnent le code région (droite).

    Retourne {"plaque", "valid", "left", "letter", "right", "raw"} où
    "plaque" suit la forme « <série> - <lettre> - <région> » (ou None si
    rien d'exploitable).
    """
    cleaned = [_clean(t) for t in texts if t]
    cleaned = [c for c in cleaned if c]
    joined = "".join(cleaned)

    left = right = ""
    letter = _UNKNOWN_LETTER

    # --- Approche fragment-aware (textes X-sortés = ordre spatial LTR) ----
    # Priorités : 1 = lettre connue non-alif, 2 = alif/variante, 3 = non trouvée
    letter_frag_idx = -1
    best_prio = 3

    letter_char_pos = -1  # position du char lettre dans son fragment

    for i, frag in enumerate(cleaned):
        ar_chars = [(pos, ch) for pos, ch in enumerate(frag) if "؀" <= ch <= "ۿ"]
        for pos, ch in ar_chars:
            if ch in MOROCCAN_LETTERS:
                prio = 2 if ch in {"ا", "أ", "إ", "آ"} else 1
                if prio < best_prio:
                    best_prio = prio
                    letter = ch
                    letter_frag_idx = i
                    letter_char_pos = pos
                if best_prio == 1:
                    break
        if best_prio == 1:
            break   # impossible de faire mieux : arrêt total

    # Fallback : n'importe quel caractère arabe si aucune lettre connue trouvée
    if letter_frag_idx < 0:
        for i, frag in enumerate(cleaned):
            for pos, ch in enumerate(frag):
                if "؀" <= ch <= "ۿ":
                    letter_frag_idx = i
                    letter_char_pos = pos
                    break
            if letter_frag_idx >= 0:
                break

    if letter_frag_idx >= 0:
        frag = cleaned[letter_frag_idx]
        # Le fragment peut fusionner série + lettre (ex : "40129هـا").
        # On découpe aussi à l'INTÉRIEUR du fragment autour de la lettre.
        frag_left  = re.sub(r"\D", "", frag[:letter_char_pos])
        frag_right = re.sub(r"\D", "", frag[letter_char_pos + 1:])
        # Série = chiffres des fragments AVANT + partie gauche du fragment lettre
        left  = "".join(re.sub(r"\D", "", f) for f in cleaned[:letter_frag_idx]) + frag_left
        # Région = partie droite du fragment lettre + chiffres des fragments APRÈS
        right = frag_right + "".join(re.sub(r"\D", "", f) for f in cleaned[letter_frag_idx + 1:])
    else:
        # Pas de lettre lue : premier fragment chiffres = série, dernier = région
        digit_frags = [f for f in cleaned if f.isdigit()]
        if len(digit_frags) >= 2:
            left, right = digit_frags[0], digit_frags[-1]
        elif len(digit_frags) == 1:
            left = digit_frags[0]
        else:
            groups = re.findall(r"\d+", joined)
            if groups:
                left = groups[0]

    left = left[:5]
    right = right[:2]

    if not left and not right:
        return {"plaque": None, "valid": False, "left": "", "letter": letter,
                "right": "", "raw": cleaned}

    valid = (
        1 <= len(left) <= 5
        and 1 <= len(right) <= 2
        and letter in MOROCCAN_LETTERS
    )
    return {"plaque": format_plaque(left, letter, right), "valid": valid,
            "left": left, "letter": letter, "right": right, "raw": cleaned}


def format_plaque(left: str, letter: str, right: str) -> str:
    """Assemble la forme « <série> - <lettre> - <région> » en ignorant les
    parties vides (utile quand l'OCR n'a lu qu'un côté)."""
    return " - ".join(p for p in (left, letter, right) if p)


def is_valid_format(plaque: str) -> bool:
    """Valide la FORME d'une chaîne plaque déjà composée (pas de clé de
    contrôle). Accepte « <1-5 chiffres> - <lettre arabe connue> - <1-2 chiffres> »."""
    parts = [p.strip() for p in plaque.split("-")]
    if len(parts) != 3:
        return False
    left, letter, right = parts
    return (left.isdigit() and 1 <= len(left) <= 5
            and letter in MOROCCAN_LETTERS
            and right.isdigit() and 1 <= len(right) <= 2)


# ── OCR (frontière EasyOCR) ────────────────────────────────────────────────

_reader = None
_has_arabic = False


def _get_reader():
    """Lecteur EasyOCR de la plaque (chargé une fois). Idéalement arabe+anglais
    pour lire la lettre de catégorie ; MAIS le modèle arabe se télécharge au
    premier appel — indisponible hors-ligne / réseau bloqué (cf. ADR-5). On
    **dégrade** alors sur l'anglais seul (déjà présent, utilisé par ocr.py) :
    les chiffres sont lus, la lettre arabe reste « ? » (saisie humaine, I3).
    Dès que arabic_g2.pth est présent dans ~/.EasyOCR/model/, l'arabe remonte."""
    global _reader, _has_arabic
    if _reader is None:
        import easyocr
        try:
            _reader = easyocr.Reader(["ar", "en"], verbose=False)
            _has_arabic = True
        except Exception as e:
            _reader = easyocr.Reader(["en"], verbose=False)
            _has_arabic = False
            print(f"[plaque] modele arabe indisponible ({type(e).__name__}) : "
                  f"lecture chiffres seule, lettre -> '?'")
    return _reader


def _allowlist() -> str:
    """Chiffres (toujours) + lettres de catégorie si le modèle arabe est chargé."""
    return _DIGITS + ("".join(sorted(MOROCCAN_LETTERS)) if _has_arabic else "")


_TARGET_H = 128  # hauteur mini d'un crop avant OCR (chiffres de plaque petits)


def _ensure_height(img):
    """Agrandit un crop trop petit jusqu'à _TARGET_H : sur ce dataset la plaque
    ne fait souvent que ~30 px de haut, en-dessous du seuil lisible d'EasyOCR.
    C'est le levier n°1 identifié au benchmark (crops minuscules et flous)."""
    import cv2
    h = img.shape[0]
    if 0 < h < _TARGET_H:
        s = _TARGET_H / h
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    return img


def _variants(image):
    """Brute + CLAHE (contraste local) + unsharp (rehausse les bords des
    chiffres). Chacune peut réussir là où les autres échouent selon
    l'exposition/le flou. On reste léger (CPU VPS)."""
    import cv2
    yield image
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    yield cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR)
    # unsharp mask : nettes les arêtes des chiffres flous du dataset
    blur = cv2.GaussianBlur(clahe, (0, 0), 3)
    sharp = cv2.addWeighted(clahe, 1.6, blur, -0.6, 0)
    yield cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR)


def extract_plaque(image, reader=None, time_budget: float = 12.0) -> dict:
    """
    Lit une plaque marocaine dans un crop (zone plaque localisée par YOLO).
    Essaie quelques variantes/échelles, garde la meilleure lecture valide
    (forme complète) sinon la plus complète. Frontière OCR : mockable en test.

    Retourne {"plaque", "valid", "left", "letter", "right", "confidence", "raw"}.
    """
    import time
    import cv2

    if reader is None:
        reader = _get_reader()
    deadline = time.monotonic() + time_budget

    image = _ensure_height(image)   # petits crops -> ~128 px avant tout OCR

    best = {"plaque": None, "valid": False, "left": "", "letter": _UNKNOWN_LETTER,
            "right": "", "confidence": 0.0, "raw": []}

    for variant in _variants(image):
        for scale in (1, 2):
            if time.monotonic() > deadline:
                break
            img = variant if scale == 1 else cv2.resize(
                variant, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            results = reader.readtext(img, allowlist=_allowlist())
            # Tri gauche→droite par position X : EasyOCR en mode arabe lit
            # parfois en RTL, ce qui place la région (droite) avant la série
            # (gauche) et casse l'assemblage dans resolve_plaque.
            results = sorted(results, key=lambda r: min(p[0] for p in r[0]))
            texts = [r[1] for r in results]
            confs = [float(r[2]) for r in results]
            res = resolve_plaque(texts)
            if res["plaque"] is None:
                continue
            conf = round(sum(confs) / len(confs), 4) if confs else 0.0
            res["confidence"] = conf
            if res["valid"]:
                return {**res, "raw": texts}
            # à défaut d'une lecture valide : garder la plus « complète »
            if len(res["left"]) + len(res["right"]) > len(best["left"]) + len(best["right"]):
                best = {**res, "confidence": conf, "raw": texts}

    return best
