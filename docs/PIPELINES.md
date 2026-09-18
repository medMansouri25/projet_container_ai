# PIPELINES — Flux Image / Vidéo

> **Dernière mise à jour** : 2026-09-19

## Pipeline image (V1 — implémenté, en production)

```
Image (upload / capture caméra)
  │  _limit_image_size : plafonnée à 1600 px (photos téléphone)
  ▼
[Étage 1] YOLO conteneur (best_v2.pt)          → bbox conteneur, orientation
  ▼
[Étage 2] YOLO zone BIC (bic/best_v1.pt, seuil 0.15)
  │   · zone contrainte DANS le conteneur détecté (anti-voisin)
  │   · marge directionnelle 40 %/15 % (capture la case du chiffre de contrôle)
  │   · si AUCUN conteneur mais zone trouvée → gros plan, lecture directe
  ▼
[Étage 3] Lecture (_extract_bic, app.py)
  │   1. EasyOCR (principal) — pipeline durci :
  │      · _detect_text_orientation : lignes vs colonnes (les caractères, pas la boîte)
  │      · horizontal : variantes (brut/CLAHE/Otsu) × échelles, tri ordre de lecture
  │      · vertical empilé : masque HSV adaptatif → colonnes → OCR caractère/caractère
  │      · budget temps 25 s (zone) / 15 s (repli conteneur entier)
  │   2. YOLO caractères (char/best_v2.pt) — SECOURS si EasyOCR ne lit rien
  ▼
[Validation ISO 6346] resolve_bic (commun aux deux moteurs)
  │   · normalisation par position (O↔0, I↔1…), scoring des candidats
  │   · chiffre de contrôle : validation, réparation, solveur de caractère inconnu
  ▼
Proposition à l'agent (badge lu/recalculé/invalide + champ éditable)
  ▼
Validation humaine → POST /confirm → PostgreSQL          [invariant I3]
```

