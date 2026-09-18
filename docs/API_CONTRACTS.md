# API_CONTRACTS — Contrats REST

> **Dernière mise à jour** : 2026-09-18 · Base : `https://api.containerai-marsa-maroc.online`

## API actuelle (V1, implémentée dans `Application/backend/app.py`)

CORS ouvert sur `/api/*` et `/uploads/*` (front hébergé sur Vercel).

### POST /api/scan

Analyse une image de conteneur. Entrée : `multipart/form-data`, champ `image` (jpg/png/webp/bmp).

```json
// 200
{
  "found": true,
  "container_found": true,          // false = gros plan, lecture zone directe
  "bic": "TLNU9101464",
  "valid": true,                    // chiffre de contrôle ISO 6346 OK
  "corrected": false,               // true = chiffre recalculé → à vérifier
  "bic_zone_found": true,
  "ocr_confidence": 0.98,
  "yolo_confidence": 0.72,
  "vertical": false,                // orientation de la ROI lue
  "raw_text": "TLNU | 910146 4",
  "image_url": "https://api…/uploads/xxx_annotated.jpg",
  "image_name": "xxx.jpg",
  "engine": "easyocr"               // moteur ayant lu : easyocr | char
}
// 400 : { "error": "Format non supporte : .gif" }
```

### POST /api/scan-plaque

Analyse une image de camion/plaque. Entrée : `multipart/form-data`, champ `image`.
YOLO (zone plaque `models/plaque`) → EasyOCR arabe+anglais → format marocain.

```json
// 200 — plaque détectée
{
  "found": true,
  "plaque": "12345 - أ - 6",         // <serie> - <lettre> - <region>
  "valid": true,                     // validation de FORME (pas de cle de controle)
  "left": "12345", "letter": "أ", "right": "6",
  "ocr_confidence": 0.83,
  "yolo_confidence": 0.91,
  "raw_text": "12345 | أ | 6",
  "image_url": "https://api…/uploads/xxx_plaque.jpg",
  "image_name": "xxx.jpg"
}
// 200 — rien : { "found": false, "reason": "modele plaque absent : lancez trainImmat.bat" | "aucune plaque detectee", … }
// 400 : { "error": "Format non supporte : .gif" }
```

Lettre arabe non reconnue → `letter: "?"`, `valid: false` (à confirmer par l'agent,
invariant I3). Aucune persistance dédiée pour l'instant (V1 = conteneur seul).

### Dossier de passage (V2 — orchestrateur)

Ces endpoints **persistent des valeurs déjà confirmées** par l'agent (les propositions
viennent de `/api/scan` et `/api/scan-plaque`). Modèle symétrique (ADR-12) : 0..1
conteneur + 0..1 camion, validable dès ≥1 entité.

| Méthode / route | Rôle | Corps → réponse |
|---|---|---|
| `POST /api/dossiers` | ouvrir un passage | `{source, voie?}` → `201 {id, statut:"en_attente"}` |
| `POST /api/dossiers/<id>/conteneur` | rattacher le conteneur confirmé | `{code_iso, dimension?, ocr_confidence?, bbox?, image_name?}` → `200` |
| `POST /api/dossiers/<id>/plaque` | rattacher la plaque confirmée | `{immatriculation, ocr_confidence?, bbox?, image_name?}` → `200` |
| `POST /api/dossiers/<id>/validate` | valider | `200 {statut:"valide"}` · **`400` si dossier vide** |
| `POST /api/dossiers/<id>/abandon` | abandonner (soft-delete) | `200 {statut:"abandonne"}` |
| `GET /api/dossiers?statut=en_attente` | lister (association différée) | `200 {dossiers:[…]}` |
| `GET /api/dossiers/<id>` | dossier agrégé (conteneur+camion+détections) | `200 {…}` · `404` si inconnu |

Chaque rattachement conserve aussi une **`Detection`** (preuve brute IA horodatée).
« Rouvrir/compléter » un `en_attente` = rappeler `/conteneur` ou `/plaque` puis `/validate`.

### POST /api/confirm

Enregistre un scan validé par l'humain (invariant I3). Entrée JSON :
`{ "bic": "TLNU9101464", "ocr_confidence": 0.98, "image_name": "xxx.jpg" }`
→ `{ "id": 42, "bic": "TLNU9101464" }` (le BIC est normalisé majuscules/sans espaces).

### GET /api/history

→ `{ "scans": [ { "id", "bic", "valid", "ocr_confidence", "image_url", "image_path", "created_at" (ISO 8601) } ] }` (100 derniers)

### GET /api/dashboard

→ `{ "total", "valid_count", "valid_pct", "invalid_count", "avg_conf_pct", "today_count", "per_day": [{label, count, pct}×14], "top_owners": [{code, count, pct}] }`

### POST /api/scans/{id}/delete · POST /api/scans/{id}/update

Suppression : → `{ "deleted": id }`. Correction : entrée `{ "bic": "…" }` → `{ "updated": id, "bic" }`.

### GET /uploads/{name}

Sert les images uploadées/annotées (volume persistant VPS).

### Routes HTML (usage direct sans front Vercel)

`GET /` (scanner) · `POST /scan` · `POST /confirm` · `GET /history` · `GET /dashboard` — mêmes traitements, rendu Jinja.

## Labo (outil de dev — comparaison de modèles, local uniquement)

