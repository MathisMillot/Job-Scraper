"""Flask application entry point for local development and Azure App Service."""

import logging
import re
import sqlite3
from collections.abc import Mapping
from typing import Any

import requests
import truststore
from flask import (
    Flask,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_wtf.csrf import CSRFError, CSRFProtect

from config import VALID_SOURCE_KEYS, Settings
from data.storage import InvalidJobData, JobStorage
from scraper.greenhouse import GreenhouseScraper
from scraper.lever import LeverScraper
from scraper.wttj import (
    CONTRACT_TYPES,
    REMOTE_OPTIONS,
    WTTJConfigurationError,
    WTTJScraper,
)

logger = logging.getLogger(__name__)
csrf = CSRFProtect()

CONTRACT_ALIASES = {
    "internship": ["internship", "intern", "stage"],
    "full_time": ["full_time", "full-time", "full time", "fulltime", "cdi"],
    "part_time": ["part_time", "part-time", "part time", "parttime"],
    "apprenticeship": [
        "apprenticeship",
        "apprentice",
        "alternance",
    ],
    "freelance": ["freelance", "contractor", "contract"],
    "temporary": ["temporary", "temp", "cdd"],
}
SALARY_RANGES: dict[str, tuple[float, float | None]] = {
    "0-25k": (0, 25_000),
    "25k-35k": (25_000, 35_000),
    "35k-45k": (35_000, 45_000),
    "45k-60k": (45_000, 60_000),
    "60k+": (60_000, None),
}
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")


def _storage() -> JobStorage:
    return current_app.extensions["job_storage"]


def _wttj_scraper() -> WTTJScraper:
    return current_app.extensions["wttj_scraper"]


def _greenhouse_scraper() -> GreenhouseScraper:
    return current_app.extensions["greenhouse_scraper"]


def _lever_scraper() -> LeverScraper:
    return current_app.extensions["lever_scraper"]


def _default_form() -> dict[str, Any]:
    return {
        "keywords": [],
        "locations": [],
        "company": "",
        "contract_type": "",
        "remote": "",
        "salary_range": "",
        "sources": ["wttj"],
        "company_slugs": [],
    }


def _render_index(
    *,
    form: dict[str, Any],
    results: list[dict[str, Any]] | None = None,
):
    return render_template(
        "index.html",
        results=results,
        form=form,
        contract_types=CONTRACT_TYPES,
        remote_options=REMOTE_OPTIONS,
    )


def _csv_values(value: str, *, lowercase: bool = False) -> list[str]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    if lowercase:
        return [item.lower() for item in values]
    return values


def _validate_search_form(form: dict[str, Any]) -> list[str]:
    errors = []
    invalid_sources = set(form["sources"]) - VALID_SOURCE_KEYS
    if invalid_sources:
        errors.append("Une source de recherche est invalide.")
    if form["contract_type"] and form["contract_type"] not in CONTRACT_TYPES:
        errors.append("Le type de contrat est invalide.")
    if form["remote"] and form["remote"] not in REMOTE_OPTIONS:
        errors.append("Le filtre remote est invalide.")
    if form["salary_range"] and form["salary_range"] not in SALARY_RANGES:
        errors.append("La tranche salariale est invalide.")
    if len(form["company"]) > 200:
        errors.append("Le nom de l'entreprise est trop long.")
    if len(form["keywords"]) > 20 or any(
        len(keyword) > 100 for keyword in form["keywords"]
    ):
        errors.append("Les mots-clés sont trop nombreux ou trop longs.")
    if len(form["locations"]) > 20 or any(
        len(location) > 100 for location in form["locations"]
    ):
        errors.append("Les localisations sont trop nombreuses ou trop longues.")
    if len(form["company_slugs"]) > 50 or any(
        not SLUG_PATTERN.fullmatch(slug) for slug in form["company_slugs"]
    ):
        errors.append("Un slug d'entreprise est invalide.")
    return errors


def index():
    form = _default_form()
    results = None

    if request.method == "POST":
        submitted_sources = list(dict.fromkeys(request.form.getlist("sources")))
        form["sources"] = submitted_sources or ["wttj"]
        form["keywords"] = _csv_values(request.form.get("keywords", ""))
        form["locations"] = _csv_values(request.form.get("locations", ""))
        form["company"] = request.form.get("company", "").strip()
        form["contract_type"] = request.form.get("contract_type", "").strip()
        form["remote"] = request.form.get("remote", "").strip()
        form["salary_range"] = request.form.get("salary_range", "").strip()
        form["company_slugs"] = _csv_values(
            request.form.get("company_slugs", ""),
            lowercase=True,
        )

        validation_errors = _validate_search_form(form)
        if validation_errors:
            for error in validation_errors:
                flash(error, "error")
            return _render_index(form=form)

        if not any(
            [
                form["keywords"],
                form["locations"],
                form["company"],
                form["contract_type"],
                form["remote"],
                form["salary_range"],
                form["company_slugs"],
            ]
        ):
            flash("Veuillez remplir au moins un champ de recherche.", "error")
            return _render_index(form=form)

        ats_selected = any(
            source in form["sources"] for source in ("greenhouse", "lever")
        )
        if ats_selected and not form["company_slugs"]:
            flash(
                "Veuillez entrer au moins un slug d'entreprise pour Greenhouse/Lever.",
                "error",
            )
            return _render_index(form=form)

        jobs = []
        locations = form["locations"] or [None]
        seen_urls: set[str] = set()
        try:
            if "wttj" in form["sources"]:
                for location in locations:
                    wttj_jobs = _wttj_scraper().search_multi_keywords(
                        keywords=form["keywords"],
                        contract_type=form["contract_type"] or None,
                        remote=form["remote"] or None,
                        company=form["company"] or None,
                        location=location,
                        max_pages=3,
                    )
                    for job in wttj_jobs:
                        if job.url not in seen_urls:
                            seen_urls.add(job.url)
                            jobs.append(job)

            if "greenhouse" in form["sources"] and form["company_slugs"]:
                greenhouse_jobs = _greenhouse_scraper().search(
                    company_slugs=form["company_slugs"],
                    keywords=form["keywords"] or None,
                    location=None,
                )
                if form["locations"]:
                    locations_lower = [location.lower() for location in form["locations"]]
                    greenhouse_jobs = [
                        job
                        for job in greenhouse_jobs
                        if any(
                            location in (job.location or "").lower()
                            for location in locations_lower
                        )
                    ]
                for job in greenhouse_jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        jobs.append(job)

            if "lever" in form["sources"] and form["company_slugs"]:
                lever_jobs = _lever_scraper().search(
                    company_slugs=form["company_slugs"],
                    keywords=form["keywords"] or None,
                    location=None,
                )
                if form["locations"]:
                    locations_lower = [location.lower() for location in form["locations"]]
                    lever_jobs = [
                        job
                        for job in lever_jobs
                        if any(
                            location in (job.location or "").lower()
                            for location in locations_lower
                        )
                    ]
                for job in lever_jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        jobs.append(job)
        except (
            KeyError,
            TypeError,
            ValueError,
            requests.RequestException,
            WTTJConfigurationError,
        ) as exc:
            logger.warning("Job search failed: %s", exc)
            flash(
                "Une source d'offres est temporairement indisponible. "
                "Vérifiez la configuration et réessayez.",
                "error",
            )
            return _render_index(form=form)

        if form["contract_type"]:
            aliases = CONTRACT_ALIASES.get(
                form["contract_type"],
                [form["contract_type"]],
            )
            jobs = [
                job
                for job in jobs
                if job.contract_type
                and any(alias in job.contract_type.lower() for alias in aliases)
            ]
        if form["remote"]:
            remote = form["remote"].lower()
            jobs = [
                job
                for job in jobs
                if job.source == "WTTJ" or remote in (job.remote or "").lower()
            ]
        if form["salary_range"]:
            jobs = _filter_by_salary(jobs, form["salary_range"])

        saved_urls = _storage().saved_urls()
        results = []
        for job in jobs:
            job_dict = job.to_dict()
            job_dict["is_saved"] = job.url in saved_urls
            results.append(job_dict)
        flash(f"{len(results)} offres trouvées.", "success")

    return _render_index(form=form, results=results)


def save_job():
    """Save one job from the browser."""
    job_data = request.get_json(silent=True)
    if not isinstance(job_data, dict):
        return jsonify({"error": "Données JSON manquantes ou invalides"}), 400

    try:
        saved = _storage().save_one(job_data)
        label = job_data.get("label", "")
        if label:
            _storage().add_label(job_data["url"], label)
    except InvalidJobData as exc:
        return jsonify({"error": str(exc)}), 422
    except sqlite3.Error:
        logger.exception("Could not save job")
        return jsonify({"error": "Impossible de sauvegarder cette offre"}), 500
    return jsonify({"saved": saved})


def labels():
    """Return existing labels for the save dialog."""
    return jsonify(_storage().all_labels())


def delete_job():
    """Delete one saved job."""
    job_url = request.form.get("url", "").strip()
    if not job_url:
        return jsonify({"error": "URL manquante"}), 400
    _storage().delete_one(job_url)
    flash("Offre supprimée.", "success")
    return redirect(url_for("saved"))


def saved():
    """Render all saved jobs."""
    jobs = _storage().all(order_by="published_at DESC")
    for job in jobs:
        job["labels"] = _storage().labels_for_job(job["url"])
    return render_template("saved.html", jobs=jobs, count=len(jobs))


def clear():
    """Delete all saved jobs while retaining the label vocabulary."""
    _storage().clear()
    flash("Toutes les offres sauvegardées ont été supprimées.", "success")
    return redirect(url_for("saved"))


def health():
    """Return a provider-independent liveness response."""
    return jsonify({"status": "ok"})


def _salary_amount(salary: str | None) -> float | None:
    if not salary:
        return None
    match = re.search(r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(k)?", salary.lower())
    if not match:
        return None
    amount = float(match.group(1).replace(",", "."))
    if match.group(2):
        amount *= 1000
    lower_salary = salary.lower()
    if "/mois" in lower_salary:
        amount *= 12
    elif "/jour" in lower_salary:
        amount *= 260
    return amount


def _filter_by_salary(jobs, salary_range):
    """Filter normalized annual salary values using half-open ranges."""
    bounds = SALARY_RANGES.get(salary_range)
    if not bounds:
        return jobs
    low, high = bounds
    filtered = []
    for job in jobs:
        amount = _salary_amount(job.salary)
        if amount is None:
            continue
        if amount >= low and (high is None or amount < high):
            filtered.append(job)
    return filtered


def create_app(
    settings: Settings | None = None,
    *,
    config: Mapping[str, Any] | None = None,
    storage_instance: JobStorage | None = None,
    wttj_scraper_instance: WTTJScraper | None = None,
    greenhouse_scraper_instance: GreenhouseScraper | None = None,
    lever_scraper_instance: LeverScraper | None = None,
) -> Flask:
    """Create an application with injectable collaborators for tests."""
    settings = settings or Settings.from_env()
    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.config.from_mapping(
        SECRET_KEY=settings.secret_key,
        TESTING=settings.testing,
        WTF_CSRF_ENABLED=settings.csrf_enabled,
        WTF_CSRF_CHECK_DEFAULT=settings.csrf_enabled,
        SESSION_COOKIE_SECURE=settings.cookie_secure,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        TRUSTSTORE_ENABLED=settings.truststore_enabled,
    )
    if config:
        app.config.from_mapping(config)

    if app.config["TRUSTSTORE_ENABLED"]:
        truststore.inject_into_ssl()
    csrf.init_app(app)

    app.extensions["job_storage"] = storage_instance or JobStorage(settings.db_path)
    app.extensions["wttj_scraper"] = wttj_scraper_instance or WTTJScraper(
        app_id=settings.wttj_app_id,
        api_key=settings.wttj_api_key,
        index_name=settings.wttj_index_name,
        timeout=settings.wttj_timeout,
        delay=settings.wttj_delay,
    )
    app.extensions["greenhouse_scraper"] = (
        greenhouse_scraper_instance or GreenhouseScraper()
    )
    app.extensions["lever_scraper"] = lever_scraper_instance or LeverScraper()
    app.extensions["settings"] = settings

    app.add_url_rule("/", "index", index, methods=["GET", "POST"])
    app.add_url_rule("/save", "save_job", save_job, methods=["POST"])
    app.add_url_rule("/labels", "labels", labels, methods=["GET"])
    app.add_url_rule("/delete", "delete_job", delete_job, methods=["POST"])
    app.add_url_rule("/saved", "saved", saved, methods=["GET"])
    app.add_url_rule("/clear", "clear", clear, methods=["POST"])
    app.add_url_rule("/health", "health", health, methods=["GET"])

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error: CSRFError):
        if request.is_json:
            return jsonify({"error": error.description}), 400
        return error.description, 400

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=False, port=5000)
