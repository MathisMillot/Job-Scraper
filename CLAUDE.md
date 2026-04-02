# Job Scraper - CLAUDE.md

## Objectif
Scraper d'offres d'emploi multi-sources avec interface web. Sources : Welcome to the Jungle (WTTJ), Greenhouse, Lever.

## Architecture
```
job-scraper/
├── scraper/
│   ├── __init__.py        # exporte WTTJScraper, GreenhouseScraper, LeverScraper
│   ├── base.py            # classe abstraite BaseScraper
│   ├── wttj.py            # client Algolia via requests (+ dataclass Job)
│   ├── greenhouse.py      # scraper API Greenhouse (ATS)
│   └── lever.py           # scraper API Lever (ATS)
├── data/
│   ├── __init__.py        # exporte JobStorage
│   ├── storage.py         # stockage SQLite + déduplication par URL
│   └── jobs.db            # base SQLite (auto-généré)
├── web/
│   ├── templates/         # templates HTML (base, index, saved)
│   └── static/            # CSS
├── app.py                 # point d'entrée Flask (racine, pour Azure + local)
├── startup.sh             # commande de démarrage Azure (gunicorn)
├── .gitignore
├── requirements.txt
└── CLAUDE.md
```

## Sources de données

### WTTJ (Algolia)
- Requête directe à l'API Algolia (pas de Selenium/Playwright)
- App ID : `CSEKHVMS53`, Index : `wttj_jobs_production_fr`
- Clé API publique : `4bd8f6215d0cc52b26430765769e65a0`
- Headers requis : `X-Algolia-Application-Id`, `X-Algolia-API-Key`, `Referer: https://www.welcometothejungle.com/`
- Recherche multi-mots-clés en mode OR via multi-query Algolia
- Filtrage par facets : `organization.name`, `offices.city`, `contract_type`, `remote`
- Important : le client officiel `algoliasearch` ne marche pas (pas de support header Referer)

### Greenhouse (ATS)
- API publique : `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`
- Zéro authentification, retourne du JSON
- Couvre ~8000 entreprises (Datadog, Cloudflare, Stripe, etc.)
- L'utilisateur fournit les slugs d'entreprises à chercher
- Filtrage par mots-clés et localisation fait côté client (l'API ne supporte pas de recherche textuelle)

### Lever (ATS)
- API publique : `GET https://api.lever.co/v0/postings/{slug}`
- Zéro authentification, retourne du JSON
- Couvre ~4000 entreprises (Spotify, Figma, etc.)
- Même principe que Greenhouse : slugs + filtrage local

## Données extraites par offre
| Champ | WTTJ | Greenhouse | Lever |
|-------|------|------------|-------|
| Titre | `name` | `title` | `text` |
| Entreprise | `organization.name` | `company_name` | slug |
| Lieu | `offices[].city` | `location.name` | `categories.location` |
| Lien | construit | `absolute_url` | `hostedUrl` |
| Date | `published_at` | `first_published` | `createdAt` (ms) |
| Contrat | `contract_type` | metadata `Time Type` | `categories.commitment` |
| Remote | `remote` | — | `workplaceType` |
| Salaire | `salary_min/max` | — | — |
| Source | "WTTJ" | "Greenhouse" | "Lever" |

## Phases de développement
1. **Scraper WTTJ** - requêtes Algolia, filtres, pagination ✅
2. **Stockage & déduplication** - SQLite, détection nouvelles offres ✅
3. **Interface web** - dashboard Flask, formulaire recherche ✅
4. **Scrapers ATS** - Greenhouse + Lever ✅
5. **Notifications email** - alertes nouvelles offres

## Data layer (data/storage.py)
- `JobStorage` : stockage **SQLite** avec déduplication par URL
- `save_one(job_data)` : sauvegarde une offre (avec champ `source`)
- `delete_one(url)` : supprime une offre
- `all(order_by)` : retourne tous les jobs triés (par défaut : `published_at DESC`)
- `count()` / `clear()` : comptage et suppression
- SQLite avec `check_same_thread=False` pour compatibilité Flask multi-thread
- Migration auto : ajoute la colonne `source` si elle n'existe pas

## Interface web
- **`/`** : recherche multi-sources avec checkboxes (WTTJ, Greenhouse, Lever)
  - Champ slugs entreprises pour Greenhouse/Lever (tags, affiché dynamiquement)
  - Filtres : mots-clés, localisation, entreprise (WTTJ), contrat, remote, salaire
  - Colonne "Source" avec badges colorés dans les résultats
  - Bouton sauvegarder individuel par offre
- **`/saved`** : tableau des offres sauvegardées avec source, supprimer individuel + tout supprimer
- **`/save`** (POST AJAX) : sauvegarde une offre
- **`/delete`** (POST) : supprime une offre
- **`/clear`** (POST) : supprime toutes les offres

## Stack technique
- Python 3.11+
- `requests` pour toutes les API (Algolia, Greenhouse, Lever)
- `Flask` pour l'interface web
- `SQLite` pour le stockage (inclus dans Python, zéro config)

## Déploiement Azure App Service
- **URL** : https://job-scraper-fr.azurewebsites.net
- Tier : F1 (gratuit) | Région : swedencentral
- Resource group : `job-scraper-rg` | Plan : `job-scraper-plan`
- Runtime : Python 3.12 + gunicorn
- SQLite stocké dans `/home/jobs.db` (persistant sur Azure)
- Redéployer : `az webapp up --name job-scraper-fr` depuis la racine du projet

## Commandes
- `python app.py` - lancer le serveur web local sur http://127.0.0.1:5000
- `az webapp up --name job-scraper-fr` - déployer sur Azure

## Notes
- Respecter un délai entre les requêtes (rate limiting)
- Le robots.txt de WTTJ bloque les pages de recherche, mais l'API Algolia est publique
- Les API Greenhouse et Lever sont publiques et sans authentification
- Le champ "Entreprise" dans le formulaire ne s'applique qu'à WTTJ (facet filter)
- Pour Greenhouse/Lever, les slugs sont les identifiants dans l'URL carrière de l'entreprise
