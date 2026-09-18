# SmartContainer_AI — Marsa Maroc

Plateforme IA pour **automatiser l'enregistrement des camions** entrant au terminal
portuaire (Marsa Maroc, Port de Casablanca). Le système reconnaît automatiquement les
informations visibles sur un **conteneur maritime** (code BIC, ISO 6346), propose la
lecture à l'agent, et n'enregistre **que sur validation humaine**.

> **Principe fondateur** : l'IA propose, l'agent humain dispose. Aucun enregistrement automatique.

En production : **[containerai-marsa-maroc.online](https://containerai-marsa-maroc.online)**

---

## État du projet

| Version | Contenu | Statut |
|---|---|---|
| **V1 — Image** | Scanner BIC : upload/caméra → détection → OCR → validation → historique + dashboard | ✅ **déployée en production** |
| **V2 — Vidéo** | Import vidéo → échantillonnage 5 FPS → même pipeline que l'image → agrégation/déduplication des codes | 🧪 expérimental, dans le **Labo** (`/labo`), pas encore intégré à l'app de production |
| **Caméra RTSP** | Téléphone en source caméra distante → aperçu live → enregistrement → pipeline vidéo | 🔜 à construire (front déjà câblé) |
| **V3 — Extension navigateur** | Interface finale "BIC Detector" pilotant le backend local | 🔜 à construire |

Détail complet, invariants et questions ouvertes : [SDD/SPEC_V2.md](SDD/SPEC_V2.md) ·
suivi d'avancement : [docs/ROADMAP.md](docs/ROADMAP.md) · décisions d'architecture :
[docs/DECISIONS.md](docs/DECISIONS.md).

## Pipeline de détection (V1, en production)

```
Image (upload / caméra)
  │
  ▼
[1] YOLO conteneur (best_v2.pt)         → bbox conteneur + orientation
  ▼
[2] YOLO zone code BIC (bic/best_v1.pt) → localise le marquage (mAP50 99.5 %)
  ▼
[3] Lecture : EasyOCR (principal) + YOLO caractères (secours si EasyOCR échoue)
  ▼
Validation ISO 6346 (chiffre de contrôle : validation / réparation / solveur)
  ▼
Proposition à l'agent → validation humaine → PostgreSQL (Neon)
```

| Métrique (benchmark figé) | Valeur |
|---|---|
| Détecteur conteneur — mAP50 | 90.7 % |
| Spécialiste zone BIC — mAP50 | 99.5 % |
| Lecteur caractères (secours) — mAP50 | 95.75 % |

Détails et historique des modèles : [docs/AI_MODELS.md](docs/AI_MODELS.md).

## Stack technique

| Composant | Détail |
|---|---|
| Détection | Python 3.11, PyTorch (CUDA 12.8 en local / CPU sur le VPS), Ultralytics YOLO11 |
| Lecture | EasyOCR + moteur caractère YOLO (36 classes) |
| Backend | Flask, OpenCV |
| Persistance | PostgreSQL (Neon, serverless) |
| Front production | HTML/CSS/JS vanilla, hébergé sur Vercel |
| Déploiement | Docker + Caddy (TLS auto) sur VPS, CI GitHub Actions |

## Structure du projet

```
ProjetMarsa/
├── Application/
│   ├── backend/
│   │   ├── app.py                  ← app Flask de production (scan/confirm/history/dashboard + API JSON)
│   │   ├── db.py                   ← persistance PostgreSQL (psycopg2)
│   │   ├── pipeline/
│   │   │   ├── detector.py         ← YOLO conteneur + zone BIC
│   │   │   ├── ocr.py              ← EasyOCR + validation ISO 6346
│   │   │   ├── char_reader.py      ← lecteur de caractères (secours OCR)
│   │   │   └── plaque.py           ← lecture plaque marocaine (service Plaque)
│   │   ├── labo.py, labo.html      ← 🔬 Labo : comparaison de modèles, image/vidéo (outil de dev, jamais en prod)
│   │   ├── templates/, static/     ← rendu HTML direct (sans le front Vercel)
│   │   └── uploads/, recordings/   ← fichiers runtime (hors git)
│   ├── ml/                         ← dataset versionné, entraînement, évaluation, benchmarks
│   ├── models/                     ← poids YOLO versionnés (best_vN.pt + metadata.json)
│   ├── dataset/                    ← config YOLO (data.yaml, classes.json)
│   └── reports/                    ← rapports d'entraînement/évaluation
├── frontend/                       ← front statique déployé sur Vercel (scanner, historique, dashboard)
├── SDD/SPEC_V2.md                  ← source de vérité de l'intention produit
├── docs/                           ← documentation vivante (12 documents, tenue à jour à chaque changement)
├── RessourceFourni/                ← matériel du tuteur (modèles, vidéos de test)
├── scripts/                        ← scripts d'exploitation (tunnel, etc.)
├── Dockerfile, setup.bat           ← build image / environnement local
└── train*.bat                      ← lancement des entraînements (conteneur, BIC, char, plaque)
```

## Installation (environnement local avec GPU)

```bat
setup.bat
```

Crée `.venv`, installe PyTorch CUDA 12.8 puis les dépendances du projet
(`requirements.txt` : ultralytics, easyocr, opencv, flask, psycopg2). Sans GPU NVIDIA,
`setup.bat` retente automatiquement une installation CPU de PyTorch.

Activation manuelle :
```bat
.venv\Scripts\activate.bat
```

Variables d'environnement (`.env` à la racine, voir [docs/DATABASE.md](docs/DATABASE.md)) :
```
DATABASE_URL=postgresql://...   # PostgreSQL Neon — requis pour /confirm, /history, /dashboard
```
Sans `DATABASE_URL`, le scanner (`/scan`) et le **Labo** (`/labo`) fonctionnent quand
même — seule la persistance (historique/dashboard) est indisponible.

## Lancer l'application

```bat
python Application\backend\app.py
```
→ `http://localhost:5000`

| Page | Rôle |
|---|---|
| `/` | Scanner BIC (upload + caméra) |
| `/history` | Historique des scans confirmés |
| `/dashboard` | KPIs et graphiques |
| `/labo` | 🔬 Comparaison de modèles — image (stable), vidéo (expérimental), caméra RTSP (à venir) |

API JSON complète (consommée par le front Vercel) : [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md).

## Pipeline ML (entraînement, standalone)

```bat
python Application\ml\dataset.py version      REM régénère current/ depuis raw/
python Application\ml\train.py                REM fine-tuning incrémental
python Application\ml\evaluate.py              REM mAP, PR curves, matrice de confusion
python Application\ml\predict.py chemin\image.jpg
```
Entraînements dédiés : `trainConteneur.bat` · `trainBIC.bat` · `train_char.bat` · `trainImmat.bat`.

## Tests

Méthode AB (voir [CLAUDE.md](CLAUDE.md)) : les tests sont écrits pendant une mission
(mocks aux frontières ultralytics/easyocr/psycopg2) puis **supprimés une fois verts** —
il n'y a donc pas de suite de tests persistante dans le dépôt. `pytest` (`pip install pytest`)
suffit pour toute mission en cours.

## Docker (déploiement VPS)

```bash
docker build -t smartcontainer-ai .
docker run -p 5000:5000 --env-file .env smartcontainer-ai
```

## Documentation

Toute décision structurante est tracée en ADR et la documentation reflète l'état réel
du code (jamais l'inverse) — voir [CLAUDE.md](CLAUDE.md) pour la règle complète.

| Document | Contenu |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | Vision globale, état d'avancement par version |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture logicielle actuelle + cible |
| [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) | Contrats REST (production + Labo) |
| [docs/PIPELINES.md](docs/PIPELINES.md) | Flux de traitement image / vidéo |
| [docs/AI_MODELS.md](docs/AI_MODELS.md) | Modèles IA, métriques, versionnement |
| [docs/DATABASE.md](docs/DATABASE.md) | Modèle de données PostgreSQL |
| [docs/SECURITY.md](docs/SECURITY.md) | Sécurité, CORS |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, VPS, CI/CD |
| [docs/DECISIONS.md](docs/DECISIONS.md) | ADR — historique des décisions d'architecture |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Prochains chantiers |
| [détail partie labo.md](détail%20partie%20labo.md) | Guide d'implémentation détaillé du Labo (image/vidéo/RTSP) |
