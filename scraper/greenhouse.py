"""Scraper pour les entreprises utilisant Greenhouse comme ATS."""
import requests
from scraper.wttj import Job


GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


class GreenhouseScraper:
    """Récupère les offres d'emploi via l'API publique Greenhouse."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()

    def search(
        self,
        company_slugs: list[str],
        keywords: list[str] | None = None,
        location: str | None = None,
    ) -> list[Job]:
        """Recherche des offres sur Greenhouse pour une liste d'entreprises.

        Récupère toutes les offres puis filtre localement par mots-clés et localisation.
        """
        all_jobs: list[Job] = []

        for slug in company_slugs:
            try:
                jobs = self._fetch_company(slug)
                all_jobs.extend(jobs)
            except requests.RequestException:
                continue

        if keywords or location:
            all_jobs = self._filter(all_jobs, keywords, location)

        return all_jobs

    def _fetch_company(self, slug: str) -> list[Job]:
        """Récupère toutes les offres d'une entreprise Greenhouse."""
        url = GREENHOUSE_API.format(slug=slug)
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for hit in data.get("jobs", []):
            job = self._parse_hit(hit, slug)
            if job:
                jobs.append(job)
        return jobs

    def _parse_hit(self, hit: dict, slug: str) -> Job | None:
        loc = hit.get("location", {}).get("name", "Non précisé")

        # Extraire le type de contrat depuis metadata
        contract_type = ""
        for meta in (hit.get("metadata") or []):
            if meta.get("name") == "Time Type":
                contract_type = meta.get("value") or ""
                break

        return Job(
            title=hit.get("title", ""),
            company=hit.get("company_name", slug),
            location=loc,
            url=hit.get("absolute_url", ""),
            published_at=hit.get("first_published", hit.get("updated_at", "")),
            contract_type=contract_type,
            remote="",
            salary=None,
            source="Greenhouse",
        )

    def _filter(
        self,
        jobs: list[Job],
        keywords: list[str] | None,
        location: str | None,
    ) -> list[Job]:
        """Filtre les offres localement par mots-clés (OR) et localisation."""
        filtered = jobs

        if location:
            loc_lower = location.lower()
            filtered = [j for j in filtered if loc_lower in j.location.lower()]

        if keywords:
            kw_lower = [k.lower() for k in keywords]
            filtered = [
                j for j in filtered
                if any(kw in j.title.lower() or kw in j.company.lower() for kw in kw_lower)
            ]

        return filtered
