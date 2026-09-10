import threading

import pytest
from werkzeug.serving import make_server

from app import create_app
from config import Settings
from data.storage import JobStorage
from scraper.wttj import Job


class BrowserWTTJ:
    def search_multi_keywords(self, **_kwargs):
        return [
            Job(
                title="Python Engineer",
                company="Browser Example",
                location="Paris",
                url="https://jobs.example.test/browser",
                published_at="2026-09-01T12:00:00",
                contract_type="full_time",
                remote="fulltime",
                salary="50000-60000 EUR/an",
                source="WTTJ",
            )
        ]


class EmptyCompanyScraper:
    def search(self, **_kwargs):
        return []


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    root = tmp_path_factory.mktemp("e2e")
    storage = JobStorage(root / "jobs.db")
    settings = Settings.from_env(
        {
            "APP_ENV": "testing",
            "SECRET_KEY": "browser-test-secret",
            "DB_PATH": str(root / "jobs.db"),
            "TRUSTSTORE_ENABLED": "false",
            "CSRF_ENABLED": "false",
        },
        testing=True,
    )
    app = create_app(
        settings,
        config={
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "WTF_CSRF_CHECK_DEFAULT": False,
            "TRUSTSTORE_ENABLED": False,
        },
        storage_instance=storage,
        wttj_scraper_instance=BrowserWTTJ(),
        greenhouse_scraper_instance=EmptyCompanyScraper(),
        lever_scraper_instance=EmptyCompanyScraper(),
    )
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=5)
    storage.close()