`/labo` + `/api/labo/*` : outil d'évaluation, **jamais** de logique métier ni d'écriture
PostgreSQL. Reconstruit le 2026-09-18 après perte du disque local (le code n'avait
jamais été poussé sur GitHub) — voir [DECISIONS.md](DECISIONS.md) ADR-19 et le guide
d'implémentation détaillé : [détail partie labo.md](../détail%20partie%20labo.md).

### GET /labo

Sert `labo.html` (page statique autonome, JS vanilla, 3 onglets : Image / Vidéo / Caméra RTSP
— l'onglet RTSP est câblé côté front mais ses endpoints backend restent à implémenter).

### GET /api/labo/models

→ `{ "models": [{id, label, map50_95, imgsz, group}], "ocr_engines": [{id, label, group}] }`
(`path` filtré côté serveur, jamais exposé au client). `group` = `"mien"` | `"tuteur"`.
Modèles "★ Meilleur" (`best/yolo`, `best/ocr`) : pointeurs explicites vers
`Application/models/bestYolo.pt` / `bestOCR.pt`, à mettre à jour à chaque nouvel
entraînement jugé meilleur (fichiers suivis en git, cf. AI_MODELS.md).

### POST /api/labo/detect (image, existant)

Entrée `multipart/form-data` : `image`, `model_id` (un id, ou plusieurs séparés par
des virgules → `run_detect_ensemble`), `ocr` (`"0"`/`"1"`), `ocr_engine`.

```json
// 200
{ "time_ms": 81, "boxes": [{x,y,w,h,conf,cls}],
  "annotated": "data:image/jpeg;base64,…" ,
  "zones": [{index, box, conf, cls, crop, bic, valid, corrected, raw_text}],
  "ocr": [{bic, valid, corrected, conf, raw_text}] }
// 400 : { "error": "modèle inconnu : …" }
```

### POST /api/labo/detect-video (vidéo, ajouté 2026-09-18)

Entrée `multipart/form-data` : soit `video` (fichier, extensions
`.mp4/.avi/.mov/.mkv/.webm/.m4v`), soit `recording` (nom d'un fichier déjà présent dans
`Application/backend/recordings/`, réservé au futur flux RTSP) ; `model_id` (**un seul**
détecteur) ; `ocr_engine`. Réutilise `labo.run_detect()` + `labo.read_zones()` — même
détection/OCR/validation ISO 6346 que l'image, aucune logique dupliquée.

Réponse en streaming `application/x-ndjson` (une ligne JSON par événement) :

```json
{"type":"meta","orig_fps":27.5,"analysis_fps":5,"total_frames":207,"to_analyze":34,"width":478,"height":850,"duration":7.5}
{"type":"progress","frame":36,"analyzed":6,"to_analyze":34,"pct":18,"proc_fps":9.6,"codes":0}
{"type":"done","analyzed":34,"elapsed":4.2,"codes":[
  {"bic":"CAIU6563528","valid":true,"corrected":true,"conf":0.732,"count":14,
   "crop":"data:image/jpeg;base64,…","first_time":1.09,
   "candidates":[…],"variants":[…]}
]}
{"type":"error","error":"vidéo illisible (codec non supporté ou fichier corrompu)"}
```

Échantillonnage : `VIDEO_ANALYSIS_FPS = 5` (constante `labo.py`), `cap.grab()` sur
toutes les frames + `cap.retrieve()` seulement sur celles retenues — YOLO ne tourne
JAMAIS sur une frame ignorée. Agrégation temporelle par code exact (vote de confiance)
puis consolidation floue (`labo._consolidate_codes`, ≤3 caractères d'écart à longueur
égale) pour fusionner les variantes OCR d'un même conteneur filmé en rafale, sans
jamais fusionner deux conteneurs différents (comparaison toujours au représentant du
cluster, jamais proche-en-proche).

Testé de bout en bout sur une vidéo réelle (fournie par le tuteur) : `CAIU6563528`
détecté sur 14/34 frames, chiffre de contrôle réparé automatiquement, `valid:true`.

### RTSP (`/api/labo/rtsp/*`) — **non implémenté**

Le front (`labo.html`, onglet Caméra RTSP) appelle déjà `connect` / `status` /
`preview/<sid>` / `record/start` / `record/stop` / `disconnect`, mais ces routes et le
module `rtsp.py` restent à construire (prochain chantier — cf. ROADMAP.md).

## Contrat cible des services IA (SPEC_V2 §8 — à implémenter)

Tout futur service IA (Plaque, Driver, Documents) expose le **même contrat** :

```
POST /analyze          (entrée : image)
→ 200 {
    "result":     <valeur lue>,        // ex. matricule, code ISO, identifiant
    "confidence": 0.0-1.0,
    "bbox":       [x1, y1, x2, y2],
    "extra":      { ... }              // champs spécifiques (ex. valid ISO)
  }
```

Règles (invariants I1/I4/I5) : sans état, sans logique métier, sans appel à un autre
service IA ; l'interface est **stable** même si le modèle interne change.

| Service | Statut | result attendu |
|---|---|---|
| API Container | ✅ existe (intégré au monolithe, à extraire) | code BIC + validité ISO |
| API Plaque | ✅ pipeline construit (`/api/scan-plaque`), modèle à entraîner | matricule (format marocain) |
| API Icônes IMDG | perspective | pictogramme danger |
| ~~API Driver~~ / ~~API Documents~~ | **hors périmètre** (ADR-11) | — |
