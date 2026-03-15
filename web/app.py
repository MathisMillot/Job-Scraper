import sys
from pathlib import Path

# Ajouter le dossier racine au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, redirect, url_for, flash
from scraper.wttj import WTTJScraper, CONTRACT_TYPES, REMOTE_OPTIONS
from data.storage import JobStorage

app = Flask(__name__)
app.secret_key = "job-scraper-dev-key"

scraper = WTTJScraper(hits_per_page=20)
storage = JobStorage()


@app.route("/", methods=["GET", "POST"])
def index():
    results = None
    # Valeurs du formulaire pour les conserver après POST
    form = {
        "keywords": [],
        "location": "",
        "company": "",
        "contract_type": "",
        "remote": "",
        "salary_range": "",
    }

    if request.method == "POST":
        keywords_raw = request.form.get("keywords", "").strip()
        form["keywords"] = [k.strip() for k in keywords_raw.split(",") if k.strip()] if keywords_raw else []
        form["location"] = request.form.get("location", "").strip()
        form["company"] = request.form.get("company", "").strip()
        form["contract_type"] = request.form.get("contract_type", "")
        form["remote"] = request.form.get("remote", "")
        form["salary_range"] = request.form.get("salary_range", "")

        # Au moins un champ rempli
        if not any([form["keywords"], form["location"], form["company"],
                     form["contract_type"], form["remote"], form["salary_range"]]):
            flash("Veuillez remplir au moins un champ de recherche.", "error")
            return render_template("index.html", form=form,
                                   contract_types=CONTRACT_TYPES,
                                   remote_options=REMOTE_OPTIONS)

        # Mots-clés en mode OR (chaque tag = une requête séparée)
        jobs = scraper.search_multi_keywords(
            keywords=form["keywords"],
            contract_type=form["contract_type"] or None,
            remote=form["remote"] or None,
            company=form["company"] or None,
            location=form["location"] or None,
            max_pages=3,
        )

        # Filtrer par salaire si spécifié
        if form["salary_range"]:
            jobs = _filter_by_salary(jobs, form["salary_range"])

        total_scraped = len(jobs)
        new_jobs = storage.add(jobs)
        new_count = len(new_jobs)
        results = [j.to_dict() for j in jobs]

        flash(f"{total_scraped} offres trouvées, {new_count} nouvelles sauvegardées.", "success")

    return render_template("index.html",
                           results=results,
                           form=form,
                           contract_types=CONTRACT_TYPES,
                           remote_options=REMOTE_OPTIONS)


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
    """Filtre les jobs par tranche de salaire annuel."""
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
