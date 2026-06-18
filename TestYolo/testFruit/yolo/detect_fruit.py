import os
from ultralytics import YOLO

BASE = os.path.dirname(__file__)
model = YOLO(os.path.join(BASE, "..", "..", "yolo11m.pt"))

IMG_DIR = os.path.join(BASE, "..", "images")
images = [os.path.join(IMG_DIR, f) for f in ["pomme.png", "orange.png", "banane.png"]]

for image_path in images:
    results = model(image_path)
    
    print(f"\n=== Résultats pour : {image_path} ===")
    
    if len(results[0].boxes) == 0:
        print("Aucun objet détecté.")
        continue
    
    for box in results[0].boxes:
        classe_id = int(box.cls[0])
        nom_classe = model.names[classe_id]
        confiance = float(box.conf[0])
        coords = box.xyxy[0].tolist()
        
        print(f"Objet    : {nom_classe}")
        print(f"Confiance: {confiance:.2%}")
        print(f"Position : x1={coords[0]:.0f}, y1={coords[1]:.0f}, x2={coords[2]:.0f}, y2={coords[3]:.0f}")
    
    # Sauvegarde image avec bounding box
    results[0].save(os.path.join(BASE, f"resultat_{os.path.basename(image_path)}"))
    print(f"→ Image sauvegardée : resultat_{image_path}")