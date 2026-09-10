import json
from unittest.mock import patch

import pytest
import requests
import responses

from scraper.wttj import (
    WTTJConfigurationError,
    WTTJScraper,
)


def make_hit(slug="python-engineer", name="Python Engineer", **overrides):
    hit = {
        "slug": slug,
        "name": name,
        "published_at": "2026-09-01T12:00:00",
        "contract_type": "full_time",
        "remote": "fulltime",
        "organization": {"slug": "example", "name": "Example"},
        "offices": [{"city": "Paris"}],
    }
    hit.update(overrides)
    return hit


@pytest.fixture
def scraper():
    return WTTJScraper(
        app_id="app",
        api_key="key",
        delay=0,
        timeout=(1, 2),
    )


def test_facet_filters_support_scalar_and_or_contract_filters(scraper):
    assert scraper._build_facet_filters(
        contract_type=["full_time", "internship"],
        remote="fulltime",
        company="Example",
        location="Paris",
    ) == [
        ["contract_type:full_time", "contract_type:internship"],
        "remote:fulltime",
        "organization.name:Example",
        "offices.city:Paris",
    ]


@responses.activate
def test_search_builds_request_and_parses_job(scraper):
    responses.add(
        responses.POST,
        scraper.query_url,
        json={"hits": [make_hit()], "nbPages": 1},
        status=200,
    )

    jobs, pages = scraper.search(
        query="python",
        contract_type="full_time",
        remote="fulltime",
        page=1,
    )

    assert pages == 1
    assert jobs[0].source == "WTTJ"
    assert jobs[0].url.endswith("/example/jobs/python-engineer")
    request = responses.calls[0].request
    assert json.loads(request.body) == {
        "query": "python",
        "hitsPerPage": 20,
        "page": 1,
        "facetFilters": ["contract_type:full_time", "remote:fulltime"],
    }
    assert request.headers["X-Algolia-Application-Id"] == "app"


@pytest.mark.parametrize(
    ("hit", "expected"),
    [
        ({"salary_minimum": 50_000, "salary_maximum": 60_000}, "50000-60000 EUR/an"),
        ({"salary_minimum": 50_000}, "50000+ EUR/an"),
        ({"salary_maximum": 60_000}, "≤60000 EUR/an"),
        ({"salary_minimum": 0, "salary_maximum": 0}, "0-0 EUR/an"),
        (
            {
                "salary_minimum": 4_000,
                "salary_maximum": 5_000,
                "salary_period": "monthly",
                "salary_currency": "USD",
            },
            "4000-5000 USD/mois",
        ),
        ({"salary_minimum": None, "salary_maximum": None}, None),
    ],
)
def test_salary_formatting(scraper, hit, expected):
    assert scraper._format_salary(hit) == expected


@responses.activate
def test_search_all_pages_stops_at_provider_page_count(scraper):
    responses.add(
        responses.POST,
        scraper.query_url,
        json={"hits": [make_hit(slug="one")], "nbPages": 2},
        status=200,
    )
    responses.add(
        responses.POST,
        scraper.query_url,
        json={"hits": [make_hit(slug="two")], "nbPages": 2},
        status=200,
    )
    responses.add(
        responses.POST,
        scraper.query_url,
        json={"hits": [make_hit(slug="three")], "nbPages": 10},
        status=200,
    )

    with patch("scraper.wttj.time.sleep") as sleep:
        jobs = scraper.search_all_pages(max_pages=2)

    assert [job.url.rsplit("/", 1)[-1] for job in jobs] == ["one", "two"]
    sleep.assert_called_once_with(0)


@responses.activate
def test_multi_keyword_search_deduplicates_and_stops_on_empty_page(scraper):
    responses.add(
        responses.POST,
        scraper.multi_query_url,
        json={
            "results": [
                {"hits": [make_hit(slug="same"), make_hit(slug="one")]},
                {"hits": [make_hit(slug="same"), make_hit(slug="two")]},
            ]
        },
        status=200,
    )
    responses.add(
        responses.POST,
        scraper.multi_query_url,
        json={"results": [{"hits": []}, {"hits": []}]},
        status=200,
    )

    jobs = scraper.search_multi_keywords(["python", "data"], max_pages=5)

    assert [job.url.rsplit("/", 1)[-1] for job in jobs] == ["same", "one", "two"]
    assert len(responses.calls) == 2


def test_unconfigured_scraper_fails_clearly():
    with pytest.raises(WTTJConfigurationError):
        WTTJScraper(delay=0).search()


@responses.activate
def test_search_propagates_http_errors(scraper):
    responses.add(responses.POST, scraper.query_url, status=503)

    with pytest.raises(requests.HTTPError):
        scraper.search()
