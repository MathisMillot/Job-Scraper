# Job Scraper

Moteur de recherche d'offres d'emploi avec interface web. Avec une architecture extensible pour ajouter d'autres sites.

## Fonctionnalités

- **Recherche multi-critères** : mots-clés (mode OR), localisation, entreprise, type de contrat, remote, salaire
- **Sauvegarde individuelle** : bouton par offre pour sauvegarder/supprimer
- **Déduplication** : les offres déjà sauvegardées sont signalées dans les résultats
- **Stockage SQLite** : persistant, sans configuration externe
- **Déployable sur Azure App Service** (tier gratuit F1)

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.11+, Flask |
| Scraping | API Algolia (via `requests`) |
| Base de données | SQLite |
| Déploiement | Azure App Service, Gunicorn |

## Installation

```bash
# Cloner le repo
git clone <url-du-repo>
cd job-scraper

# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur local
python app.py
```

Le site est accessible sur https://job-scraper-fr.azurewebsites.net/

## Utilisation

### Page de recherche (`/`)

Remplir au moins un champ parmi :
- **Mots-clés** : saisir un mot puis Entrée (plusieurs mots = recherche OR)
- **Localisation** : ville (ex: Paris, Lyon)
- **Entreprise** : nom exact ou approché
- **Type de contrat** : CDI, stage, alternance, freelance...
- **Remote** : non, ponctuel, partiel, total
- **Salaire** : tranche salariale

### Page des offres sauvegardées (`/saved`)

Affiche toutes les offres sauvegardées triées par date. Chaque offre peut être supprimée individuellement ou en bloc.

## Déploiement Azure

```bash
# Prérequis : Azure CLI installé et connecté
az login

# Déployer
az webapp up --name job-scraper-fr --resource-group job-scraper-rg --runtime "PYTHON:3.12" --sku F1 --location swedencentral
```

## Structure du projet

```
├── app.py                 # Point d'entrée Flask (local + Azure)
├── startup.sh             # Démarrage Gunicorn pour Azure
├── requirements.txt
├── scraper/
│   ├── __init__.py
│   └── wttj.py            # Client Algolia WTTJ
├── data/
│   ├── __init__.py
│   └── storage.py          # Stockage SQLite
└── web/
    ├── templates/
    │   ├── base.html
    │   ├── index.html       # Page de recherche
    │   └── saved.html       # Offres sauvegardées
    └── static/
        └── style.css
```

## Roadmap

- [x] Scraper WTTJ (Algolia)
- [x] Stockage SQLite avec déduplication
- [x] Interface web Flask
- [x] Déploiement Azure App Service
- [ ] Notifications email pour nouvelles offres
- [ ] Support d'autres sites d'emploi
