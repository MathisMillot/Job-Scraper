"""Scraper for companies using Lever as their ATS."""

import logging
from datetime import UTC, datetime

import requests

from scraper.wttj import Job

logger = logging.getLogger(__name__)
LEVER_API = "https://api.lever.co/v0/postings/{slug}"


class LeverScraper:
    """Retrieve job postings through the public Lever API."""

    def __init__(self, timeout: float = 20):
        self.timeout = timeout
        self.session = requests.Session()

    def search(
        self,
        company_slugs: list[str],
        keywords: list[str] | None = None,
        location: str | None = None,
    ) -> list[Job]:
        """Fetch all configured companies and filter their jobs locally."""
        all_jobs: list[Job] = []
        for slug in company_slugs:
            try:
                all_jobs.extend(self._fetch_company(slug))
            except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
                logger.warning("Lever: failed to fetch %r: %s", slug, exc)

        if keywords or location:
            return self._filter(all_jobs, keywords, location)
        return all_jobs

    def _fetch_company(self, slug: str) -> list[Job]:
        """Fetch all jobs for one Lever company."""
        response = self.session.get(
            LEVER_API.format(slug=slug),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("Lever response must be a list")

        jobs = []
        for hit in data:
            if not isinstance(hit, dict):
                logger.warning("Lever: skipped malformed job for %r", slug)
                continue
            jobs.append(self._parse_hit(hit, slug))
        return jobs

    def _parse_hit(self, hit: dict, slug: str) -> Job:
        categories = hit.get("categories") or {}
        if not isinstance(categories, dict):
            categories = {}
        location = categories.get("location", "Non précisé") or "Non précisé"
        commitment = categories.get("commitment", "") or ""

        created_at = hit.get("createdAt")
        published_at = ""
        if created_at is not None:
            try:
                published_at = datetime.fromtimestamp(
                    float(created_at) / 1000,
                    tz=UTC,
                ).strftime("%Y-%m-%dT%H:%M:%S")
            except (OverflowError, TypeError, ValueError):
                logger.warning("Lever: invalid createdAt value %r", created_at)

        workplace = str(hit.get("workplaceType", "") or "")
        remote = workplace if workplace in {"remote", "hybrid"} else ""

        return Job(
            title=str(hit.get("text", "") or ""),
            company=slug.replace("-", " ").title(),
            location=str(location),
            url=str(hit.get("hostedUrl", "") or ""),
            published_at=published_at,
            contract_type=str(commitment),
            remote=remote,
            salary=None,
            source="Lever",
        )

    def _filter(
        self,
        jobs: list[Job],
        keywords: list[str] | None,
        location: str | None,
    ) -> list[Job]:
        """Filter jobs locally by OR keyword and location matches."""
        filtered = jobs
        if location and location.strip():
            location_lower = location.strip().lower()
            filtered = [
                job
                for job in filtered
                if location_lower in (job.location or "").lower()
            ]

        clean_keywords = [
            keyword.strip().lower()
            for keyword in (keywords or [])
            if keyword and keyword.strip()
        ]
        if clean_keywords:
            filtered = [
                job
                for job in filtered
                if any(
                    keyword in job.title.lower() or keyword in job.company.lower()
                    for keyword in clean_keywords
                )
            ]
        return filtered
