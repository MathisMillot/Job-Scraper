import sqlite3
from pathlib import Path
from typing import Any

from config import VALID_SOURCES

DATA_DIR = Path(__file__).parent
DEFAULT_DB = DATA_DIR / "jobs.db"
REQUIRED_JOB_FIELDS = (
    "url",
    "title",
    "company",
    "location",
    "published_at",
    "contract_type",
    "remote",
    "source",
)
ORDER_QUERIES = {
    "published_at DESC": "SELECT * FROM jobs ORDER BY published_at DESC",
    "published_at ASC": "SELECT * FROM jobs ORDER BY published_at ASC",
    "title ASC": "SELECT * FROM jobs ORDER BY title ASC",
    "title DESC": "SELECT * FROM jobs ORDER BY title DESC",
}


class InvalidJobData(ValueError):
    """Raised when a job does not satisfy the storage contract."""


class JobStorage:
    """SQLite storage for jobs with URL deduplication."""

    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_table()

    def _create_table(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                published_at TEXT,
                contract_type TEXT,
                remote TEXT,
                salary TEXT,
                source TEXT NOT NULL CHECK(source IN ('WTTJ', 'Greenhouse', 'Lever'))
            );

            CREATE TABLE IF NOT EXISTS labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS job_label (
                job_url TEXT NOT NULL,
                label_id INTEGER NOT NULL,
                PRIMARY KEY (job_url, label_id),
                FOREIGN KEY (job_url) REFERENCES jobs(url) ON DELETE CASCADE,
                FOREIGN KEY (label_id) REFERENCES labels(id) ON DELETE CASCADE
            );
            """
        )

        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "source" not in columns:
            # Existing databases predate source support and were WTTJ-only.
            self._conn.execute(
                "ALTER TABLE jobs ADD COLUMN source TEXT NOT NULL DEFAULT 'WTTJ'"
            )

        self._migrate_job_label_foreign_keys()
        self._conn.commit()

    def _migrate_job_label_foreign_keys(self) -> None:
        foreign_keys = self._conn.execute(
            "PRAGMA foreign_key_list(job_label)"
        ).fetchall()
        if not foreign_keys:
            self._conn.executescript(
                """
                CREATE TABLE job_label_new (
                    job_url TEXT NOT NULL,
                    label_id INTEGER NOT NULL,
                    PRIMARY KEY (job_url, label_id),
                    FOREIGN KEY (job_url) REFERENCES jobs(url) ON DELETE CASCADE,
                    FOREIGN KEY (label_id) REFERENCES labels(id) ON DELETE CASCADE
                );
                INSERT OR IGNORE INTO job_label_new (job_url, label_id)
                SELECT jl.job_url, jl.label_id
                FROM job_label jl
                JOIN jobs j ON j.url = jl.job_url
                JOIN labels l ON l.id = jl.label_id;
                DROP TABLE job_label;
                ALTER TABLE job_label_new RENAME TO job_label;
                """
            )

    @staticmethod
    def _validate_job_data(job_data: dict[str, Any]) -> None:
        if not isinstance(job_data, dict):
            raise InvalidJobData("Job data must be a JSON object")

        missing = [field for field in REQUIRED_JOB_FIELDS if field not in job_data]
        if missing:
            raise InvalidJobData(
                f"Missing required job fields: {', '.join(missing)}"
            )

        for field in REQUIRED_JOB_FIELDS:
            if not isinstance(job_data[field], str):
                raise InvalidJobData(f"Job field {field!r} must be a string")

        if not job_data["url"].strip():
            raise InvalidJobData("Job URL cannot be empty")
        if job_data["source"] not in VALID_SOURCES:
            valid_sources = ", ".join(sorted(VALID_SOURCES))
            raise InvalidJobData(
                f"Job source must be one of: {valid_sources}"
            )

        salary = job_data.get("salary")
        if salary is not None and not isinstance(salary, str):
            raise InvalidJobData("Job salary must be a string or null")

    def save_one(self, job_data: dict[str, Any]) -> bool:
        """Save one job, returning False when its URL already exists."""
        self._validate_job_data(job_data)
        try:
            self._conn.execute(
                """
                INSERT INTO jobs (
                    url, title, company, location, published_at,
                    contract_type, remote, salary, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_data["url"],
                    job_data["title"],
                    job_data["company"],
                    job_data["location"],
                    job_data["published_at"],
                    job_data["contract_type"],
                    job_data["remote"],
                    job_data.get("salary"),
                    job_data["source"],
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            self._conn.rollback()
            if self.is_saved(job_data["url"]):
                return False
            raise

    def add_label(self, job_url: str, label: str) -> None:
        """Associate a trimmed label with an existing job."""
        if not isinstance(label, str):
            raise InvalidJobData("Job label must be a string")
        label = label.strip()
        if not label:
            return
        if not self.is_saved(job_url):
            raise InvalidJobData("Cannot label a job that is not saved")

        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO labels (label) VALUES (?)",
                (label,),
            )
            cursor = self._conn.execute(
                "SELECT id FROM labels WHERE label = ?", (label,)
            )
            label_id = cursor.fetchone()["id"]
            self._conn.execute(
                """
                INSERT OR IGNORE INTO job_label (job_url, label_id)
                VALUES (?, ?)
                """,
                (job_url, label_id),
            )
            self._conn.commit()
        except sqlite3.Error:
            self._conn.rollback()
            raise

    def labels_for_job(self, job_url: str) -> list[str]:
        """Return labels associated with one job."""
        cursor = self._conn.execute(
            """
            SELECT l.label
            FROM labels l
            JOIN job_label jl ON jl.label_id = l.id
            WHERE jl.job_url = ?
            ORDER BY l.label COLLATE NOCASE
            """,
            (job_url,),
        )
        return [row["label"] for row in cursor.fetchall()]

    def all_labels(self) -> list[str]:
        """Return all labels alphabetically, retaining unused label names."""
        cursor = self._conn.execute(
            "SELECT label FROM labels ORDER BY label COLLATE NOCASE"
        )
        return [row["label"] for row in cursor.fetchall()]

    def delete_one(self, url: str) -> bool:
        """Delete one job and its associations; retain the label vocabulary."""
        try:
            cursor = self._conn.execute("DELETE FROM jobs WHERE url = ?", (url,))
            self._conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error:
            self._conn.rollback()
            raise

    def is_saved(self, url: str) -> bool:
        cursor = self._conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,))
        return cursor.fetchone() is not None

    def saved_urls(self) -> set[str]:
        cursor = self._conn.execute("SELECT url FROM jobs")
        return {row["url"] for row in cursor.fetchall()}

    def all(self, order_by: str = "published_at DESC") -> list[dict[str, Any]]:
        """Return all jobs using one of the supported order expressions."""
        try:
            query = ORDER_QUERIES[order_by]
        except KeyError as exc:
            raise ValueError(f"Unsupported order_by value: {order_by!r}") from exc
        cursor = self._conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def count(self) -> int:
        cursor = self._conn.execute("SELECT COUNT(*) FROM jobs")
        return cursor.fetchone()[0]

    def clear(self) -> None:
        """Delete all jobs and associations while retaining label names."""
        try:
            self._conn.execute("DELETE FROM jobs")
            self._conn.commit()
        except sqlite3.Error:
            self._conn.rollback()
            raise

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "JobStorage":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
