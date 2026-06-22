"""
detect_ocr_container.py
Extraction de texte (EasyOCR) sur images de conteneurs maritimes.

Interface publique :
    run_ocr(image_path, languages, conf_threshold) -> list[dict]
    save_annotated_image(image_path, results, output_path) -> None
"""
import os
import re
import cv2
import numpy as np
import easyocr

# ─── Constantes ───────────────────────────────────────────────────────────────

# Numéro ISO conteneur : code propriétaire = exactement 4 lettres (ex : GVTU, MCRU)
_OWNER_CODE_RE = re.compile(r'^[A-Z]{4}$')

# Facteurs d'upscale par passe
_SCALE_PASS1 = 2   # suffisant pour la majorité des images
_SCALE_PASS2 = 3   # fallback pour texte en angle ou petite résolution
_SCALE_PASS3 = 4   # crop zone ISO uniquement (passe de rescue)

# Seuil fixe de la passe 3 : plus bas que conf_threshold normal car les conteneurs
# à fond gris foncé  ne dépassent jamais 0.27 même à x4.
_PASS3_OWNER_MIN_CONF = 0.25

# ─── Singleton EasyOCR ────────────────────────────────────────────────────────

_reader_cache: dict = {}


def _get_reader(languages: list) -> easyocr.Reader:
    """Réutilise le Reader si déjà initialisé pour ces langues (init GPU ~3 s)."""
    key = tuple(sorted(languages))
    if key not in _reader_cache:
        _reader_cache[key] = easyocr.Reader(list(languages), gpu=True)
    return _reader_cache[key]


# ─── Prétraitement ────────────────────────────────────────────────────────────

def _preprocess(img: np.ndarray, scale: int) -> np.ndarray:
    """
    Upscale + sharpening en couleur BGR.

    Ne pas convertir en niveaux de gris : le texte des conteneurs est peint
    en blanc sur fond coloré (bleu, vert, gris). La conversion grayscale réduit
    le contraste blanc/couleur et dégrade significativement la détection OCR.
    (Inverse des étiquettes de fruits où grayscale + CLAHE est optimal.)
    """
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    return cv2.filter2D(img, -1, kernel)


# ─── Helpers internes ─────────────────────────────────────────────────────────

def _read_at_scale(
    img_bgr: np.ndarray,
    reader: easyocr.Reader,
    scale: int,
    conf_threshold: float,
) -> list[dict]:
    """Lance EasyOCR sur img_bgr prétraité et filtre sous conf_threshold."""
    preprocessed = _preprocess(img_bgr, scale)
    results = []
    for bbox, text, confidence in reader.readtext(preprocessed):
        if confidence >= conf_threshold:
            xs = [p[0] / scale for p in bbox]
            ys = [p[1] / scale for p in bbox]
            results.append({
                "text": text,
                "confidence": round(confidence, 4),
                "bbox": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
            })
    return results


def _has_owner_code(results: list[dict]) -> bool:
    """Retourne True si un code propriétaire 4 lettres est déjà dans results."""
    return any(_OWNER_CODE_RE.match(r["text"].upper()) for r in results)


def _merge_into(base: list[dict], additions: list[dict]) -> None:
    """Ajoute dans base les entrées de additions dont le texte est nouveau."""
    seen = {r["text"].upper() for r in base}
    for r in additions:
        if r["text"].upper() not in seen:
            base.append(r)
            seen.add(r["text"].upper())


# ─── Interface publique ───────────────────────────────────────────────────────

