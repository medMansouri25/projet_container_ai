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
