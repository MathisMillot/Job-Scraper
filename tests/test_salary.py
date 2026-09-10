from app import _filter_by_salary


def make_job(salary):
    from scraper.wttj import Job

    return Job(
        title="Job",
        company="Example",
        location="Paris",
        url=f"https://jobs.example.test/{salary}",
        published_at="",
        contract_type="",
        remote="",
        salary=salary,
    )


def test_salary_ranges_are_lower_inclusive_and_upper_exclusive():
    assert _filter_by_salary([make_job("25000 EUR/an")], "0-25k") == []
    assert _filter_by_salary([make_job("25000 EUR/an")], "25k-35k")
    assert _filter_by_salary([make_job("60000 EUR/an")], "60k+")


def test_monthly_and_daily_salaries_are_normalized():
    assert _filter_by_salary([make_job("2500 EUR/mois")], "25k-35k")
    assert _filter_by_salary([make_job("200 EUR/jour")], "45k-60k")
    assert _filter_by_salary([make_job("60k+ EUR/an")], "60k+")


def test_missing_and_malformed_salaries_are_excluded():
    jobs = [make_job(None), make_job("not available")]
    assert _filter_by_salary(jobs, "0-25k") == []
