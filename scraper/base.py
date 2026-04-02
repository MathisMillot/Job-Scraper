"""Classe abstraite pour tous les scrapers."""
from abc import ABC, abstractmethod
from scraper.wttj import Job


class BaseScraper(ABC):
    """Interface commune pour les scrapers d'offres d'emploi."""

    @abstractmethod
    def search(
        self,
        keywords: list[str] | None = None,
        location: str | None = None,
        company: str | None = None,
    ) -> list[Job]:
        """Recherche des offres et retourne une liste de Job."""
        ...
