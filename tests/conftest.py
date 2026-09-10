from pathlib import Path

import pytest

from config import Settings
from data.storage import JobStorage
from scraper.wttj import Job


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "APP_ENV": "testing",
            "SECRET_KEY": "test-secret",
            "DB_PATH": str(tmp_path / "jobs.db"),
            "WTTJ_APP_ID": "test-app",
            "WTTJ_API_KEY": "test-key",
            "TRUSTSTORE_ENABLED": "false",
            "CSRF_ENABLED": "true",
        },
        testing=True,
    )


@pytest.fixture
def storage(tmp_path: Path):
    instance = JobStorage(tmp_path / "jobs.db")
    yield instance
    instance.close()


@pytest.fixture
def job_data() -> dict[str, str]:
    return {
        "url": "https://jobs.example.test/job-1",
        "title": "Python Engineer",
        "company": "Example",
        "location": "Paris",
        "published_at": "2026-09-01T12:00:00",
        "contract_type": "full_time",
        "remote": "fulltime",
        "salary": "50000-60000 EUR/an",
        "source": "WTTJ",
    }


@pytest.fixture
def jobs() -> list[Job]:
    return [
        Job(
            title="Python Engineer",
            company="Example",
            location="Paris",
            url="https://jobs.example.test/wttj",
            published_at="2026-09-01T12:00:00",
            contract_type="full_time",
            remote="fulltime",
            salary="50000-60000 EUR/an",
            source="WTTJ",
        ),
        Job(
            title="Data Engineer",
            company="Green Example",
            location="Lyon",
            url="https://jobs.example.test/greenhouse",
            published_at="2026-09-02T12:00:00",
            contract_type="Full-time",
            remote="",
            salary=None,
            source="Greenhouse",
        ),
        Job(
            title="Product Engineer",
            company="Lever Example",
            location="Remote",
            url="https://jobs.example.test/lever",
            published_at="2026-09-03T12:00:00",
            contract_type="Full-time",
            remote="remote",
            salary="60000+ EUR/an",
            source="Lever",
        ),
    ]
