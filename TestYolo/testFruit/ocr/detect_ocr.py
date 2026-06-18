import os
import cv2
import numpy as np
import easyocr


_reader_cache: dict = {}


def _get_reader(languages: list) -> easyocr.Reader:
    key = tuple(sorted(languages))
    if key not in _reader_cache:
        _reader_cache[key] = easyocr.Reader(list(languages), gpu=True)
    return _reader_cache[key]


def _preprocess(image_path: str) -> np.ndarray:
    img = cv2.imread(image_path)
    # Upscale x2 — EasyOCR lit mieux les petits caractères
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # CLAHE : améliore le contraste local (utile pour texte sur fond non uniforme)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    # Légère netteté
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    gray = cv2.filter2D(gray, -1, kernel)
    return gray


def run_ocr(image_path: str, languages: list, conf_threshold: float) -> list[dict]:
    reader = _get_reader(languages)
    preprocessed = _preprocess(image_path)
    raw = reader.readtext(preprocessed)
    results = []
    for bbox, text, confidence in raw:
        if confidence >= conf_threshold:
            # bbox coords sont sur l'image x2 — on remet à l'échelle originale
            xs = [p[0] / 2 for p in bbox]
            ys = [p[1] / 2 for p in bbox]
            results.append({
                "text": text,
                "confidence": round(confidence, 4),
                "bbox": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
            })
    return results


def save_annotated_image(image_path: str, results: list[dict], output_path: str) -> None:
    img = cv2.imread(image_path)
    for r in results:
        x1, y1, x2, y2 = r["bbox"]
        label = f"{r['text']} ({r['confidence']:.2f})"
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(img, label, (x1, max(y1 - 8, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    cv2.imwrite(output_path, img)


def main():
    img_dir = os.path.join(os.path.dirname(__file__), "..", "images")
    images = {
        "pomme":  os.path.join(img_dir, "pomme.png"),
        "orange": os.path.join(img_dir, "orange.png"),
        "banane": os.path.join(img_dir, "banane.png"),
    }
    languages = ["en", "fr"]
    threshold = 0.5

    for name, path in images.items():
        print(f"\n=== {name.upper()} ===")
        results = run_ocr(path, languages, threshold)
        if results:
            for r in results:
                print(f"  [{r['confidence']:.2f}] \"{r['text']}\"  bbox={r['bbox']}")
        else:
            print("  Aucun texte detecte au-dessus du seuil.")

        output = os.path.join(os.path.dirname(__file__), f"resultat_{name}_OCR.png")
        save_annotated_image(path, results, output)
        print(f"  >> Enregistre : {output}")


if __name__ == "__main__":
    main()
