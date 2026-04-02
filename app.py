"""Point d'entrée pour Azure App Service et développement local."""
import os
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from scraper.wttj import WTTJScraper, CONTRACT_TYPES, REMOTE_OPTIONS
from scraper.greenhouse import GreenhouseScraper
from scraper.lever import LeverScraper
from data.storage import JobStorage

# Sur Azure Linux, /home est le seul dossier persistant
if os.environ.get("WEBSITE_SITE_NAME"):
    db_path = Path("/home/jobs.db")
else:
    db_path = Path(__file__).parent / "data" / "jobs.db"

app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static",
)
app.secret_key = os.environ.get("SECRET_KEY", "job-scraper-dev-key")

wttj_scraper = WTTJScraper(hits_per_page=20)
greenhouse_scraper = GreenhouseScraper()
lever_scraper = LeverScraper()
storage = JobStorage(db_path=db_path)


@app.route("/", methods=["GET", "POST"])
def index():
    results = None
    form = {
        "keywords": [],
        "locations": [],
        "company": "",
        "contract_type": "",
        "remote": "",
        "salary_range": "",
        "sources": ["wttj"],
        "company_slugs": [],
    }

    if request.method == "POST":
        keywords_raw = request.form.get("keywords", "").strip()
        form["keywords"] = [k.strip() for k in keywords_raw.split(",") if k.strip()] if keywords_raw else []
        locations_raw = request.form.get("locations", "").strip()
        form["locations"] = [l.strip() for l in locations_raw.split(",") if l.strip()] if locations_raw else []
        form["company"] = request.form.get("company", "").strip()
        form["contract_type"] = request.form.get("contract_type", "")
        form["remote"] = request.form.get("remote", "")
        form["salary_range"] = request.form.get("salary_range", "")
        form["sources"] = request.form.getlist("sources") or ["wttj"]
        slugs_raw = request.form.get("company_slugs", "").strip()
        form["company_slugs"] = [s.strip().lower() for s in slugs_raw.split(",") if s.strip()] if slugs_raw else []

        # Greenhouse/Lever nécessitent au moins un slug d'entreprise
        ats_selected = any(s in form["sources"] for s in ("greenhouse", "lever"))
        has_wttj = "wttj" in form["sources"]

        if not any([form["keywords"], form["locations"], form["company"],
                     form["contract_type"], form["remote"], form["salary_range"],
                     form["company_slugs"]]):
            flash("Veuillez remplir au moins un champ de recherche.", "error")
            return render_template("index.html", form=form,
                                   contract_types=CONTRACT_TYPES,
                                   remote_options=REMOTE_OPTIONS)

        if ats_selected and not form["company_slugs"]:
            flash("Veuillez entrer au moins un slug d'entreprise pour Greenhouse/Lever.", "error")
            return render_template("index.html", form=form,
                                   contract_types=CONTRACT_TYPES,
                                   remote_options=REMOTE_OPTIONS)

        jobs = []
        locations = form["locations"] or [None]
        seen_urls: set[str] = set()

        # WTTJ : une requête par localisation, dédupliquées
        if has_wttj:
            for loc in locations:
                wttj_jobs = wttj_scraper.search_multi_keywords(
                    keywords=form["keywords"],
                    contract_type=form["contract_type"] or None,
                    remote=form["remote"] or None,
                    company=form["company"] or None,
                    location=loc,
                    max_pages=3,
                )
                for j in wttj_jobs:
                    if j.url not in seen_urls:
                        seen_urls.add(j.url)
                        jobs.append(j)

        # Greenhouse : filtre multi-localisations côté client
        if "greenhouse" in form["sources"] and form["company_slugs"]:
            gh_jobs = greenhouse_scraper.search(
                company_slugs=form["company_slugs"],
                keywords=form["keywords"] or None,
                location=None,
            )
            if form["locations"]:
                locs_lower = [l.lower() for l in form["locations"]]
                gh_jobs = [j for j in gh_jobs if any(l in j.location.lower() for l in locs_lower)]
            for j in gh_jobs:
                if j.url not in seen_urls:
                    seen_urls.add(j.url)
                    jobs.append(j)

        # Lever : filtre multi-localisations côté client
        if "lever" in form["sources"] and form["company_slugs"]:
            lever_jobs = lever_scraper.search(
                company_slugs=form["company_slugs"],
                keywords=form["keywords"] or None,
                location=None,
            )
            if form["locations"]:
                locs_lower = [l.lower() for l in form["locations"]]
                lever_jobs = [j for j in lever_jobs if any(l in j.location.lower() for l in locs_lower)]
            for j in lever_jobs:
                if j.url not in seen_urls:
                    seen_urls.add(j.url)
                    jobs.append(j)

        # Filtres contract_type et remote appliqués côté client
        # (WTTJ les applique déjà via Algolia, mais Greenhouse/Lever non)
        # Mapping WTTJ → termes ATS (Greenhouse/Lever utilisent des noms différents)
        CONTRACT_ALIASES = {
            "internship": ["intern", "internship", "stage"],
            "full_time": ["full-time", "full time", "fulltime", "cdi"],
            "part_time": ["part-time", "part time", "parttime"],
            "apprenticeship": ["apprentice", "apprenticeship", "alternance"],
            "freelance": ["freelance", "contractor", "contract"],
            "temporary": ["temporary", "temp", "cdd"],
        }
        if form["contract_type"]:
            ct = form["contract_type"].lower()
            aliases = CONTRACT_ALIASES.get(ct, [ct])
            jobs = [j for j in jobs if j.source == "WTTJ" or
                    any(a in j.contract_type.lower() for a in aliases)]
        if form["remote"]:
            rm = form["remote"].lower()
            jobs = [j for j in jobs if j.source == "WTTJ" or rm in j.remote.lower()]

        if form["salary_range"]:
            jobs = _filter_by_salary(jobs, form["salary_range"])

        # Marquer les offres déjà sauvegardées
        saved = storage.saved_urls()
        results = []
        for j in jobs:
            d = j.to_dict()
            d["is_saved"] = j.url in saved
            results.append(d)

        flash(f"{len(results)} offres trouvées.", "success")

    return render_template("index.html",
                           results=results,
                           form=form,
                           contract_types=CONTRACT_TYPES,
                           remote_options=REMOTE_OPTIONS)


