# DATABASE — Modèle de données

> **Dernière mise à jour** : 2026-07-20

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

## Dossier de passage (V2 — schéma normalisé, implémenté 2026-07-20)

Schéma normalisé SPEC §12 créé par `init_dossier_db()` (`db.py`). Périmètre
vision-only (ADR-11) : pas de `chauffeur` ni `document`. Modèle **symétrique**
(ADR-12) — 0..1 conteneur + 0..1 camion, validable dès **≥1 entité**.

```sql
dossiers (
    id SERIAL PK, statut VARCHAR(16) DEFAULT 'en_attente',   -- en_attente | valide | abandonne
    source VARCHAR(16), voie VARCHAR(32),
    created_at TIMESTAMPTZ DEFAULT now(), validated_at TIMESTAMPTZ)
conteneurs (id SERIAL PK, dossier_id INT UNIQUE FK→dossiers ON DELETE CASCADE,
            code_iso VARCHAR(11), dimension VARCHAR(16))     -- 0..1, valeur VALIDÉE
camions    (id SERIAL PK, dossier_id INT UNIQUE FK→dossiers ON DELETE CASCADE,
            immatriculation VARCHAR(32))                     -- 0..1, valeur VALIDÉE
detections (id SERIAL PK, dossier_id INT FK→dossiers ON DELETE CASCADE,
            type VARCHAR(16), valeur TEXT, confidence REAL,
            bbox JSONB, image_path TEXT, timestamp TIMESTAMPTZ DEFAULT now())
```

Principe : entité métier (conteneur/camion) = information **validée** ; `detections`
= **preuve brute IA** horodatée (traçabilité, support de l'agrégation).

| Opération | Fonction (`db.py`) |
|---|---|
| Init idempotent | `init_dossier_db()` |
| Ouvrir passage | `create_dossier(source, voie=None) -> id` (statut `en_attente`) |
| Rattacher entité (upsert 0..1) | `set_conteneur(id, code_iso, dim)` · `set_camion(id, immat)` |
| Preuve brute | `add_detection(id, type, valeur, confidence, bbox, image_path)` |
| Valider | `validate_dossier(id) -> bool` — **refuse si 0 entité** (I3) |
| Abandonner | `abandon_dossier(id)` (soft-delete → `abandonne`) |
| Lire agrégé / lister | `get_dossier(id)` · `list_dossiers(statut=None, limit)` |
| Migration | `migrate_scans_to_dossiers() -> int` |

**Migration** : chaque ligne `scans` ↦ un `dossier` `valide` mono-conteneur + sa
`detection` (`type='conteneur'`). Aucune perte. La table `scans` reste en place
(source de la migration, pas encore supprimée).

## Opérations

- Pas de migrations formelles à ce stade (une table) ; à introduire (ex. simple
  dossier `migrations/*.sql` appliqué par `init_db`) dès la 2e table.
- Sauvegardes : Neon fournit le point-in-time recovery (plan gratuit : 24 h).
