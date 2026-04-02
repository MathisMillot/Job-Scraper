import time
import requests
from dataclasses import dataclass, asdict


ALGOLIA_APP_ID = "CSEKHVMS53"
ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
INDEX_NAME = "wttj_jobs_production_fr"
ALGOLIA_QUERY_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{INDEX_NAME}/query"
ALGOLIA_MULTI_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries"

WTTJ_BASE_URL = "https://www.welcometothejungle.com/fr/companies"

# Valeurs acceptées par l'API
CONTRACT_TYPES = ["full_time", "part_time", "internship", "apprenticeship", "freelance", "temporary", "vie", "graduate_program"]
REMOTE_OPTIONS = ["no", "punctual", "partial", "fulltime"]


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
    """Scraper pour Welcome to the Jungle via l'API Algolia."""

    def __init__(self, hits_per_page: int = 20, delay: float = 0.5):
        self.hits_per_page = hits_per_page
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "X-Algolia-Application-Id": ALGOLIA_APP_ID,
            "X-Algolia-API-Key": ALGOLIA_API_KEY,
            "Referer": "https://www.welcometothejungle.com/",
            "Content-Type": "application/json",
        })

    def _build_facet_filters(
        self,
        contract_type: str | list[str] | None = None,
        remote: str | None = None,
        company: str | None = None,
        location: str | None = None,
    ) -> list:
        """Construit la liste de facet filters pour Algolia."""
        facet_filters = []
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
        """Recherche des offres d'emploi (une seule query).

        Returns:
            Tuple (liste de jobs, nombre total de pages)
        """
        facet_filters = self._build_facet_filters(contract_type, remote, company, location)

        payload = {
            "query": query,
            "hitsPerPage": self.hits_per_page,
            "page": page,
        }
        if facet_filters:
            payload["facetFilters"] = facet_filters

        resp = self.session.post(ALGOLIA_QUERY_URL, json=payload)
        resp.raise_for_status()
        result = resp.json()

        hits = result["hits"]
        nb_pages = result["nbPages"]

        jobs = [self._parse_hit(hit) for hit in hits]
        return jobs, nb_pages

    def search_multi_keywords(
        self,
        keywords: list[str],
        contract_type: str | list[str] | None = None,
        remote: str | None = None,
        company: str | None = None,
        location: str | None = None,
        max_pages: int = 3,
    ) -> list[Job]:
        """Recherche OR sur plusieurs mots-clés.

        Lance une requête par mot-clé via l'API multi-query d'Algolia,
        puis fusionne et déduplique les résultats par URL.
        """
        if not keywords:
            return self.search_all_pages(
                query="", contract_type=contract_type, remote=remote,
                company=company, location=location, max_pages=max_pages,
            )

        if len(keywords) == 1:
            return self.search_all_pages(
                query=keywords[0], contract_type=contract_type, remote=remote,
                company=company, location=location, max_pages=max_pages,
            )

        # Plusieurs mots-clés : une requête par keyword, fusionnées en OR
        seen_urls: set[str] = set()
        all_jobs: list[Job] = []

        for page in range(max_pages):
            facet_filters = self._build_facet_filters(contract_type, remote, company, location)
            requests_list = []
            for kw in keywords:
                req = {
                    "indexName": INDEX_NAME,
                    "query": kw,
                    "hitsPerPage": self.hits_per_page,
                    "page": page,
                }
                if facet_filters:
                    req["facetFilters"] = facet_filters
                requests_list.append(req)

            resp = self.session.post(ALGOLIA_MULTI_URL, json={"requests": requests_list})
            resp.raise_for_status()
            data = resp.json()

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
        """Recherche sur plusieurs pages avec délai entre chaque requête."""
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
        """Transforme un résultat Algolia en objet Job."""
        org = hit.get("organization", {})
        offices = hit.get("offices", [])
        location = offices[0].get("city", "Non précisé") if offices else "Non précisé"

        # Construction du lien
        org_slug = org.get("slug", "")
        job_slug = hit.get("slug", "")
        url = f"{WTTJ_BASE_URL}/{org_slug}/jobs/{job_slug}"

        # Salaire
        salary = self._format_salary(hit)

        return Job(
            title=hit.get("name", ""),
            company=org.get("name", ""),
            location=location,
            url=url,
            published_at=hit.get("published_at", ""),
            contract_type=hit.get("contract_type", ""),
            remote=hit.get("remote", ""),
            salary=salary,
        )

    def _format_salary(self, hit: dict) -> str | None:
        """Formate le salaire à partir des données Algolia."""
        sal_min = hit.get("salary_minimum")
        sal_max = hit.get("salary_maximum")
        currency = hit.get("salary_currency", "EUR")
        period = hit.get("salary_period", "yearly")

        if not sal_min and not sal_max:
            return None

        period_label = {"yearly": "/an", "monthly": "/mois", "daily": "/jour"}.get(period, "")

        if sal_min and sal_max:
            return f"{sal_min}-{sal_max} {currency}{period_label}"
        elif sal_min:
            return f"{sal_min}+ {currency}{period_label}"
        else:
            return f"≤{sal_max} {currency}{period_label}"
