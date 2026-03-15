import sqlite3
from pathlib import Path
from scraper.wttj import Job

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
                salary TEXT
            )
        """)
        self._conn.commit()

    def add(self, jobs: list[Job]) -> list[Job]:
        """Ajoute des jobs et retourne uniquement les nouveaux (non dupliqués)."""
        new_jobs = []
        for job in jobs:
            try:
                self._conn.execute(
                    "INSERT INTO jobs (url, title, company, location, published_at, contract_type, remote, salary) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (job.url, job.title, job.company, job.location,
                     job.published_at, job.contract_type, job.remote, job.salary),
                )
                new_jobs.append(job)
            except sqlite3.IntegrityError:
                pass  # doublon, on ignore
        if new_jobs:
            self._conn.commit()
        return new_jobs

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
