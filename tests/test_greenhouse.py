import pytest
import responses

from scraper.greenhouse import GREENHOUSE_API, GreenhouseScraper


def greenhouse_job(**overrides):
    job = {
        "title": "Python Engineer",
        "company_name": "Example",
        "location": {"name": "Paris, France"},
        "absolute_url": "https://boards.example.test/python",
        "first_published": "2026-09-01T12:00:00",
        "metadata": [{"name": "Time Type", "value": "Full-time"}],
    }
    job.update(overrides)
    return job


@responses.activate
def test_search_parses_metadata_and_uses_timeout():
    scraper = GreenhouseScraper(timeout=7)
    responses.add(
        responses.GET,
        GREENHOUSE_API.format(slug="example"),
        json={"jobs": [greenhouse_job()]},
        status=200,
    )

    jobs = scraper.search(["example"])

    assert jobs[0].source == "Greenhouse"
    assert jobs[0].contract_type == "Full-time"
    assert jobs[0].location == "Paris, France"
    assert jobs[0].url == "https://boards.example.test/python"
    assert jobs[0].published_at == "2026-09-01T12:00:00"
    assert responses.calls[0].request.url.endswith("/example/jobs")


def test_contract_type_inference_and_filters():
    scraper = GreenhouseScraper()
    jobs = [
        scraper._parse_hit(
            greenhouse_job(title="Stage Python", metadata=[]),
            "example",
        ),
        scraper._parse_hit(
            greenhouse_job(
                title="Contract Consultant",
                company_name="Other Company",
                location={"name": "Lyon"},
                metadata=[],
            ),
            "example",
        ),
    ]

    assert jobs[0].contract_type == "Internship"
    assert jobs[1].contract_type == "Contract"
    assert scraper._filter(jobs, ["python"], "Paris") == [jobs[0]]
    assert scraper._filter(jobs, ["other"], None) == [jobs[1]]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Freelance consultant", "Freelance"),
        ("Part-time engineer", "Part-time"),
        ("Permanent engineer", ""),
    ],
)
def test_remaining_contract_type_inference_categories(title, expected):
    job = GreenhouseScraper()._parse_hit(
        greenhouse_job(title=title, metadata=[]),
        "example",
    )

    assert job.contract_type == expected


def test_malformed_optional_fields_are_safe():
    job = GreenhouseScraper()._parse_hit(
        {
            "title": "Temporary job",
            "location": None,
            "metadata": None,
        },
        "example",
    )

    assert job.location == "Non précisé"
    assert job.url == ""
    assert job.contract_type == "Contract"


@responses.activate
def test_search_skips_malformed_records_and_applies_local_filters():
    responses.add(
        responses.GET,
        GREENHOUSE_API.format(slug="example"),
        json={
            "jobs": [
                None,
                greenhouse_job(title="Python Engineer"),
                greenhouse_job(title="Pythonesque Engineer"),
            ]
        },
        status=200,
    )

    jobs = GreenhouseScraper().search(
        ["example"],
        keywords=[" python "],
        location=" paris ",
    )

    assert [job.title for job in jobs] == ["Python Engineer"]


@responses.activate
def test_invalid_response_shape_is_ignored():
    responses.add(
        responses.GET,
        GREENHOUSE_API.format(slug="example"),
        json=[],
        status=200,
    )

    assert GreenhouseScraper().search(["example"]) == []


@responses.activate
def test_one_company_failure_does_not_discard_other_companies():
    scraper = GreenhouseScraper()
    responses.add(
        responses.GET,
        GREENHOUSE_API.format(slug="bad"),
        status=404,
    )
    responses.add(
        responses.GET,
        GREENHOUSE_API.format(slug="good"),
        json={"jobs": [greenhouse_job()]},
        status=200,
    )

    jobs = scraper.search(["bad", "good"])

    assert len(jobs) == 1
    assert jobs[0].company == "Example"
