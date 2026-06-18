import easyocr
import os

reader = easyocr.Reader(['en', 'fr'], gpu=False)
images = {'pomme': 'pomme.png', 'orange': 'orange.png', 'banane': 'banane.png'}
base = os.path.dirname(__file__)

for name, fname in images.items():
    path = os.path.join(base, fname)
    raw = reader.readtext(path)
    print(f'\n=== {name.upper()} (seuil 0.0) ===')
    for bbox, text, conf in raw:
        print(f'  [{conf:.3f}] "{text}"')
    if not raw:
        print('  (aucune detection)')
