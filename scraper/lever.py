"""Scraper pour les entreprises utilisant Lever comme ATS."""
import requests
from scraper.wttj import Job


LEVER_API = "https://api.lever.co/v0/postings/{slug}"


class LeverScraper:
    """Récupère les offres d'emploi via l'API publique Lever."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()

    def search(
        self,
        company_slugs: list[str],
        keywords: list[str] | None = None,
        location: str | None = None,
    ) -> list[Job]:
        """Recherche des offres sur Lever pour une liste d'entreprises.

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
        """Récupère toutes les offres d'une entreprise Lever."""
        url = LEVER_API.format(slug=slug)
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for hit in data:
            job = self._parse_hit(hit, slug)
            if job:
                jobs.append(job)
        return jobs

    def _parse_hit(self, hit: dict, slug: str) -> Job | None:
        categories = hit.get("categories", {})
        location = categories.get("location", "Non précisé") or "Non précisé"
        commitment = categories.get("commitment", "")

        # createdAt est un timestamp en millisecondes
        created_at = hit.get("createdAt")
        if created_at:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc)
            published_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            published_at = ""

        workplace = hit.get("workplaceType", "")

        return Job(
            title=hit.get("text", ""),
            company=slug.replace("-", " ").title(),
            location=location,
            url=hit.get("hostedUrl", ""),
            published_at=published_at,
            contract_type=commitment,
            remote=workplace if workplace in ("remote", "hybrid") else "",
            salary=None,
            source="Lever",
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
