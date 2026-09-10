# Test and Issue Report

## Current state

The application is a Python 3.11+ Flask service backed by SQLite. It has:

- Web routes for searching, saving, listing, deleting, and clearing jobs.
- WTTJ/Algolia, Greenhouse, and Lever scraper integrations.
- HTML templates and browser-side JavaScript for tag inputs and saving labels.
- An Azure App Service startup script using Gunicorn.

There is currently no `tests/` directory, test dependency set, Dockerfile, health endpoint, or GitHub Actions workflow. The test suite should never call a live job-board API in pull requests; all external responses must be deterministic fixtures or mocked HTTP responses.

## Required test coverage

### 1. Storage unit tests

Create `tests/test_storage.py` using a temporary SQLite database for every test or test class.

| Area | Required cases |
|---|---|
| Schema creation | A new database creates `jobs`, `labels`, and `job_label`; initialization is idempotent; the `source` migration works for a database created by an older version. |
| Job persistence | Save a complete job with each supported source (`WTTJ`, `Greenhouse`, and `Lever`), preserve nullable salary, reject a missing or unsupported source, return the correct boolean, and preserve Unicode and empty optional fields. |
| Deduplication | Saving the same URL twice does not create a second job; verify the defined behavior when a duplicate save also supplies a new label. |
| Labels | Trim labels, ignore empty labels, deduplicate job-label associations, reuse an existing label, return labels for one job, and return all labels in case-insensitive alphabetical order. |
| Queries | `is_saved`, `saved_urls`, `count`, and `all` return correct values; ordering is deterministic and only supported order fields are accepted. |
| Deletion | Deleting an existing and a missing URL returns the correct result; associated join rows and any intentionally retained label records follow the documented retention policy. |
| Clearing | `clear()` removes all jobs and leaves the database in the expected label/join state. |
| Failure handling | Malformed job dictionaries and SQLite failures produce explicit errors rather than partially committed data. |
| Lifecycle | A close/dispose operation releases the connection so temporary databases can be cleaned up on every supported platform. |

The persistence test must not silently assign `WTTJ` when `source` is absent. Every saved job must carry an explicit supported source. After saving a valid job, the test should read it back and verify that the exact source is retained; route/template tests should also verify that the corresponding source label is displayed for search results and saved jobs. Missing or unsupported sources should produce a clear validation error and no database row.

### 2. WTTJ scraper unit and contract tests

Create `tests/test_wttj.py` with mocked `requests.Session` calls.

| Area | Required cases |
|---|---|
| Model | `Job.to_dict()` contains every field, including `source` and `salary`. |
| Facets | `_build_facet_filters()` handles no filters, one string, multiple contract types, remote, company, location, and the expected Algolia OR nesting. |
| Request construction | `search()` sends the expected URL, headers, JSON payload, page, and hits-per-page values. |
| Response parsing | Parse normal hits, missing organization/offices, missing slugs, missing optional fields, and multiple offices without crashing. |
| Salary formatting | Cover min/max, min-only, max-only, no salary, zero values, each supported period, unknown periods, and currencies. |
| Pagination | Stop at `nbPages`, respect `max_pages`, sleep only between pages, and return all parsed jobs. |
| Multi-keyword search | Empty and single-keyword inputs delegate correctly; multiple keywords use the multi-query endpoint, merge results in stable order, deduplicate by URL, stop when a page has no hits, and respect the page limit. |
| HTTP failures | Timeouts, non-2xx responses, invalid JSON, and missing response keys have an explicit and tested policy. |
| Rate limiting | The configured delay is honored without making tests slow; patch the clock or sleep function. |

### 3. Greenhouse scraper unit and contract tests

Create `tests/test_greenhouse.py` with fixture payloads based on the public response shape.

- Build the correct company URL and pass the configured timeout.
- Parse title, company, location, URL, publication date, source, and contract type from metadata.
- Fall back to title-based contract inference when `Time Type` metadata is absent.
- Cover every inference category and the no-match case.
- Handle missing or empty locations, metadata, timestamps, and URLs.
- Filter locations case-insensitively and filter keywords as OR matches on title or company.
- Verify whole-word matching, punctuation, Unicode, and multiple keywords.
- Search multiple slugs while preserving result order.
- Verify the documented behavior when one company returns an HTTP error, timeout, malformed JSON, or malformed job record.

