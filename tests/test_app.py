import re

import pytest
import requests

from app import create_app
from data.storage import JobStorage


class FakeWTTJScraper:
    def __init__(self, jobs):
        self.jobs = jobs
        self.calls = []

    def search_multi_keywords(self, **kwargs):
        self.calls.append(kwargs)
        return self.jobs


class FakeCompanyScraper:
    def __init__(self, jobs):
        self.jobs = jobs
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return self.jobs


@pytest.fixture
def app_client(settings, tmp_path, jobs):
    storage = JobStorage(tmp_path / "app.db")
    wttj = FakeWTTJScraper([jobs[0]])
    greenhouse = FakeCompanyScraper([jobs[1]])
    lever = FakeCompanyScraper([jobs[2]])
    app = create_app(
        settings,
        config={
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "WTF_CSRF_CHECK_DEFAULT": False,
            "TRUSTSTORE_ENABLED": False,
        },
        storage_instance=storage,
        wttj_scraper_instance=wttj,
        greenhouse_scraper_instance=greenhouse,
        lever_scraper_instance=lever,
    )
    with app.test_client() as client:
        yield app, client, storage, wttj, greenhouse, lever
    storage.close()


def test_get_index_and_health(app_client):
    _, client, _, _, _, _ = app_client

    response = client.get("/")
    health = client.get("/health")

    assert response.status_code == 200
    assert b"Rechercher des offres" in response.data
    assert health.get_json() == {"status": "ok"}


def test_search_form_submits_with_csrf_token(settings, tmp_path, jobs):
    storage = JobStorage(tmp_path / "csrf-search.db")
    app = create_app(
        settings,
        config={
            "TESTING": True,
            "WTF_CSRF_ENABLED": True,
            "WTF_CSRF_CHECK_DEFAULT": True,
            "TRUSTSTORE_ENABLED": False,
        },
        storage_instance=storage,
        wttj_scraper_instance=FakeWTTJScraper([jobs[0]]),
        greenhouse_scraper_instance=FakeCompanyScraper([]),
        lever_scraper_instance=FakeCompanyScraper([]),
    )
    with app.test_client() as client:
        page = client.get("/")
        token = re.search(
            br'<input type="hidden" name="csrf_token" value="([^"]+)"',
            page.data,
        ).group(1).decode()
        response = client.post(
            "/",
            data={
                "csrf_token": token,
                "sources": "wttj",
                "keywords": "python",
            },
        )
    storage.close()

    assert response.status_code == 200
    assert b"WTTJ" in response.data


def test_empty_search_does_not_call_scrapers(app_client):
    _, client, _, wttj, _, _ = app_client

    response = client.post("/", data={})

    assert response.status_code == 200
    assert b"Veuillez remplir au moins un champ" in response.data
    assert wttj.calls == []


def test_search_deduplicates_and_displays_source(app_client):
    _, client, _, _, greenhouse, _ = app_client

    response = client.post(
        "/",
        data={
            "sources": ["greenhouse"],
            "keywords": "data",
            "company_slugs": "example",
        },
    )

    assert response.status_code == 200
    assert b"Greenhouse" in response.data
    assert greenhouse.calls[0]["company_slugs"] == ["example"]


def test_wttj_search_parses_locations_deduplicates_and_applies_filters(
    app_client,
    jobs,
):
    _, client, _, wttj, _, _ = app_client
    wttj.jobs = [jobs[0], jobs[0]]

    response = client.post(
        "/",
        data={
            "sources": "wttj",
            "keywords": "python, backend",
            "locations": "Paris, Lyon",
            "contract_type": "full_time",
            "remote": "fulltime",
            "salary_range": "45k-60k",
        },
    )

    assert response.status_code == 200
    assert response.data.count(b'class="source-badge source-wttj"') == 1
    assert len(wttj.calls) == 2


def test_lever_search_filters_location_and_displays_source(app_client):
    _, client, _, _, _, lever = app_client

    response = client.post(
        "/",
        data={
            "sources": "lever",
            "keywords": "product",
            "locations": "remote",
            "company_slugs": "lever-example",
        },
    )

    assert response.status_code == 200
    assert b"Lever" in response.data
    assert lever.calls[0]["keywords"] == ["product"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("contract_type", "invalid", b"type de contrat est invalide"),
        ("remote", "invalid", b"filtre remote est invalide"),
        ("salary_range", "invalid", b"tranche salariale est invalide"),
        ("company", "x" * 201, b"nom de l&#39;entreprise est trop long"),
        ("keywords", "x" * 101, b"mots-cl"),
        ("locations", "x" * 101, b"localisations"),
        ("company_slugs", "bad_slug!", b"slug d&#39;entreprise est invalide"),
    ],
)
def test_search_validation_rejects_invalid_values(app_client, field, value, message):
    _, client, _, _, _, _ = app_client
    data = {"sources": "wttj", "keywords": "python"}
    data[field] = value

    response = client.post("/", data=data)

    assert response.status_code == 200
    assert message in response.data


