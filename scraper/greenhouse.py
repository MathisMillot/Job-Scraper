"""Scraper for companies using Greenhouse as their ATS."""

import logging
import re

import requests

from scraper.wttj import Job

logger = logging.getLogger(__name__)
GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


class GreenhouseScraper:
    """Retrieve job postings through the public Greenhouse API."""

    def __init__(self, timeout: float = 15):
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
                logger.warning(
                    "Greenhouse: failed to fetch %r: %s",
                    slug,
                    exc,
                )

        if keywords or location:
            return self._filter(all_jobs, keywords, location)
        return all_jobs

    def _fetch_company(self, slug: str) -> list[Job]:
        """Fetch all jobs for one Greenhouse company."""
        response = self.session.get(
            GREENHOUSE_API.format(slug=slug),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Greenhouse response must be an object")

        jobs = []
        for hit in data.get("jobs", []):
            if not isinstance(hit, dict):
                logger.warning("Greenhouse: skipped malformed job for %r", slug)
                continue
            jobs.append(self._parse_hit(hit, slug))
        return jobs

    def _parse_hit(self, hit: dict, slug: str) -> Job:
        location_data = hit.get("location") or {}
        location = (
            location_data.get("name", "Non précisé")
            if isinstance(location_data, dict)
            else "Non précisé"
        ) or "Non précisé"

        contract_type = ""
        metadata = hit.get("metadata") or []
        if isinstance(metadata, list):
            for meta in metadata:
                if isinstance(meta, dict) and meta.get("name") == "Time Type":
                    contract_type = meta.get("value") or ""
                    break

        if not contract_type:
            contract_type = self._infer_contract_type(
                str(hit.get("title", "") or "").lower()
            )

        return Job(
            title=str(hit.get("title", "") or ""),
            company=str(hit.get("company_name", slug) or slug),
            location=str(location),
            url=str(hit.get("absolute_url", "") or ""),
            published_at=str(
                hit.get("first_published", hit.get("updated_at", "")) or ""
            ),
            contract_type=str(contract_type),
            remote="",
            salary=None,
            source="Greenhouse",
        )

    def _infer_contract_type(self, text: str) -> str:
        """Infer the contract type from a job title."""
        text = text.lower()
        if any(word in text for word in ("intern", "stage", "apprenti")):
            return "Internship"
        if any(word in text for word in ("contract", "temporary", "temp", "cdd")):
            return "Contract"
        if any(word in text for word in ("freelance", "consultant")):
            return "Freelance"
        if any(word in text for word in ("part-time", "part time", "parttime")):
            return "Part-time"
        return ""

    def _filter(
        self,
        jobs: list[Job],
        keywords: list[str] | None,
        location: str | None,
    ) -> list[Job]:
        """Filter jobs locally by whole-word keyword and location matches."""
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
                    re.search(r"\b" + re.escape(keyword) + r"\b", job.title.lower())
                    or re.search(
                        r"\b" + re.escape(keyword) + r"\b",
                        job.company.lower(),
                    )
                    for keyword in clean_keywords
                )
            ]
        return filtered