### 4. Lever scraper unit and contract tests

Create `tests/test_lever.py`.

- Build the correct company URL and pass the configured timeout.
- Parse title, slug-derived/company name, location, hosted URL, timestamp, commitment, workplace type, source, and empty salary.
- Convert millisecond timestamps correctly, including zero/missing/invalid values.
- Map `remote` and `hybrid` workplace types and leave other types empty according to the product contract.
- Filter locations and keywords case-insensitively with OR semantics.
- Search multiple slugs and isolate a failing company from successful companies as intended.
- Cover HTTP errors, timeouts, malformed JSON, and malformed records.

### 5. Application helper and route tests

Create `tests/test_app.py` with a Flask test client, a temporary database, and injected/mocked scraper dependencies. Tests must not use the module-level production database.

#### Helpers and search orchestration

- `_filter_by_salary()` accepts every supported range, keeps or excludes exact boundaries according to a documented convention, ignores malformed salary strings, handles missing salaries, and defines how monthly/daily salaries are treated.
- GET `/` renders the form with default sources and option lists.
- POST `/` rejects a completely empty search with a flash message and does not call external scrapers.
- POST `/` parses comma-separated keywords, locations, and slugs, trims whitespace, lowercases slugs, and preserves form values after validation errors.
- WTTJ searches once per location, deduplicates URLs, and handles no location.
- Greenhouse and Lever require company slugs, filter locations locally, and merge results without duplicate URLs.
- Contract, remote, and salary filters apply consistently across all sources.
- Existing saved URLs are marked in search results.
- Unknown source values and invalid form values are rejected or normalized according to an explicit validation policy.
- External scraper failures result in a controlled user-facing response rather than an accidental 500 page.

#### Routes and persistence

- POST `/save` rejects missing JSON, missing URL, and incomplete job records with a 4xx response; valid records are saved; duplicates return the documented boolean; labels are trimmed and associated correctly.
- GET `/labels` returns JSON in sorted order.
- POST `/delete` deletes a valid URL, handles a missing URL explicitly, redirects to `/saved`, and flashes the correct message.
- GET `/saved` renders an empty state and a populated table, including labels and count.
- POST `/clear` clears jobs, redirects to `/saved`, and flashes the correct message.
- Verify method restrictions for every mutating route and verify CSRF behavior once protection is added.
- Verify database path and secret configuration are read from environment/configuration rather than test-host globals.

### 6. Template and browser tests

Add a small browser suite, preferably Playwright running in the test container, for behavior that Flask route tests cannot cover:

- Source checkboxes show and hide the ATS slug section.
- Enter, comma, Backspace, duplicate, removal, and form-submit behavior work for keyword, location, and slug tags.
- Pending input is included in a submitted search.
- Search results render escaped job data and the correct saved state.
- The save modal loads existing labels, can select/create a label, and has distinct cancel and save behavior.
- A successful save disables and updates only the selected button.
- A failed `/labels` or `/save` request shows an error state and does not falsely mark a job as saved.
- Saved-page delete and clear flows work, including the confirmation dialog.
- Basic keyboard navigation, focus visibility, table readability, and responsive layout work at desktop and mobile widths.

### 7. Integration, container, and smoke tests

- Run the complete backend suite against the same Python versions supported by the application.
- Build the production Docker image without network access to external job APIs.
- Start Gunicorn in the container with an isolated writable database path.
- Verify the application responds successfully to `/` and, after it is added, `/health`.
- Verify the container stops cleanly, runs as a non-root user, and does not require a source-tree write.
- Verify a container restart preserves data only when the configured persistent volume is mounted.
- Exercise one mocked search request through the running service.
- Confirm configuration failures, such as a missing production secret, fail clearly at startup or use a documented safe default.

### 8. Quality and security checks

Run these in CI inside Docker:

- `pytest` with coverage for backend and route behavior.
- Ruff (or the repository-standard Python linter/formatter) for Python code.
- A type check for the annotated scraper and storage code once configuration boundaries are typed.
- `pip-audit` and a container image vulnerability scan.
- Bandit or an equivalent static security scan.
- A dependency/license check if required by the organization.

