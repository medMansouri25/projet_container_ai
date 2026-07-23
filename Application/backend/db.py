"""
db.py — Persistance des scans BIC (PostgreSQL Neon)
----------------------------------------------------
Connexion via DATABASE_URL (variable d'environnement ; .env local en dev).
Table unique `scans` : code BIC confirmé, confiance OCR, chemin de l'image,
date du scan.
"""

import os

import psycopg2
import psycopg2.extras


def _load_dotenv():
    """Charge .env à la racine du projet si DATABASE_URL n'est pas déjà défini."""
    if os.environ.get("DATABASE_URL"):
        return
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def get_conn():
    _load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL non defini (env ou .env).")
    return psycopg2.connect(url)


def init_db() -> None:
    """Crée la table scans si elle n'existe pas."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id             SERIAL PRIMARY KEY,
                bic            VARCHAR(11) NOT NULL,
                ocr_confidence REAL,
                image_path     TEXT,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


def save_scan(bic: str, ocr_confidence: float = None, image_path: str = None) -> int:
    """Enregistre un scan confirmé. Retourne l'id créé."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO scans (bic, ocr_confidence, image_path) "
            "VALUES (%s, %s, %s) RETURNING id",
            (bic, ocr_confidence, image_path),
        )
        return cur.fetchone()[0]


def delete_scan(scan_id: int) -> None:
    """Supprime un scan de l'historique."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM scans WHERE id = %s", (scan_id,))


def update_scan(scan_id: int, bic: str) -> None:
    """Corrige le code BIC d'un scan existant."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE scans SET bic = %s WHERE id = %s", (bic, scan_id))


def list_scans(limit: int = 50) -> list:
    """Retourne les derniers scans confirmés (plus récents d'abord)."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, bic, ocr_confidence, image_path, created_at "
                "FROM scans ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]


# ── Dossier de passage (V2, schéma normalisé SPEC §12) ────────────────────────
# DossierPassage agrège 0..1 Conteneur + 0..1 Camion (valeurs VALIDÉES) ; chaque
# Detection porte la preuve brute IA horodatée. Validable dès ≥1 entité.


def validate_dossier(dossier_id: int) -> bool:
    """Passe un dossier au statut 'valide' — SEULEMENT s'il porte au moins une
    entité (conteneur ou camion). Retourne False sans rien changer si vide
    (invariant : on ne valide pas un dossier sans contenu)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM conteneurs WHERE dossier_id = %s", (dossier_id,))
        n_conteneur = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM camions WHERE dossier_id = %s", (dossier_id,))
        n_camion = cur.fetchone()[0]
        if n_conteneur + n_camion == 0:
            return False
        cur.execute(
            "UPDATE dossiers SET statut = 'valide', validated_at = now() WHERE id = %s",
            (dossier_id,),
        )
        return True


def get_dossier(dossier_id: int) -> dict | None:
    """Retourne un dossier agrégé : ses métadonnées + le conteneur (0..1), le
    camion (0..1) et la liste des détections brutes. None si le dossier
    n'existe pas."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, statut, source, voie, created_at, validated_at "
                "FROM dossiers WHERE id = %s", (dossier_id,))
            dossier = cur.fetchone()
            if dossier is None:
                return None
            cur.execute(
                "SELECT code_iso, dimension FROM conteneurs WHERE dossier_id = %s",
                (dossier_id,))
            conteneur = cur.fetchone()
            cur.execute(
                "SELECT immatriculation FROM camions WHERE dossier_id = %s",
                (dossier_id,))
            camion = cur.fetchone()
            cur.execute(
                "SELECT type, valeur, confidence, bbox, image_path, timestamp "
                "FROM detections WHERE dossier_id = %s ORDER BY timestamp",
                (dossier_id,))
            detections = cur.fetchall()
            result = dict(dossier)
            result["conteneur"] = dict(conteneur) if conteneur else None
            result["camion"] = dict(camion) if camion else None
            result["detections"] = [dict(r) for r in detections]
            return result


def init_dossier_db() -> None:
    """Crée les 4 tables du dossier de passage si absentes (idempotent).
    conteneurs/camions : UNIQUE(dossier_id) → au plus une entité par dossier."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dossiers (
                id           SERIAL PRIMARY KEY,
                statut       VARCHAR(16) NOT NULL DEFAULT 'en_attente',
                source       VARCHAR(16),
                voie         VARCHAR(32),
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                validated_at TIMESTAMPTZ
            )""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conteneurs (
                id         SERIAL PRIMARY KEY,
                dossier_id INTEGER NOT NULL UNIQUE REFERENCES dossiers(id) ON DELETE CASCADE,
                code_iso   VARCHAR(11) NOT NULL,
                dimension  VARCHAR(16)
            )""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS camions (
                id              SERIAL PRIMARY KEY,
                dossier_id      INTEGER NOT NULL UNIQUE REFERENCES dossiers(id) ON DELETE CASCADE,
                immatriculation VARCHAR(32) NOT NULL
            )""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id         SERIAL PRIMARY KEY,
                dossier_id INTEGER NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
                type       VARCHAR(16) NOT NULL,
                valeur     TEXT,
                confidence REAL,
                bbox       JSONB,
                image_path TEXT,
                timestamp  TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")