def test_provider_failure_is_reported_without_server_error(app_client):
    _, client, _, wttj, _, _ = app_client

    def fail(**_kwargs):
        raise requests.Timeout("provider unavailable")

    wttj.search_multi_keywords = fail
    response = client.post(
        "/",
        data={"sources": "wttj", "keywords": "python"},
    )

    assert response.status_code == 200
    assert b"temporairement indisponible" in response.data


def test_invalid_source_is_rejected(app_client):
    _, client, _, _, _, _ = app_client

    response = client.post(
        "/",
        data={"sources": "unknown", "keywords": "python"},
    )

    assert response.status_code == 200
    assert b"source de recherche est invalide" in response.data


def test_ats_search_requires_company_slug(app_client):
    _, client, _, _, _, _ = app_client

    response = client.post(
        "/",
        data={"sources": "lever", "keywords": "python"},
    )

    assert response.status_code == 200
    assert b"slug d&#39;entreprise" in response.data


def test_save_rejects_missing_source_and_accepts_all_valid_sources(app_client, jobs):
    _, client, storage, _, _, _ = app_client
    missing_source = jobs[0].to_dict()
    missing_source.pop("source")

    rejected = client.post("/save", json=missing_source)
    assert rejected.status_code == 422
    assert storage.count() == 0

    for job in jobs:
        response = client.post("/save", json=job.to_dict())
        assert response.status_code == 200
        assert response.get_json() == {"saved": True}

    saved_page = client.get("/saved")
    assert b"WTTJ" in saved_page.data
    assert b"Greenhouse" in saved_page.data
    assert b"Lever" in saved_page.data


def test_save_rejects_missing_json_and_labels_endpoint_is_sorted(app_client):
    _, client, _, _, _, _ = app_client

    missing_json = client.post("/save", data="not-json")
    labels_response = client.get("/labels")

    assert missing_json.status_code == 400
    assert labels_response.get_json() == []


def test_labels_duplicate_saves_and_delete(app_client, jobs):
    _, client, storage, _, _, _ = app_client
    payload = jobs[0].to_dict()
    payload["label"] = " Favorite "

    first = client.post("/save", json=payload)
    duplicate = client.post("/save", json=payload)

    assert first.get_json() == {"saved": True}
    assert duplicate.get_json() == {"saved": False}
    assert storage.all_labels() == ["Favorite"]

    deleted = client.post(
        "/delete",
        data={"url": payload["url"]},
        follow_redirects=True,
    )
    assert deleted.status_code == 200
    assert storage.count() == 0


def test_delete_requires_a_url(app_client):
    _, client, _, _, _, _ = app_client

    response = client.post("/delete", data={})

    assert response.status_code == 400
    assert response.get_json() == {"error": "URL manquante"}


def test_clear_removes_saved_jobs(app_client, jobs):
    _, client, storage, _, _, _ = app_client
    client.post("/save", json=jobs[0].to_dict())

    response = client.post("/clear", follow_redirects=True)

    assert response.status_code == 200
    assert storage.count() == 0
    assert "Aucune offre sauvegardée".encode() in response.data


def test_csrf_rejects_json_without_token(settings, tmp_path, jobs):
    storage = JobStorage(tmp_path / "csrf.db")
    app = create_app(
        settings,
        config={
            "TESTING": True,
            "WTF_CSRF_ENABLED": True,
            "WTF_CSRF_CHECK_DEFAULT": True,
            "TRUSTSTORE_ENABLED": False,
        },
        storage_instance=storage,
        wttj_scraper_instance=FakeWTTJScraper([jobs[0]]),
        greenhouse_scraper_instance=FakeCompanyScraper([]),
        lever_scraper_instance=FakeCompanyScraper([]),
    )
    with app.test_client() as client:
        response = client.post("/save", json=jobs[0].to_dict())
    storage.close()

    assert response.status_code == 400
    assert b"CSRF" in response.data


def test_csrf_accepts_token_from_page(settings, tmp_path, jobs):
    storage = JobStorage(tmp_path / "csrf-token.db")
    app = create_app(
        settings,
        config={
            "TESTING": True,
            "WTF_CSRF_ENABLED": True,
            "WTF_CSRF_CHECK_DEFAULT": True,
            "TRUSTSTORE_ENABLED": False,
        },
        storage_instance=storage,
        wttj_scraper_instance=FakeWTTJScraper([jobs[0]]),
        greenhouse_scraper_instance=FakeCompanyScraper([]),
        lever_scraper_instance=FakeCompanyScraper([]),
    )
    with app.test_client() as client:
        page = client.get("/")
        token = re.search(
            br'<meta name="csrf-token" content="([^"]+)"',
            page.data,
        ).group(1).decode()
        response = client.post(
            "/save",
            json=jobs[0].to_dict(),
            headers={"X-CSRFToken": token},
        )
    storage.close()

    assert response.status_code == 200
