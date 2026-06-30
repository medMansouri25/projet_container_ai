# ProjetContainer_AI

Détection automatique de **conteneurs maritimes** par vision par ordinateur.  
Pipeline IA : **YOLO11m fine-tuné** → prédiction bbox + score de confiance.

---

## Résultats d'entraînement (baseline YOLO11m)

| Métrique | Valeur |
|----------|--------|
| Precision | **0.999** |
| Recall | **1.000** |
| mAP50 | **0.995** |
| mAP50-95 | **0.995** |

- Dataset : **5 025 images** de conteneurs maritimes (1920x1080)
- Split : 70% train / 20% valid / 10% test
- Classe : `conteneur` (1 classe)
- Epochs : 50 (early stopping patience=10)
- GPU : RTX 5070 Ti, CUDA 12.8

---

## Stack technique

| Composant | Version |
|-----------|---------|
| Python | 3.11.9 |
| PyTorch (CUDA 12.8) | 2.11.0+cu128 |
| Ultralytics YOLO | 8.4.68 |
| OpenCV | 4.13.0 |
| Flask | 3.1.3 |

---

## Structure du projet

```
ProjetContainer_AI/
├── Application/
│   ├── backend/
│   │   ├── app.py              <- API Flask (upload / train / predict / gallery)
│   │   ├── trainer.py          <- Wrapper entrainement pour l'API web
│   │   ├── predictor.py        <- Wrapper inference pour l'API web
│   │   ├── templates/
│   │   │   ├── gallery.html    <- UI selection + drag&drop images
│   │   │   └── predict.html    <- UI prediction avec canvas bbox
│   │   └── tests/
│   └── ml/
│       ├── analyze_dataset.py  <- Analyse du dataset (counts, classes, bbox)
│       ├── clean_dataset.py    <- Nettoyage orphelins + correction nc
│       ├── train_baseline.py   <- Fine-tuning YOLO11m baseline (50 epochs)
│       ├── evaluate.py         <- Evaluation complete (mAP, PR curves, confusion matrix)
│       ├── predict.py          <- Inference sur nouvelles images
│       ├── runs/
│       │   └── baseline/train/weights/best.pt  <- Modele entraine
│       └── tests/
├── Application/data/
│   └── data.yaml               <- Config dataset YOLO
├── Dockerfile
├── requirements.txt
└── setup.bat
```

---

## Installation

```bat
setup.bat
```

Cree automatiquement le `.venv`, installe PyTorch CUDA 12.8 et toutes les dependances.

Activation manuelle :
```bat
.venv\Scripts\activate.bat
```

---

## Pipeline ML (standalone)

```bat
python Application/ml/analyze_dataset.py
python Application/ml/clean_dataset.py
python Application/ml/train_baseline.py
python Application/ml/evaluate.py
python Application/ml/predict.py chemin/image.jpg
```

---

## API Flask

```bat
python Application/backend/app.py
```

| Route | Methode | Description |
|-------|---------|-------------|
| `/` | GET | Accueil |
| `/predict-page` | GET | UI prediction |
| `/upload` | POST | Upload images |
| `/gallery` | GET | Galerie images |
| `/train` | POST | Lancer entrainement |
| `/train/status` | GET | Statut entrainement |
| `/predict` | POST | Inference sur image |

---

## Lancer les tests

```bat
python -m pytest Application/ml/tests/ -v
python -m pytest Application/backend/tests/ -v
```

---

## Docker

```bash
docker build -t projetcontainer-ai .
docker run -p 5000:5000 projetcontainer-ai
```