def create_dossier(source: str, voie: str = None) -> int:
    """Ouvre un dossier de passage (statut initial 'en_attente'). Retourne l'id."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dossiers (statut, source, voie) "
            "VALUES ('en_attente', %s, %s) RETURNING id", (source, voie))
        return cur.fetchone()[0]


def set_conteneur(dossier_id: int, code_iso: str, dimension: str = None) -> None:
    """Rattache (ou remplace) le conteneur validé du dossier — au plus un."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conteneurs (dossier_id, code_iso, dimension) "
            "VALUES (%s, %s, %s) ON CONFLICT (dossier_id) DO UPDATE "
            "SET code_iso = EXCLUDED.code_iso, dimension = EXCLUDED.dimension",
            (dossier_id, code_iso, dimension))


def set_camion(dossier_id: int, immatriculation: str) -> None:
    """Rattache (ou remplace) le camion validé du dossier — au plus un."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO camions (dossier_id, immatriculation) VALUES (%s, %s) "
            "ON CONFLICT (dossier_id) DO UPDATE "
            "SET immatriculation = EXCLUDED.immatriculation",
            (dossier_id, immatriculation))


def add_detection(dossier_id: int, type: str, valeur: str, confidence: float = None,
                  bbox=None, image_path: str = None) -> int:
    """Enregistre une preuve brute IA horodatée. Retourne l'id."""
    import json
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO detections (dossier_id, type, valeur, confidence, bbox, image_path) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (dossier_id, type, valeur, confidence,
             json.dumps(bbox) if bbox is not None else None, image_path))
        return cur.fetchone()[0]


def abandon_dossier(dossier_id: int) -> None:
    """Passe le dossier au statut 'abandonne' (soft-delete, traçabilité)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE dossiers SET statut = 'abandonne' WHERE id = %s", (dossier_id,))


def list_dossiers(statut: str = None, limit: int = 100) -> list:
    """Liste les dossiers (plus récents d'abord), filtrés par statut si fourni.
    Sert notamment à la liste des 'en_attente' pour l'association différée."""
    cols = "id, statut, source, voie, created_at, validated_at"
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if statut:
                cur.execute(
                    f"SELECT {cols} FROM dossiers WHERE statut = %s "
                    "ORDER BY created_at DESC LIMIT %s", (statut, limit))
            else:
                cur.execute(
                    f"SELECT {cols} FROM dossiers ORDER BY created_at DESC LIMIT %s",
                    (limit,))
            return [dict(r) for r in cur.fetchall()]


def list_dossiers_with_entities(statut: str = None, limit: int = 100) -> list:
    """Liste dossiers avec conteneur + camion attachés (JOIN) pour l'historique."""
    where = "WHERE d.statut = %s " if statut else ""
    params = (statut, limit) if statut else (limit,)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT d.id, d.statut, d.source, d.voie, d.created_at, d.validated_at,
                       c.code_iso, cam.immatriculation
                FROM dossiers d
                LEFT JOIN conteneurs c   ON c.dossier_id   = d.id
                LEFT JOIN camions    cam ON cam.dossier_id = d.id
                {where}ORDER BY d.created_at DESC LIMIT %s
            """, params)
            return [dict(r) for r in cur.fetchall()]


def dossier_stats() -> dict:
    """Comptages agrégés des dossiers pour le dashboard."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT statut, COUNT(*) FROM dossiers GROUP BY statut")
            counts = {row[0]: row[1] for row in cur.fetchall()}
            total = sum(counts.values())
            cur.execute("""
                SELECT COUNT(*) FROM dossiers d
                JOIN conteneurs c   ON c.dossier_id   = d.id
                JOIN camions    cam ON cam.dossier_id = d.id
            """)
            complets = cur.fetchone()[0]
        return {
            "total": total,
            "en_attente": counts.get("en_attente", 0),
            "valide": counts.get("valide", 0),
            "abandonne": counts.get("abandonne", 0),
            "complets": complets,
        }


def migrate_scans_to_dossiers() -> int:
    """Migre chaque `scan` BIC existant en un dossier 'valide' réduit au
    conteneur (+ sa détection). Retourne le nombre de dossiers créés.
    (cf. note de migration DOMAIN_MODEL.md : un scan = dossier mono-conteneur.)"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, bic, ocr_confidence, image_path, created_at FROM scans ORDER BY id")
        scans = cur.fetchall()
        migrated = 0
        for _sid, bic, confidence, image_path, created in scans:
            cur.execute(
                "INSERT INTO dossiers (statut, source, created_at, validated_at) "
                "VALUES ('valide', 'image', %s, now()) RETURNING id", (created,))
            dossier_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO conteneurs (dossier_id, code_iso) VALUES (%s, %s)",
                (dossier_id, bic))
            cur.execute(
                "INSERT INTO detections (dossier_id, type, valeur, confidence, image_path) "
                "VALUES (%s, 'conteneur', %s, %s, %s)",
                (dossier_id, bic, confidence, image_path))
            migrated += 1
        return migrated