@app.route("/save", methods=["POST"])
def save_job():
    """Sauvegarde une offre individuelle (appelé en AJAX)."""
    job_data = request.get_json()
    if not job_data or not job_data.get("url"):
        return jsonify({"error": "Données manquantes"}), 400

    saved = storage.save_one(job_data)
    return jsonify({"saved": saved})


@app.route("/delete", methods=["POST"])
def delete_job():
    """Supprime une offre individuelle."""
    url = request.form.get("url")
    if url:
        storage.delete_one(url)
        flash("Offre supprimée.", "success")
    return redirect(url_for("saved"))


@app.route("/saved")
def saved():
    jobs = storage.all(order_by="published_at DESC")
    return render_template("saved.html", jobs=jobs, count=len(jobs))


@app.route("/clear", methods=["POST"])
def clear():
    storage.clear()
    flash("Toutes les offres sauvegardées ont été supprimées.", "success")
    return redirect(url_for("saved"))


def _filter_by_salary(jobs, salary_range):
    ranges = {
        "0-25k": (0, 25000),
        "25k-35k": (25000, 35000),
        "35k-45k": (35000, 45000),
        "45k-60k": (45000, 60000),
        "60k+": (60000, float("inf")),
    }
    bounds = ranges.get(salary_range)
    if not bounds:
        return jobs

    low, high = bounds
    filtered = []
    for job in jobs:
        if not job.salary:
            continue
        try:
            num = float(job.salary.split("-")[0].replace("+", "").replace("≤", ""))
            if low <= num <= high:
                filtered.append(job)
        except (ValueError, IndexError):
            continue
    return filtered


if __name__ == "__main__":
    app.run(debug=True, port=5000)
