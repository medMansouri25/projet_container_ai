# AI_MODELS — Modèles IA

> **Dernière mise à jour** : 2026-07-16

## Convention de versionnement (commune à tous les modèles)

```
Application/models/<nom>/
├── best_v1.pt, best_v2.pt, …   (optimizer strippé, ~19-38 Mo)
└── metadata.json               (classes, métriques, run, date, epochs, hyperparams)
```
- Chargement : dernier `best_vN` via `metadata.json` ; override par env
  (`MODEL_PATH`, `BIC_MODEL_PATH`, `CHAR_MODEL_PATH`) ; cache en mémoire.
- Entraînement : `Application/ml/train.py` (fine-tuning incrémental depuis le dernier best),
  base par défaut `yolo11m.pt` (téléchargé automatiquement).
- Tous embarqués dans l'image Docker (`COPY Application/models/`).

## Modèles en production

### 1. Détecteur de conteneur — `models/best_v2.pt`

| | |
|---|---|
| Base / taille | YOLO11m fine-tuné, 2 classes (`Conteneur`, `Fruit`†) |
| Données | 7586 images (raw/Conteneur + expérience Fruit), benchmark figé 1001 img |
| Métriques (benchmark) | **mAP50 90.7 %** (baseline 70.5 %), recall Fruit 40.9→86.2 % |
| Rôle | Étage 1 : bbox conteneur + orientation |

† La classe Fruit provient de l'expérience d'équilibrage v_A/v_B (voir [DECISIONS.md](DECISIONS.md) ADR-2) ; ses données sources ont été purgées, la classe reste dans le modèle.

### 2. Spécialiste zone BIC — `models/bic/best_v1.pt`

| | |
|---|---|
| Base | YOLO11m, 1 classe (`NumeroBIC`) |
| Données | `datasetEnt` — 6289 gros plans Roboflow de zones de code |
| Métriques (valid) | **mAP50 99.5 %**, P 99.8 %, R 99.7 % |
| Rôle | Étage 2 : localiser le marquage (seuil 0.15, contraint au conteneur) |
| Entraînement | `train_bic.bat` |

**Décision clé (ADR-3)** : modèle **séparé** plutôt que classe ajoutée à best_v2 —
un fine-tuning BIC-only aurait effacé Conteneur/Fruit (oubli catastrophique démontré par v_B).

### 3. Lecteur caractères — `models/char/best_v2.pt` (architecture du tuteur)

| | |
|---|---|
| Base | **YOLO11s** (léger : 9.4M params, ~2× plus rapide sur CPU AMD du VPS) |
| Classes | **36** : 0-9 + A-Z — OCR-par-détection |
| Données | dataset tuteur « o_c » (Roboflow) : 2011 train / 355 valid / 613 test — ~99 % plaques d'immatriculation |
| Métriques | détection : **mAP50 94-95.75 %** (test tuteur) |
| Rôle | Étage 3 **en secours** d'EasyOCR (voir ADR-6) |
| Entraînement | `train_char.bat` · préparation : `Application/ml/prepare_char_dataset.py` |

**Benchmark réel conteneurs** (3 codes connus, mode app) : EasyOCR 3/3, char 1/3 →
char rétrogradé en secours. Cause : pas de données *conteneurs* annotées caractère.
**Amélioration identifiée** : annoter `datasetEnt` au niveau caractère.

### 4. EasyOCR (moteur principal de lecture)

Pas un modèle entraîné par nous — bibliothèque durcie par ~600 lignes de logique :
orientation par caractères, masque HSV adaptatif, lecteur de colonnes empilées,
normalisation par position, scoring, **validation/réparation/solveur ISO 6346**
(`Application/backend/pipeline/ocr.py`). Modèles EasyOCR cuits dans l'image Docker.

## Historique / purgé

- `best_v1.pt` (baseline 20 epochs, mAP50 70.5 %) — conservé pour comparaison
- `exp_A`/`exp_B` (expérience équilibrage) — purgés (2026-07-15), conclusions dans ADR-2
- POC TestYolo (yolo11m COCO + EasyOCR brut) — supprimé du dépôt (récupérable dans l'historique git)

## Modèles cibles (SPEC_V2, à créer)

| Service | Modèle pressenti | Blocage |
|---|---|---|
| API Plaque | YOLO11s détection + lecture (nouveau format marocain) | dataset (Q2) |
| API Driver | détection CIN/permis + OCR champs | dataset |
| API Documents | extraction de champs (DUM, booking) | manuscrit = Q6 |