def run_ocr(image_path: str, languages: list, conf_threshold: float) -> list[dict]:
    """
    Extrait le texte d'une image de conteneur maritime via EasyOCR.

    Stratégie 3 passes (chaque passe ne s'active que si le code propriétaire
    ISO n'a pas encore été trouvé) :

      Passe 1 — image entière upscalée x2, seuil conf_threshold.
                Couvre la majorité des conteneurs bleus/verts à texte clair.

      Passe 2 — image entière upscalée x3, seuil conf_threshold.
                Fallback pour texte en angle ou faible résolution (ex : HBSU image4).
                NB : x3 seul casse certaines images (ex : CCCU image3) → appliqué
                uniquement en complément de la passe 1, jamais en remplacement.

      Passe 3 — crop quadrant haut-droit upscalé x4, seuil fixe 0.25.
                Rescue pour conteneurs à faible contraste (fond gris foncé, ex : NEWU
                image7). Le Numéro ISO est toujours dans ce quadrant sur portes standard.
                Seuil 0.25 car ces images n'atteignent pas 0.27 quelle que soit la passe.
                Seul le code propriétaire (4 lettres) est accepté à ce seuil bas.

    Retourne une liste de dict :
        [{"text": str, "confidence": float, "bbox": [x1, y1, x2, y2]}, ...]

    Lève ValueError si l'image est illisible (fichier corrompu ou chemin invalide).
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Image illisible : {image_path}")

    reader = _get_reader(languages)

    # Passe 1
    results = _read_at_scale(img, reader, _SCALE_PASS1, conf_threshold)

    # Passe 2
    if not _has_owner_code(results):
        _merge_into(results, _read_at_scale(img, reader, _SCALE_PASS2, conf_threshold))

    # Passe 3 — crop haut-droit, seuil bas, uniquement le code propriétaire
    if not _has_owner_code(results):
        h, w = img.shape[:2]
        iso_crop = img[0 : h // 2, w // 2 :]
        crop_upscaled = cv2.resize(
            iso_crop, None, fx=_SCALE_PASS3, fy=_SCALE_PASS3, interpolation=cv2.INTER_CUBIC
        )
        seen = {r["text"].upper() for r in results}
        for bbox, text, confidence in reader.readtext(crop_upscaled):
            if confidence >= _PASS3_OWNER_MIN_CONF and _OWNER_CODE_RE.match(text.upper()):
                if text.upper() not in seen:
                    xs = [p[0] / _SCALE_PASS3 + w // 2 for p in bbox]
                    ys = [p[1] / _SCALE_PASS3 for p in bbox]
                    results.append({
                        "text": text,
                        "confidence": round(confidence, 4),
                        "bbox": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                    })
                    seen.add(text.upper())

    return results


def save_annotated_image(image_path: str, results: list[dict], output_path: str) -> None:
    """Dessine les bounding boxes et labels EasyOCR sur l'image et sauvegarde en PNG."""
    img = cv2.imread(image_path)
    for r in results:
        x1, y1, x2, y2 = r["bbox"]
        label = f"{r['text']} ({r['confidence']:.2f})"
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(img, label, (x1, max(y1 - 8, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    cv2.imwrite(output_path, img)


# ─── Script standalone ────────────────────────────────────────────────────────

def main() -> None:
    base = os.path.dirname(__file__)
    img_dir = os.path.join(base, "..", "images")
    images = {
        "conteneur_maersk": "conteneur_maersk.jpg",
        "image1":           "image1.jpg",
        "image2":           "imahe2.jpg",   # fichier corrompu — ignoré (ValueError)
        "image3":           "image3.jpg",
        "image4":           "image4.jpg",
        "image5":           "image5.jpg",
        "image6":           "image6.jpg",
        "image7":           "image7.jpg",
        "image8":           "image8.jpg",
    }
    languages = ["en", "fr"]
    threshold = 0.5

    for name, fname in images.items():
        path = os.path.join(img_dir, fname)
        print(f"\n=== {name.upper()} ===")
        try:
            results = run_ocr(path, languages, threshold)
            if results:
                for r in results:
                    print(f"  [{r['confidence']:.2f}] \"{r['text']}\"")
            else:
                print("  Aucun texte détecté au-dessus du seuil.")
            output = os.path.join(base, f"resultat_{name}_OCR.png")
            save_annotated_image(path, results, output)
            print(f"  >> Enregistré : {output}")
        except ValueError as e:
            print(f"  [SKIP] {e}")


if __name__ == "__main__":
    main()
