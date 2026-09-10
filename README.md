# Job Scraper

Moteur de recherche d'offres d'emploi avec interface web Flask et architecture extensible pour plusieurs sources.

## Fonctionnalités

- **Recherche multi-critères** : mots-clés, localisation, entreprise, type de contrat, remote et salaire.
- **Sources multiples** : Welcome to the Jungle, Greenhouse et Lever.
- **Sauvegarde individuelle** avec labels.
- **Déduplication** par URL.
- **Stockage SQLite** persistant.
- **Protection CSRF** pour les opérations qui modifient les données.
- **Déploiement Docker** sur Azure App Service for Containers.

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.11+, Flask |
| Scraping | Algolia/WTTJ, Greenhouse API, Lever API |
| Base de données | SQLite |
| Serveur | Gunicorn |
| Tests | pytest, coverage, responses, Playwright |
| CI/CD | GitHub Actions, Docker, GHCR |
| Déploiement | Azure App Service for Containers |

## Configuration

Les secrets et les paramètres provider ne sont jamais stockés dans le dépôt.

| Variable | Obligatoire | Description |
|---|---:|---|
| `APP_ENV` | production | `development`, `testing` ou `production`. |
| `SECRET_KEY` | production | Secret Flask fort et unique. |
| `WTTJ_APP_ID` | production/WTTJ | Application ID Algolia WTTJ. |
| `WTTJ_API_KEY` | production/WTTJ | Clé Algolia WTTJ. |
| `WTTJ_INDEX_NAME` | non | Index Algolia, avec une valeur par défaut. |
| `DB_PATH` | non | Chemin SQLite. Azure utilise `/home/jobs.db` par défaut. |
| `CSRF_ENABLED` | non | Activé par défaut. |
| `COOKIE_SECURE` | non | Activé par défaut en production. |
| `TRUSTSTORE_ENABLED` | non | Utilisation du magasin de certificats système, activée par défaut. |
| `WTTJ_CONNECT_TIMEOUT` | non | Timeout de connexion en secondes. |
| `WTTJ_READ_TIMEOUT` | non | Timeout de lecture en secondes. |
| `WTTJ_DELAY` | non | Délai entre les pages Algolia. |

Chaque offre sauvegardée doit contenir explicitement l'une des sources suivantes : `WTTJ`, `Greenhouse` ou `Lever`. Une source absente ou inconnue est rejetée.

## Développement local

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt

export APP_ENV=development
export WTTJ_APP_ID=<algolia-app-id>
export WTTJ_API_KEY=<algolia-api-key>
.venv/bin/python app.py
```

Le site est accessible sur `http://127.0.0.1:5000`.

## Docker

Construire et lancer l'image runtime :

```bash
docker build --target runtime -t job-scraper:local .
docker run --rm -p 8000:8000 \
  -e APP_ENV=development \
  -e SECRET_KEY=local-development-secret \
  -e WTTJ_APP_ID=<algolia-app-id> \
  -e WTTJ_API_KEY=<algolia-api-key> \
  -v job-scraper-data:/home \
  job-scraper:local
```

Le health check est disponible sur `http://127.0.0.1:8000/health`.

Construire l'image de test et lancer les tests backend :

```bash
docker build --target test -t job-scraper:test .
docker run --rm \
  -e APP_ENV=testing \
  -e SECRET_KEY=test-secret \
  -e CSRF_ENABLED=false \
  -e TRUSTSTORE_ENABLED=false \
  job-scraper:test pytest -m "not e2e" --cov
```

Les tests navigateur utilisent la cible `e2e` :

```bash
docker build --target e2e -t job-scraper:e2e .
docker run --rm --ipc=host job-scraper:e2e pytest -m e2e --browser chromium
```

## Tests et qualité

Les tests backend utilisent des bases SQLite temporaires et des réponses provider simulées. Aucun test normal ne doit contacter WTTJ, Greenhouse ou Lever.

```bash
.venv/bin/pytest -m "not e2e" --cov --cov-report=term-missing
.venv/bin/ruff check .
.venv/bin/mypy app.py config.py data scraper
.venv/bin/bandit --recursive app.py config.py data scraper
.venv/bin/pip-audit -r requirements.txt
```

Les workflows GitHub Actions exécutent ces contrôles dans Docker pour les pull requests et la branche principale.

## Déploiement Azure

Le workflow `release.yml` publie une image runtime immuable dans GHCR pour chaque tag `vX.Y.Z`, puis déploie le même digest vers Azure App Service for Containers.

Configurer dans l'environnement GitHub `staging` ou `production` :

- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` et `AZURE_SUBSCRIPTION_ID` comme secrets OIDC.
- `AZURE_WEBAPP_NAME` comme variable d'environnement.
- `SECRET_KEY`, `WTTJ_APP_ID` et `WTTJ_API_KEY` dans la configuration Azure, jamais dans GitHub Actions ou le dépôt.
- Un volume persistant Azure pour `/home`, qui contient `/home/jobs.db`.

La production doit être protégée par approbation. Le rollback se fait en redéployant le digest GHCR de la dernière image saine.

## Structure du projet

```text
├── app.py
├── config.py
├── data/
│   └── storage.py
├── scraper/
│   ├── base.py
│   ├── greenhouse.py
│   ├── lever.py
│   └── wttj.py
├── tests/
│   ├── e2e/
│   ├── test_app.py
│   ├── test_config.py
│   ├── test_greenhouse.py
│   ├── test_lever.py
│   ├── test_salary.py
│   ├── test_storage.py
│   └── test_wttj.py
├── web/
│   ├── templates/
│   └── static/
├── Dockerfile
├── action.md
├── plan.md
└── report.md
```
