import os
import sys
import cv2
import numpy as np
from ultralytics import YOLO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ocr"))
from detect_ocr import run_ocr, _preprocess, _get_reader


def run_pipeline(
    image_path: str,
    yolo_model_path: str,
    languages: list,
    ocr_threshold: float,
) -> list[dict]:
    model = YOLO(yolo_model_path)
    yolo_results = model(image_path, verbose=False)

    img_orig = cv2.imread(image_path)
    detections = []

    for result in yolo_results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cls_name = result.names[int(box.cls[0])]
            yolo_conf = round(float(box.conf[0]), 4)

            # Crop de la zone détectée
            crop = img_orig[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            # Préprocessing du crop puis OCR
            crop_path = _save_temp_crop(crop)
            ocr_results = run_ocr(crop_path, languages, ocr_threshold)
            os.remove(crop_path)

            # Recalage des bbox OCR dans les coordonnées de l'image originale
            for r in ocr_results:
                bx1, by1, bx2, by2 = r["bbox"]
                r["bbox"] = [bx1 + x1, by1 + y1, bx2 + x1, by2 + y1]

            detections.append({
                "class": cls_name,
                "yolo_confidence": yolo_conf,
                "bbox": [x1, y1, x2, y2],
                "ocr_results": ocr_results,
            })

    return detections


def _save_temp_crop(crop: np.ndarray) -> str:
    tmp_path = os.path.join(os.path.dirname(__file__), "_tmp_crop.png")
    cv2.imwrite(tmp_path, crop)
    return tmp_path


def save_pipeline_result(image_path: str, detections: list[dict], output_path: str) -> None:
    img = cv2.imread(image_path)
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        # Box YOLO en bleu avec classe et confiance
        label_yolo = f"{d['class']} ({d['yolo_confidence']:.2f})"
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 100, 0), 2)
        cv2.putText(img, label_yolo, (x1, max(y1 - 8, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 100, 0), 2)
        # Textes OCR en vert
        for r in d["ocr_results"]:
            rx1, ry1, rx2, ry2 = r["bbox"]
            label_ocr = f"{r['text']} ({r['confidence']:.2f})"
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), (0, 220, 0), 1)
            cv2.putText(img, label_ocr, (rx1, max(ry1 - 5, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 0), 1)
    cv2.imwrite(output_path, img)


def main():
    base = os.path.dirname(__file__)
    img_dir = os.path.join(base, "..", "images")
    images = {
        "pomme":  os.path.join(img_dir, "pomme.png"),
        "orange": os.path.join(img_dir, "orange.png"),
        "banane": os.path.join(img_dir, "banane.png"),
    }
    yolo_model = os.path.join(base, "..", "..", "yolo11m.pt")
    languages = ["en", "fr"]
    threshold = 0.5

    for name, path in images.items():
        print(f"\n=== {name.upper()} ===")
        detections = run_pipeline(path, yolo_model, languages, threshold)

        if not detections:
            print("  Aucun objet detecte par YOLO.")
        for d in detections:
            print(f"  YOLO  [{d['yolo_confidence']:.2f}] {d['class']}  bbox={d['bbox']}")
            if d["ocr_results"]:
                for r in d["ocr_results"]:
                    print(f"    OCR [{r['confidence']:.2f}] \"{r['text']}\"  bbox={r['bbox']}")
            else:
                print("    OCR : aucun texte detecte dans la zone.")

        output = os.path.join(base, f"resultat_{name}_pipeline.png")
        save_pipeline_result(path, detections, output)
        print(f"  >> Enregistre : {output}")


if __name__ == "__main__":
    main()
