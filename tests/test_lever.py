from datetime import UTC, datetime

import pytest
import responses

from scraper.lever import LEVER_API, LeverScraper


def lever_job(**overrides):
    job = {
        "text": "Product Engineer",
        "categories": {
            "location": "Paris",
            "commitment": "Full-time",
        },
        "hostedUrl": "https://jobs.example.test/product",
        "createdAt": 1_757_000_000_000,
        "workplaceType": "remote",
    }
    job.update(overrides)
    return job


@responses.activate
def test_search_parses_timestamp_and_workplace():
    scraper = LeverScraper(timeout=8)
    responses.add(
        responses.GET,
        LEVER_API.format(slug="example-company"),
        json=[lever_job()],
        status=200,
    )

    jobs = scraper.search(["example-company"])

    expected_date = datetime.fromtimestamp(
        1_757_000_000,
        tz=UTC,
    ).strftime("%Y-%m-%dT%H:%M:%S")
    assert jobs[0].source == "Lever"
    assert jobs[0].published_at == expected_date
    assert jobs[0].remote == "remote"
    assert jobs[0].company == "Example Company"
    assert jobs[0].location == "Paris"
    assert jobs[0].contract_type == "Full-time"
    assert jobs[0].salary is None


def test_filter_matches_keyword_or_location():
    scraper = LeverScraper()
    first = scraper._parse_hit(lever_job(text="Python Engineer"), "example")
    second = scraper._parse_hit(
        lever_job(
            text="Product Manager",
            categories={"location": "Lyon", "commitment": "Full-time"},
        ),
        "example",
    )

    assert scraper._filter([first, second], ["python"], None) == [first]
    assert scraper._filter([first, second], None, "lyon") == [second]
    assert scraper._filter([first, second], ["manager", "product"], None) == [second]


def test_invalid_timestamp_and_categories_are_safe():
    job = LeverScraper()._parse_hit(
        {
            "text": "Unknown",
            "categories": None,
            "createdAt": "invalid",
            "workplaceType": "onsite",
        },
        "example",
    )

    assert job.location == "Non précisé"
    assert job.published_at == ""
    assert job.remote == ""


@pytest.mark.parametrize(
    ("created_at", "workplace", "expected_date", "expected_remote"),
    [
        (None, "hybrid", "", "hybrid"),
        (0, "onsite", "1970-01-01T00:00:00", ""),
    ],
)
def test_timestamp_and_workplace_variants(
    created_at,
    workplace,
    expected_date,
    expected_remote,
):
    payload = lever_job(createdAt=created_at, workplaceType=workplace)
    job = LeverScraper()._parse_hit(payload, "example")

    assert job.published_at == expected_date
    assert job.remote == expected_remote


@responses.activate
def test_search_skips_malformed_records_and_invalid_response_shapes():
    responses.add(
        responses.GET,
        LEVER_API.format(slug="mixed"),
        json=[None, lever_job()],
        status=200,
    )
    responses.add(
        responses.GET,
        LEVER_API.format(slug="invalid"),
        json={},
        status=200,
    )

    assert len(LeverScraper().search(["mixed"])) == 1
    assert LeverScraper().search(["invalid"]) == []


@responses.activate
def test_one_company_failure_does_not_discard_other_companies():
    scraper = LeverScraper()
    responses.add(
        responses.GET,
        LEVER_API.format(slug="bad"),
        status=500,
    )
    responses.add(
        responses.GET,
        LEVER_API.format(slug="good"),
        json=[lever_job()],
        status=200,
    )

    jobs = scraper.search(["bad", "good"])

    assert len(jobs) == 1
