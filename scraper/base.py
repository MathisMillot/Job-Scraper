"""Protocols shared by company ATS scrapers."""

from typing import Protocol

from scraper.wttj import Job


class CompanyScraper(Protocol):
    """Interface implemented by Greenhouse and Lever scrapers."""

    def search(
        self,
        company_slugs: list[str],
        keywords: list[str] | None = None,
        location: str | None = None,
    ) -> list[Job]:
        """Return matching jobs for the supplied company slugs."""
        ...
