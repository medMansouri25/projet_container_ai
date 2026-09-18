# ARCHITECTURE — Architecture logicielle

> **Dernière mise à jour** : 2026-09-19

## Architecture actuelle (V1 en production)

```
Navigateur / téléphone
        │ HTTPS
        ▼
┌─────────────────────────────┐
│ Front statique (Vercel)     │  frontend/ — HTML/CSS/JS vanilla
│ containerai-marsa-maroc.online  (+ www)
└─────────────┬───────────────┘
              │ fetch HTTPS (CORS)
              ▼
┌─────────────────────────────┐
│ api.containerai-marsa-maroc.online
│ Caddy (reverse proxy, TLS auto Let's Encrypt)
│         │ localhost:5001
│         ▼
│ Docker « smartcontainer »   │  VPS Contabo (AMD EPYC, sans GPU)
│  Flask (app.py)             │
│  ├── pipeline/detector.py   │  YOLO conteneur + YOLO zone BIC
│  ├── pipeline/ocr.py        │  EasyOCR + logique ISO 6346
│  ├── pipeline/char_reader.py│  YOLO caractères (secours)
│  └── db.py                  │  psycopg2
└─────────────┬───────────────┘
              ▼
      Neon PostgreSQL (cloud)
```

### Composants

| Composant | Rôle | Fichiers |
|---|---|---|
| **Front** | Scanner + Capture passage (upload image/vidéo, caméra getUserMedia, **caméra RTSP**), validation, historique, dashboard | `frontend/` |
| **Backend Flask** | Routes HTML (usage direct) + **API JSON** (front Vercel) | `Application/backend/app.py` |
| **Pipeline détection** | 3 étages : conteneur → zone BIC → lecture | `Application/backend/pipeline/` |
| **Persistance** | Table `scans` (dossiers validés) | `Application/backend/db.py` |
| **ML tooling** | dataset versionné, entraînement, évaluation, benchmarks | `Application/ml/` |
| **Labo** (dev, local uniquement — jamais déployé sur le VPS) | comparaison de modèles, image/vidéo/RTSP, écrit **jamais** dans PostgreSQL | `Application/backend/labo.py`, `labo.html`, `rtsp.py` (source caméra découplée de YOLO/OCR) |
| **Extension "BIC Detector"** (prototype, `Application/Extension/`) | Interface finale RTSP → live → enregistrement → analyse, pilote le backend local via HTTP | `manifest.json` (Manifest V3), `src/popup/`, `src/services/backend-api.js` (seul point d'appel réseau) — voir [Extension/README.md](../Application/Extension/README.md) |

### Deux pipelines de détection distincts (ADR-22)

`capture.html` (prod) détecte **côté navigateur** (ONNX/onnxruntime-web,
`frontend/js/webdetect.js`) — conçu pour le VPS CPU (ADR-7), seul le crop OCR part au
serveur. Le Labo (`/labo`) détecte **côté serveur** (YOLO `.pt`/ultralytics,
`Application/backend/labo.py`) — nécessite un GPU local, outil de dev uniquement.
La caméra RTSP de `capture.html` (ADR-22) réutilise le **relais MJPEG** du backend
local (`rtsp.py`, ADR-20) mais la **détection** reste côté navigateur — elle ne
déclenche jamais le pipeline serveur du Labo. Ne pas confondre les deux en modifiant
l'un en pensant affecter l'autre.

### Séparation actuelle vs invariant I1 (SPEC_V2)

La V1 est un **monolithe Flask** : pipeline IA et logique métier cohabitent dans le même processus.
C'est un écart **assumé et documenté** avec la cible « services IA indépendants » — acceptable en V1
(un seul service métier, un seul type d'entité), à résorber lors de l'ajout des services Plaque/Driver/Documents.
La frontière est déjà préparée dans le code : `pipeline/` ne contient **aucune logique métier**
(pas de DB, pas de validation, image → dict), `app.py` orchestre.

## Architecture cible (SPEC_V2 §6)

```
Sources (image | vidéo | RTSP)
        ▼
Couche de capture & normalisation (vidéo = suite d'images, tracking)
        ▼
Application métier (orchestrateur)
  ├── appelle en parallèle → API Container (existe : pipeline actuel)
  │                          API Plaque   (à créer)
  │                          API Driver   (à créer)
  │                          API Documents(à créer)
  ├── Agrégation / Linking → dossier de passage
  ├── Validation humaine
  └── Persistance
```

**Contrat service IA** : entrée = image, sortie = JSON `{résultat, confiance, bbox}`,
sans état, sans métier, sans appel entre services.

## Chemin de migration V1 → cible

1. Extraire le pipeline conteneur actuel en **service API Container** autonome (le contrat existe déjà de fait : `crop → {bic, valid, confidence, bbox}`)
2. L'orchestrateur (Flask actuel) devient l'application métier : linking + validation + persistance
3. Ajouter les services Plaque / Driver / Documents sur le même contrat
4. Ajouter la couche capture vidéo (tracking + sélection de frame) devant l'orchestrateur

## Règles pour tout nouveau code

- Aucune notion métier dans `pipeline/` (invariant I1)
- Tout nouveau modèle IA suit la mécanique versionnée `models/<nom>/best_vN.pt` + `metadata.json` + env `<NOM>_MODEL_PATH` (voir [AI_MODELS.md](AI_MODELS.md))
- Les ports VPS restent scopés : 5001 (app), 80/443 (Caddy) — invariant I9
