# DATABASE — Modèle de données

> **Dernière mise à jour** : 2026-07-16

## Actuel (V1)

**PostgreSQL Neon** (serverless, cloud). Connexion : env `DATABASE_URL`
(`.env` local en dev, secret GitHub → conteneur en prod). Accès : `psycopg2`
(`Application/backend/db.py`), création de table idempotente (`init_db`).

```sql
CREATE TABLE IF NOT EXISTS scans (
    id             SERIAL PRIMARY KEY,
    bic            VARCHAR(11) NOT NULL,     -- normalisé majuscules sans espaces
    ocr_confidence REAL,
    image_path     TEXT,                     -- ex. uploads/abc123.jpg (volume VPS)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

| Opération | Fonction | Note |
|---|---|---|
| Insertion | `save_scan(bic, conf, path)` | uniquement après validation humaine (I3) |
| Lecture | `list_scans(limit)` | plus récents d'abord |
| Correction | `update_scan(id, bic)` | édition inline historique |
| Suppression | `delete_scan(id)` | avec confirmation UI |

**Choix assumés** :
- La validité ISO n'est **pas stockée** (recalculée à l'affichage — pas de dénormalisation).
- Les images vivent sur le **volume VPS** (`/root/smartcontainer_uploads`), la base ne
  stocke que le chemin. Conséquence : la base est portable, les images liées au VPS.

## Cible (SPEC_V2 §12 — hypothèse, dépend des questions Q1/Q3)

```sql
-- Esquisse indicative, à valider avec le tuteur
dossier_passage (id UUID, statut, source, voie, created_at, validated_at)
camion          (dossier_id FK, plaque)
conteneur       (dossier_id FK, code_iso, dimension)
chauffeur       (dossier_id FK, identifiant)
document        (dossier_id FK, type, reference)
detection       (id, dossier_id FK, type, valeur, confidence,
                 bbox, timestamp)          -- preuve brute IA, traçabilité
```

Principe : entité métier = information **validée** ; `detection` = **preuve brute**
horodatée (support du linking et de l'audit).

**Migration** : chaque ligne `scans` ↦ un `dossier_passage` mono-conteneur
(statut validé) + sa `detection`. Aucune perte.

## Opérations

- Pas de migrations formelles à ce stade (une table) ; à introduire (ex. simple
  dossier `migrations/*.sql` appliqué par `init_db`) dès la 2e table.
- Sauvegardes : Neon fournit le point-in-time recovery (plan gratuit : 24 h).
