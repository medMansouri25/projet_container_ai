"""
detect_pipeline_container.py
Pipeline complète : YOLO11m → crop → EasyOCR sur images de conteneurs maritimes.

Interface publique :
    run_pipeline(image_path, yolo_model_path, languages, ocr_threshold) -> list[dict]
    save_pipeline_result(image_path, detections, output_path) -> None
"""
import os
import sys
import cv2
import numpy as np
from ultralytics import YOLO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ocr"))
from detect_ocr_container import run_ocr, save_annotated_image


def run_pipeline(
    image_path: str,
    yolo_model_path: str,
    languages: list,
    ocr_threshold: float,
) -> list[dict]:
    """
    Pipeline YOLO11m → crop → EasyOCR sur une image de conteneur.

    YOLO11m ne connaît pas la classe "conteneur" (absent des 80 classes COCO).
    Il peut détecter d'autres classes présentes (truck, person…) ou rien du tout.
    Pour garantir l'extraction du Numéro ISO, une entrée "full_image" est toujours
    ajoutée : OCR sur l'image entière avec la stratégie 3 passes de detect_ocr_container.

    Retourne une liste de dict :
        {
            "class":           str,         # classe YOLO ou "full_image"
            "yolo_confidence": float|None,  # None pour l'entrée full_image
            "bbox":            [x1,y1,x2,y2],
            "ocr_results":     list[dict],  # résultats run_ocr sur cette zone
        }
    """
    model  = YOLO(yolo_model_path)
    img    = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Image illisible : {image_path}")
    h, w = img.shape[:2]

    detections = []

    # ── Détections YOLO (classes COCO quelconques) ─────────────────────────
    for result in model(image_path, verbose=False):
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cls_name  = result.names[int(box.cls[0])]
            yolo_conf = round(float(box.conf[0]), 4)

            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            # Sauvegarder le crop temporairement pour run_ocr (attend un chemin)
            tmp = os.path.join(os.path.dirname(__file__), "_tmp_crop.png")
            cv2.imwrite(tmp, crop)
            ocr_results = run_ocr(tmp, languages, ocr_threshold)
            os.remove(tmp)

            # Recaler les bbox OCR dans les coordonnées de l'image originale
            for r in ocr_results:
                bx1, by1, bx2, by2 = r["bbox"]
                r["bbox"] = [bx1 + x1, by1 + y1, bx2 + x1, by2 + y1]

            detections.append({
                "class":           cls_name,
                "yolo_confidence": yolo_conf,
                "bbox":            [x1, y1, x2, y2],
                "ocr_results":     ocr_results,
            })

    # ── Fallback full_image (toujours présent) ─────────────────────────────
    # YOLO rate systématiquement le conteneur → on applique run_ocr sur l'image
    # entière pour garantir la détection du Numéro ISO via la stratégie 3 passes.
    detections.append({
        "class":           "full_image",
        "yolo_confidence": None,
        "bbox":            [0, 0, w, h],
        "ocr_results":     run_ocr(image_path, languages, ocr_threshold),
    })

    return detections


def save_pipeline_result(
    image_path: str,
    detections: list[dict],
    output_path: str,
) -> None:
    """Dessine les détections YOLO (bleu) et textes OCR (vert) sur l'image."""
    img = cv2.imread(image_path)
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]

        if d["class"] != "full_image":
            # Box YOLO en bleu
            label = f"{d['class']} ({d['yolo_confidence']:.2f})"
            cv2.rectangle(img, (x1, y1), (x2, y2), (255, 100, 0), 2)
            cv2.putText(img, label, (x1, max(y1 - 8, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 100, 0), 2)

        # Textes OCR en vert
        for r in d["ocr_results"]:
            rx1, ry1, rx2, ry2 = r["bbox"]
            ocr_label = f"{r['text']} ({r['confidence']:.2f})"
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), (0, 220, 0), 1)
            cv2.putText(img, ocr_label, (rx1, max(ry1 - 5, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 0), 1)

    cv2.imwrite(output_path, img)


# ── Script standalone ──────────────────────────────────────────────────────

def main() -> None:
    base      = os.path.dirname(__file__)
    img_dir   = os.path.join(base, "..", "images")
    yolo_model = os.path.join(base, "..", "..", "yolo11m.pt")
    images = {
        "conteneur_maersk": "conteneur_maersk.jpg",
        "image1":           "image1.jpg",
        "image2":           "imahe2.jpg",
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
            detections = run_pipeline(path, yolo_model, languages, threshold)
            for d in detections:
                if d["class"] == "full_image":
                    print(f"  [full_image fallback]")
                else:
                    print(f"  YOLO [{d['yolo_confidence']:.2f}] {d['class']}  bbox={d['bbox']}")
                for r in d["ocr_results"]:
                    print(f"    OCR [{r['confidence']:.2f}] \"{r['text']}\"")
                if not d["ocr_results"]:
                    print(f"    OCR : aucun texte détecté.")
            output = os.path.join(base, f"resultat_{name}_pipeline.png")
            save_pipeline_result(path, detections, output)
            print(f"  >> Enregistré : {output}")
        except ValueError as e:
            print(f"  [SKIP] {e}")


if __name__ == "__main__":
    main()