Recommended initial coverage gates are at least 85% overall and at least 90% for `data/`, `scraper/`, and application orchestration. Coverage should measure behavior, not encourage meaningless tests.

## Issues that should be addressed

| Priority | Issue | Impact | Recommended action |
|---|---|---|---|
| P0 | Algolia application ID/API key are hard-coded in `scraper/wttj.py`. | Credentials cannot be rotated safely and configuration differs between environments. | Move all API configuration to environment-backed settings, rotate the exposed key if it is not intentionally public, and keep secrets out of logs and test fixtures. |
| P0 | Mutating routes have no CSRF protection and the deployed app has a predictable fallback secret key. | A public deployment could be forced to save/delete/clear data, and sessions can be forged. | Use a strong required production secret, add CSRF protection for form and JSON mutations, and add secure cookie/security-header settings. |
| P1 | WTTJ requests do not pass a timeout, and route-level scraper failures are not consistently handled. | A provider outage can hang a worker or produce an unhelpful 500 response. | Add connect/read timeouts, bounded retries where appropriate, structured logging, and a consistent user-facing error policy. |
| P1 | Global scraper and storage instances are created at import time. | Tests share state, configuration is difficult to inject, and imports have side effects (`truststore.inject_into_ssl()`). | Introduce an application factory and dependency/configuration injection; use a test database and explicit lifecycle management. |
| P1 | SQLite foreign keys are not enabled and job deletion does not clean `job_label` rows. | Orphaned associations accumulate and referential integrity is not enforced. | Enable `PRAGMA foreign_keys=ON`, add foreign-key actions/migrations, define label retention, and test delete/clear behavior. |
| P1 | `JobStorage.all()` interpolates `order_by` directly into SQL. | Future callers could turn a sorting parameter into SQL injection. | Replace it with a whitelist of allowed order expressions and test rejected values. |
| P1 | `/save` indexes required fields without validating the JSON shape. | A malformed or hostile request can cause a 500 response. | Validate a schema and return a clear 400/422 response; validate URL and field lengths/content. |
| P1 | Dependencies use open lower bounds and there is no separate development dependency set. | Builds can change unexpectedly and contributors lack a reproducible test environment. | Add a lock or constraints strategy, `requirements-dev.txt`/`pyproject.toml`, and update dependencies through automation. |
| P1 | There is no health endpoint or container definition. | CI and Azure cannot reliably distinguish a running process from a healthy application. | Add a dependency-light `/health` endpoint, a Dockerfile health check, and a container smoke test. |
| P2 | `BaseScraper` is unused and its interface does not match the concrete scrapers. | A common abstraction cannot safely be used for substitution or testing. | Either remove it or define a shared protocol/interface and make all scrapers conform to it. |
| P2 | Salary parsing assumes a simple annual numeric string and has ambiguous inclusive range boundaries. | Valid salaries may be filtered incorrectly, especially with zero values, decimals, or non-annual periods. | Normalize salary data into structured values, define boundary semantics, and test conversion/filtering. |
| P2 | Browser fetch failures are swallowed and save buttons are marked saved without checking the HTTP status. | Users receive false success and cannot recover from network/API failures. | Handle non-2xx responses, show an accessible error, and update UI state only after a confirmed success. |
| P2 | The modal's “Annuler” action currently saves the job without a label. | The visible action name conflicts with its behavior. | Decide whether cancel should cancel the save or save without a label, then align text, behavior, and tests. |
| P2 | `debug=True` is enabled when running `app.py`, and environment/input validation is minimal. | A careless production launch can expose debug tooling or accept unsupported source/filter values. | Disable debug by default, validate allowed values, and fail clearly for unsafe production configuration. |
| P2 | README structure and deployment instructions do not describe all current scrapers or the future Docker workflow. | Operators and contributors can follow stale instructions. | Update README after implementation with local, Docker, CI, and Azure deployment instructions. |

## Test completion criteria

The implementation is ready when all required backend, route, container, and security checks pass in Docker; no test performs an uncontrolled external request; the coverage gates are met; and every P0/P1 issue is either fixed or explicitly accepted with an owner and follow-up issue.
