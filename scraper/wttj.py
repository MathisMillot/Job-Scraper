import os
import time
from dataclasses import asdict, dataclass

import requests

DEFAULT_INDEX_NAME = "wttj_jobs_production_fr"
DEFAULT_BASE_URL = "https://www.welcometothejungle.com/fr/companies"

# Values accepted by the WTTJ API.
CONTRACT_TYPES = [
    "full_time",
    "part_time",
    "internship",
    "apprenticeship",
    "freelance",
    "temporary",
    "vie",
    "graduate_program",
]
REMOTE_OPTIONS = ["no", "punctual", "partial", "fulltime"]


class WTTJConfigurationError(RuntimeError):
    """Raised when a WTTJ request cannot be configured safely."""


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    published_at: str
    contract_type: str
    remote: str
    salary: str | None = None
    source: str = "WTTJ"

    def to_dict(self) -> dict:
        return asdict(self)


class WTTJScraper:
    """Scraper for Welcome to the Jungle through the Algolia API."""

    def __init__(
        self,
        hits_per_page: int = 20,
        delay: float = 0.5,
        *,
        app_id: str | None = None,
        api_key: str | None = None,
        index_name: str | None = None,
        timeout: tuple[float, float] = (10.0, 30.0),
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.hits_per_page = hits_per_page
        self.delay = delay
        self.app_id = (app_id if app_id is not None else os.getenv("WTTJ_APP_ID", "")).strip()
        self.api_key = (
            api_key if api_key is not None else os.getenv("WTTJ_API_KEY", "")
        ).strip()
        self.index_name = (
            index_name
            if index_name is not None
            else os.getenv("WTTJ_INDEX_NAME", DEFAULT_INDEX_NAME)
        ).strip()
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Referer": "https://www.welcometothejungle.com/",
                "Content-Type": "application/json",
            }
        )
        if self.app_id:
            self.session.headers["X-Algolia-Application-Id"] = self.app_id
        if self.api_key:
            self.session.headers["X-Algolia-API-Key"] = self.api_key

    @property
    def query_url(self) -> str:
        return f"https://{self.app_id}-dsn.algolia.net/1/indexes/{self.index_name}/query"

    @property
    def multi_query_url(self) -> str:
        return f"https://{self.app_id}-dsn.algolia.net/1/indexes/*/queries"

    def _ensure_configured(self) -> None:
        if not self.app_id or not self.api_key:
            raise WTTJConfigurationError(
                "WTTJ_APP_ID and WTTJ_API_KEY must be configured before searching"
            )

    def _build_facet_filters(
        self,
        contract_type: str | list[str] | None = None,
        remote: str | None = None,
        company: str | None = None,
        location: str | None = None,
    ) -> list:
        """Build Algolia facet filters."""
        facet_filters: list[str | list[str]] = []
        if contract_type:
            if isinstance(contract_type, str):
                facet_filters.append(f"contract_type:{contract_type}")
            else:
                facet_filters.append([f"contract_type:{ct}" for ct in contract_type])
        if remote:
            facet_filters.append(f"remote:{remote}")
        if company:
            facet_filters.append(f"organization.name:{company}")
        if location:
            facet_filters.append(f"offices.city:{location}")
        return facet_filters

    def search(
        self,
        query: str = "",
        contract_type: str | list[str] | None = None,
        remote: str | None = None,
        company: str | None = None,
        location: str | None = None,
        page: int = 0,
    ) -> tuple[list[Job], int]:
        """Search jobs with one Algolia query."""
        self._ensure_configured()
        facet_filters = self._build_facet_filters(
            contract_type, remote, company, location
        )
        payload: dict[str, object] = {
            "query": query,
            "hitsPerPage": self.hits_per_page,
            "page": page,
        }
        if facet_filters:
            payload["facetFilters"] = facet_filters

        response = self.session.post(
            self.query_url,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        hits = result["hits"]
        nb_pages = result["nbPages"]
        return [self._parse_hit(hit) for hit in hits], nb_pages

    def search_multi_keywords(
        self,
        keywords: list[str],
        contract_type: str | list[str] | None = None,
        remote: str | None = None,
        company: str | None = None,
        location: str | None = None,
        max_pages: int = 3,
    ) -> list[Job]:
        """Search multiple keywords with OR semantics and URL deduplication."""
        self._ensure_configured()
        if not keywords:
            return self.search_all_pages(
                query="",
                contract_type=contract_type,
                remote=remote,
                company=company,
                location=location,
                max_pages=max_pages,
            )
        if len(keywords) == 1:
            return self.search_all_pages(
                query=keywords[0],
                contract_type=contract_type,
                remote=remote,
                company=company,
                location=location,
                max_pages=max_pages,
            )

        seen_urls: set[str] = set()
        all_jobs: list[Job] = []
        for page in range(max_pages):
            facet_filters = self._build_facet_filters(
                contract_type, remote, company, location
            )
            requests_list: list[dict[str, object]] = []
            for keyword in keywords:
                request_payload: dict[str, object] = {
                    "indexName": self.index_name,
                    "query": keyword,
                    "hitsPerPage": self.hits_per_page,
                    "page": page,
                }
                if facet_filters:
                    request_payload["facetFilters"] = facet_filters
                requests_list.append(request_payload)

            response = self.session.post(
                self.multi_query_url,
                json={"requests": requests_list},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            page_has_results = False
            for result in data["results"]:
                if result["hits"]:
                    page_has_results = True
                for hit in result["hits"]:
                    job = self._parse_hit(hit)
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)

            if not page_has_results:
                break
            if page + 1 < max_pages:
                time.sleep(self.delay)

        return all_jobs

    def search_all_pages(
        self,
        query: str = "",
        contract_type: str | list[str] | None = None,
        remote: str | None = None,
        company: str | None = None,
        location: str | None = None,
        max_pages: int = 5,
    ) -> list[Job]:
        """Search multiple pages with a delay between requests."""
        all_jobs = []
        for page in range(max_pages):
            jobs, nb_pages = self.search(
                query=query,
                contract_type=contract_type,
                remote=remote,
                company=company,
                location=location,
                page=page,
            )
            all_jobs.extend(jobs)
            if page + 1 >= nb_pages:
                break
            time.sleep(self.delay)
        return all_jobs

    def _parse_hit(self, hit: dict) -> Job:
        """Transform one Algolia result into a Job."""
        organization = hit.get("organization") or {}
        offices = hit.get("offices") or []
        first_office = offices[0] if offices and isinstance(offices[0], dict) else {}
        location = first_office.get("city", "Non précisé") or "Non précisé"

        organization_slug = organization.get("slug", "")
        job_slug = hit.get("slug", "")
        url = f"{self.base_url}/{organization_slug}/jobs/{job_slug}"

        return Job(
            title=hit.get("name", "") or "",
            company=organization.get("name", "") or "",
            location=location,
            url=url,
            published_at=hit.get("published_at", "") or "",
            contract_type=hit.get("contract_type", "") or "",
            remote=hit.get("remote", "") or "",
            salary=self._format_salary(hit),
            source="WTTJ",
        )

    def _format_salary(self, hit: dict) -> str | None:
        """Format salary data from Algolia."""
        salary_minimum = hit.get("salary_minimum")
        salary_maximum = hit.get("salary_maximum")
        currency = hit.get("salary_currency", "EUR")
        period = hit.get("salary_period", "yearly")

        if salary_minimum is None and salary_maximum is None:
            return None

        period_label = {
            "yearly": "/an",
            "monthly": "/mois",
            "daily": "/jour",
        }.get(period, "")

        if salary_minimum is not None and salary_maximum is not None:
            return f"{salary_minimum}-{salary_maximum} {currency}{period_label}"
        if salary_minimum is not None:
            return f"{salary_minimum}+ {currency}{period_label}"
        return f"≤{salary_maximum} {currency}{period_label}"
