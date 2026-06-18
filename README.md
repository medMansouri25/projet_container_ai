# ProjetContainer_AI

Prototype de détection et extraction automatique des données affichées sur des **conteneurs maritimes**, à partir d'images ou de flux caméra.

Pipeline IA : **YOLO11m** (détection) → crop → **EasyOCR** (extraction texte) → JSON

---

## Stack technique

| Composant | Version |
|-----------|---------|
| Python | 3.11.9 |
| PyTorch (CUDA 12.8) | 2.11.0+cu128 |
| Ultralytics YOLO | 8.4.68 |
| EasyOCR | 1.7.2 |
| OpenCV | 4.13.0 |
| Flask | 3.1.3 |

> GPU recommandé : NVIDIA avec driver ≥ 520 (testé sur RTX 5070 Ti)  
> CPU supporté mais beaucoup plus lent.

---

## Installation

```bat
setup.bat
```

Le script crée automatiquement le `.venv`, installe PyTorch CUDA 12.8 et toutes les dépendances.

Activation manuelle du venv :
```bat
.venv\Scripts\activate.bat
```

---

## Structure du projet

```
ProjetContainer_AI/
├── setup.bat                    ← Installation automatique
├── README.md
├── SmartContainer_AI_SDD_v1.md  ← Spécification technique complète
│
└── TestYolo/
    ├── yolo11m.pt               ← Modèle YOLO11 medium (téléchargé auto)
    └── testFruit/               ← Tests de validation YOLO + OCR sur fruits
        ├── images/              ← Images de test (pomme, orange, banane)
        ├── yolo/                ← Détection YOLO seule
        │   └── detect_fruit.py
        ├── ocr/                 ← OCR standalone (EasyOCR)
        │   ├── detect_ocr.py
        │   └── test_detect_ocr.py
        └── pipeline/            ← Pipeline complète YOLO → crop → OCR
            ├── detect_pipeline.py
            └── test_detect_pipeline.py
```

---

## Lancer les tests

```bat
REM Depuis la racine du projet, avec .venv activé

REM Tests OCR standalone
python -m pytest TestYolo\testFruit\ocr\ -v

REM Tests pipeline YOLO + OCR
python -m pytest TestYolo\testFruit\pipeline\ -v
```

Résultats attendus : **8/8 tests PASSED**

---

## Lancer la pipeline sur les images de test

```bat
REM Détection YOLO seule
python TestYolo\testFruit\yolo\detect_fruit.py

REM OCR standalone
python TestYolo\testFruit\ocr\detect_ocr.py

REM Pipeline complète YOLO → OCR
python TestYolo\testFruit\pipeline\detect_pipeline.py
```

---

## Résultats de validation (fruits)

| Image | YOLO | OCR |
|-------|------|-----|
| pomme.png | apple 91% | "1829" (182g — confusion g/9 connue) |
| orange.png | orange 80% | "Orange" |
| banane.png | banana 95% | détecté |

> Note : les images de fruits servent uniquement à valider la pipeline.  
> La confusion `g`→`9` ne s'applique pas aux codes conteneurs (majuscules uniquement).

---

## Prochaines étapes

- [ ] Test pipeline sur images réelles de conteneurs maritimes
- [ ] Fine-tuning YOLO sur dataset conteneurs annotés
- [ ] API Flask (POST `/api/detect`, POST `/api/save`)
- [ ] Déploiement VPS Contabo + Cloudflare Tunnel

Voir `SmartContainer_AI_SDD_v1.md` pour la spécification complète.
