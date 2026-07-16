# API_CONTRACTS — Contrats REST

> **Dernière mise à jour** : 2026-07-16 · Base : `https://api.containerai-marsa-maroc.online`

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
| API Plaque | à créer (Q2 : dataset plaques marocaines) | matricule |
| API Driver | à créer | identifiant CIN/permis |
| API Documents | à créer (Q6 : manuscrit hors OCR auto) | champs DUM/booking… |
