import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent
DEFAULT_DB = DATA_DIR / "jobs.db"


class JobStorage:
    """Stockage SQLite des offres avec déduplication par URL."""

    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                published_at TEXT,
                contract_type TEXT,
                remote TEXT,
                salary TEXT,
                source TEXT DEFAULT 'WTTJ'
            )
        """)
        self._conn.commit()
        # Migration : ajouter la colonne source si elle n'existe pas
        try:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN source TEXT DEFAULT 'WTTJ'")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # colonne existe déjà

    def save_one(self, job_data: dict) -> bool:
        """Sauvegarde une seule offre. Retourne True si nouveau, False si doublon."""
        try:
            self._conn.execute(
                "INSERT INTO jobs (url, title, company, location, published_at, contract_type, remote, salary, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (job_data["url"], job_data["title"], job_data["company"], job_data["location"],
                 job_data["published_at"], job_data["contract_type"], job_data["remote"],
                 job_data.get("salary"), job_data.get("source", "WTTJ")),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_one(self, url: str) -> bool:
        """Supprime une offre par URL. Retourne True si supprimée."""
        cursor = self._conn.execute("DELETE FROM jobs WHERE url = ?", (url,))
        self._conn.commit()
        return cursor.rowcount > 0

    def is_saved(self, url: str) -> bool:
        """Vérifie si une offre est déjà sauvegardée."""
        cursor = self._conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,))
        return cursor.fetchone() is not None

    def saved_urls(self) -> set[str]:
        """Retourne l'ensemble des URLs sauvegardées."""
        cursor = self._conn.execute("SELECT url FROM jobs")
        return {row["url"] for row in cursor.fetchall()}

    def all(self, order_by: str = "published_at DESC") -> list[dict]:
        """Retourne tous les jobs stockés, triés chronologiquement."""
        cursor = self._conn.execute(f"SELECT * FROM jobs ORDER BY {order_by}")
        return [dict(row) for row in cursor.fetchall()]

    def count(self) -> int:
        cursor = self._conn.execute("SELECT COUNT(*) FROM jobs")
        return cursor.fetchone()[0]

    def clear(self):
        """Supprime tous les jobs."""
        self._conn.execute("DELETE FROM jobs")
        self._conn.commit()