**Latence mesurée (VPS CPU)** : ~4-10 s horizontal net, ~20-40 s vertical difficile.
Warmup au démarrage du conteneur (modèles préchargés, EasyOCR cuit dans l'image Docker).

### Variante navigateur multi-codes (Capture passage, 2026-07-28)

Sur import d'image dans `capture.html` (cible conteneur), la détection tourne
**en local** (bic.onnx via onnxruntime-web) et l'OCR serveur est appelé sur
**chaque** zone code bic détectée — pas seulement la meilleure :

```
bic.onnx (local, seuil 0.15) → N zones code bic
  │   déduplication IoU > 0.5, tri par score, plafond 20 zones
  ▼
POST /api/ocr-crop × N — SÉQUENTIEL (une requête à la fois)
  │   [CONTRAINTE VPS] chaque OCR a ~25 s de budget CPU ; des requêtes
  │   simultanées se partagent le CPU et dépassent TOUTES leur budget
  ▼
Déduplication par code lu → une carte par code dans « Codes détectés »
  ▼
Validation humaine : bouton Confirmer par carte           [invariant I3]
```

Si aucun code lisible → repli sur l'OCR de la meilleure zone (comportement V1).
Le statut distingue « Aucun code lisible » de « Serveur OCR injoignable ».
Cas d'usage : photos de parc avec plusieurs conteneurs empilés visibles.

### Source caméra RTSP dans `capture.html` (ADR-22, 2026-09-19)

4ᵉ source pour la même détection client ci-dessus (à côté de photo/vidéo importées et
webcam) : le backend **local** (`rtsp.py`, ADR-20) relaie un flux RTSP en MJPEG,
consommé par `capture.html` via `<img crossorigin="anonymous">`. `detect()`
(`webdetect.js`) dessine sa source via `ctx.drawImage()` — identique pour un
`<video>` ou un `<img>`, donc **aucune détection serveur ajoutée**, seulement une
source de frames de plus pour le pipeline ONNX déjà en place.

```
Téléphone (rtsp://…)
  ▼
Backend LOCAL — rtsp.py (ADR-20) : relais MJPEG, jamais de YOLO/OCR ici
  ▼
<img id="rtsp-preview"> dans capture.html (backend local requis, apiBase() reste la prod)
  ▼
── même pipeline client que webcam/vidéo (ONNX local → crop → OCR serveur) ──
```

**[CONTRAINTE RÉSEAU]** Ne fonctionne que si le navigateur peut joindre
`http://localhost:5000` — un VPS de production distant ne peut pas atteindre une
adresse RTSP sur le réseau local du téléphone. Cette source restera donc toujours un
usage **poste local**, jamais accessible depuis `containerai-marsa-maroc.online` tel quel.

## Pipeline plaque (service Plaque — pipeline construit 2026-07-18)

```
Image (upload / capture caméra)
  │  _limit_image_size : plafonnée à 1600 px
  ▼
[Étage 1] YOLO zone plaque (plaque/best_vN.pt)   → bbox plaque + crop
  │   · None si modèle absent (trainImmat.bat non lancé) → found:false
  ▼
[Étage 2] EasyOCR arabe+anglais (pipeline/plaque.py)
  │   · allowlist chiffres + lettres de catégorie ; variantes brut/CLAHE × échelles
  │   · budget temps 12 s
  ▼
[Normalisation format marocain] resolve_plaque
  │   · la lettre arabe sépare série (gauche) / région (droite)
  │   · lettre non lue → '?' (validation de FORME, pas de clé de contrôle)
  ▼
Proposition à l'agent : champ pré-rempli « <série> - <lettre> - <région> »
  ▼
Validation humaine                                        [invariant I3]
```

Miroir du flux BIC mais **sans clé mathématique** : la plaque marocaine n'a pas
de chiffre de contrôle → le juge de paix est la **forme**, plus faible, d'où le
rôle accru de la validation humaine. Entrée `POST /api/scan-plaque`.

## Pipeline vidéo — état actuel (Labo, expérimental, 2026-09-18)

Implémenté dans **`Application/backend/labo.py`** (`stream_video_detection`) et branché
sur `POST /api/labo/detect-video` (`app.py`) — outil de dev/évaluation, **pas encore
intégré à l'app de production** (`/scan`, `/api/scan`). Réutilise tel quel le pipeline
image (`run_detect` + `read_zones`, étages 1-3 + validation ISO 6346 ci-dessus) :
aucune logique YOLO/OCR dupliquée.

```
Vidéo importée (fichier, ou enregistrement RTSP — ADR-20, non testé avec caméra réelle)
  ▼
Échantillonnage FIXE 5 FPS (VIDEO_ANALYSIS_FPS)
  │   cap.grab() sur TOUTES les frames (avance sans décoder, gratuit)
  │   cap.retrieve() SEULEMENT sur la frame retenue (1 frame décodée / step)
  ▼
Pour chaque frame retenue : run_detect() (annotate=False) → read_zones()
  │   = EXACTEMENT le même détecteur + la même boucle OCR que l'image
  ▼
Agrégation temporelle par code exact (vote : occurrences, meilleure confiance,
  authentique > recalculé)
  ▼
Consolidation floue (_consolidate_codes, ≤3 caractères d'écart à longueur égale,
  toujours comparé au représentant du cluster — jamais proche-en-proche)
  ▼
Liste de codes uniques, streamée en NDJSON (meta → progress × N → done)
```

**Ce que ce pipeline N'EST PAS** : il n'y a **aucun tracking d'objet** — chaque frame
échantillonnée est traitée indépendamment (nouvelle détection à chaque fois), la
déduplication se fait entièrement **a posteriori** sur les codes lus. C'est plus simple
et plus robuste (pas de perte de piste si l'objet sort/rentre du cadre) mais coûte une
inférence YOLO par frame échantillonnée — acceptable à 5 FPS sur GPU local, à
reconsidérer avant un déploiement CPU/VPS.

Testé de bout en bout sur vidéo réelle (matériel tuteur) : code `CAIU6563528` détecté
sur 14/34 frames analysées, chiffre de contrôle réparé automatiquement.

## Pipeline vidéo — cible SPEC_V2 §7 (tracking, non commencé)

```
Flux vidéo (caméra téléphone, puis RTSP en V3)
  ▼
Normalisation en frames (cadence FPS maîtrisée)
  ▼
Tracking : identifier et SUIVRE chaque objet entre frames
  ▼
Sélection de frame stable/nette par objet suivi
  ▼
── même pipeline aval que l'image (étages 1-3 + validation) ──
```

**[EXIGENCE SPEC]** L'OCR n'est jamais exécuté sur chaque frame : le tracking suit
l'objet, la lecture est déclenchée **une seule fois** sur une frame choisie.
C'est le cœur de la maîtrise de latence (risque R1). **Écart avec l'état actuel** :
le Labo réexécute OCR sur chaque frame échantillonnée (pas de cache par objet suivi) —
acceptable en labo (dédoublonné après coup), à corriger avant toute intégration
production à fort volume.

**[EXIGENCE SPEC]** Le pipeline aval est **commun** image/vidéo (invariant I2) —
la couche capture normalise, rien d'autre ne change. **Déjà respecté** par le Labo
(même `run_detect`/`read_zones` que l'image).

### Briques à construire pour la cible SPEC_V2

| Brique | Statut |
|---|---|
| Échantillonnage FPS maîtrisé | ✅ fait (Labo, 5 FPS fixe configurable) |
| Réutilisation du pipeline aval image | ✅ fait (Labo) |
| Capture vidéo web (getUserMedia) | à faire |
| Tracking (ByteTrack/BoT-SORT, `model.track()`) | à faire |
| Sélection de frame par netteté (variance du Laplacien) + stabilité bbox | à faire |
| Anti-redéclenchement (un objet suivi = une seule lecture, cache par track_id) | à faire — le Labo s'en passe (dédup a posteriori) |
| Intégration dans l'app de production (`/scan`) | à faire |
