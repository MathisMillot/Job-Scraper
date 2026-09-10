# Implementation Plan

## Target outcome

Deliver a secure, predictable, tested, Dockerized Flask application with GitHub Actions that validates every change and deploys immutable images to Azure App Service for Containers.

The implementation order is deliberate: first resolve the issues identified in `report.md` and establish a clean application baseline; only then add automated tests, CI, and deployment automation. Tests must encode the corrected behavior rather than preserve known unsafe or ambiguous behavior.

## Phase 0: Establish the clean-start decisions

Before changing code, convert the open behavior questions from `report.md` into explicit requirements:

1. Every persisted job must have an explicit source. Only `WTTJ`, `Greenhouse`, and `Lever` are valid; a missing or unsupported source is rejected and never defaults to `WTTJ`.
2. Search results and saved-job pages must display the exact source stored with each job.
3. Define salary range boundary semantics and how monthly/daily salaries are normalized.
4. Define whether labels survive job deletion and clearing.
5. Define whether a duplicate save may add a label to an existing job.
6. Define whether the modal’s cancel action cancels the save or saves without a label.
7. Define whether one provider failure returns partial results or fails the complete search.
8. Record supported Python versions, deployment environments, required secrets, database persistence expectations, and the approved dependency update policy.

**Exit criteria:** all behavior decisions are documented, the report issues have owners or implementation tasks, and no later test depends on an undocumented assumption.

## Phase 1: Resolve report issues before writing tests

No automated test implementation begins until this phase is complete. Use manual local smoke checks while making these changes.

### 1.1 Security and configuration

1. Move Algolia/WTTJ configuration out of `scraper/wttj.py` and into environment-backed typed configuration.
2. Rotate any exposed credential where required; do not copy provider keys into tests, images, logs, or documentation.
3. Replace the predictable fallback secret with a required strong production secret while retaining a clearly documented development-only option.
4. Add CSRF protection to form and JSON mutation routes (`/save`, `/delete`, and `/clear`).
5. Configure secure session cookies, HTTPS-only behavior, and appropriate security headers for production.
6. Disable debug mode by default and ensure production startup cannot accidentally enable the Flask debugger.

### 1.2 Runtime architecture and provider reliability

1. Introduce an application factory or equivalent dependency injection for storage, scrapers, configuration, and the Flask test client.
2. Remove import-time runtime side effects where possible; initialize trust-store behavior during application startup/configuration.
3. Add connect/read timeouts to WTTJ requests and define bounded retry behavior only for retryable failures.
4. Normalize error handling across WTTJ, Greenhouse, and Lever so provider failures are logged and surfaced according to the Phase 0 policy.
5. Add a dependency-free `/health` endpoint that reports application readiness without calling external job APIs.
6. Validate search form values, allowed sources, company slugs, filter values, field lengths, and comma-separated input.
7. Validate `/save` JSON before touching storage and return a clear 400/422 response for malformed or incomplete records.

### 1.3 Storage integrity and source correctness

1. Make `source` mandatory in `JobStorage.save_one()` and accept only `WTTJ`, `Greenhouse`, or `Lever`.
2. Remove the implicit `"WTTJ"` fallback. A missing or unsupported source must be rejected with no partially stored row.
3. Preserve the exact valid source through storage, API responses, search results, and saved-job templates.
4. Enable SQLite foreign keys and add the correct delete behavior for `job_label` associations.
5. Decide and implement label retention for job deletion and clearing.
6. Add explicit transaction/error handling and a connection close/dispose method.
7. Replace interpolated `order_by` SQL with a whitelist of supported order expressions.
8. Ensure database parent directories are created/configured safely and production storage uses the persistent Azure path.

### 1.4 Code, data, and frontend consistency

1. Align `BaseScraper` with all concrete scraper signatures, or remove it and use a typed protocol.
2. Define a consistent salary representation and implement the Phase 0 conversion and boundary rules.
3. Handle malformed provider payloads consistently instead of allowing unexpected `None` values to reach templates or filters.
4. Update browser fetch handling so non-2xx responses and network failures show an error and never mark a job as saved falsely.
5. Resolve the label modal’s cancel behavior and align its label, implementation, and intended tests.
6. Add safe link attributes and preserve template escaping for external job data.

### 1.5 Dependency and reproducibility baseline

1. Add a production dependency lock or constraints strategy instead of relying only on open lower bounds.
2. Add `requirements-dev.txt` or `pyproject.toml` for pytest, coverage, HTTP mocking, linting, typing, and security tools.
3. Define the supported Python versions and ensure production and development dependencies install reproducibly.
4. Configure Dependabot or the approved dependency update automation.
5. Update the README so its scraper list, configuration, local startup, and deployment instructions match the corrected application.

### 1.6 Baseline Docker runtime

1. Add a multi-stage `Dockerfile` and `.dockerignore`.
2. Provide a minimal non-root runtime image with configurable port, secret, provider settings, and database path.
3. Run Gunicorn using the corrected application entry point.
4. Add a Docker health check that uses `/health`.
5. Verify the image does not contain source-tree databases, credentials, caches, or development-only packages.
6. Verify `/home` or the configured persistent path is writable for SQLite in the Azure deployment model.

**Clean-start exit criteria:** all P0 and P1 issues in `report.md` are fixed; all P2 correctness/security issues selected in Phase 0 are fixed; source validation and source display are correct; production secrets are externalized; provider calls have timeouts; storage integrity is enforced; dependencies are reproducible; and the baseline container starts as a non-root user.

## Phase 2: Build the test foundation

Only after Phase 1 passes its clean-start criteria:

1. Configure pytest discovery, markers, warnings, coverage, and the initial coverage threshold.
2. Create fixtures for temporary SQLite databases, Flask clients, valid jobs for each source, and representative provider payloads.
3. Create mocked HTTP sessions and deterministic clock/sleep helpers.
4. Add a guard that prevents normal tests from contacting live provider hosts.
5. Add a fast unit-test command and a complete local Docker test command.

**Exit criteria:** pytest runs from a clean checkout in Docker without live network calls and can isolate every test database.

## Phase 3: Implement backend unit tests

1. Test storage schema creation, migrations, required fields, explicit source validation, persistence, deduplication, labels, ordering, cleanup, transactions, and lifecycle.
2. Test WTTJ facets, request payloads, response parsing, salary handling, pagination, multi-keyword deduplication, delays, timeouts, and failures.
3. Test Greenhouse metadata/inference, filtering, malformed records, multiple companies, timeouts, and partial failures.
4. Test Lever timestamps, workplace mapping, filtering, malformed records, multiple companies, timeouts, and partial failures.
5. Test configuration and salary validators independently.

**Exit criteria:** storage and scraper behavior is covered without Flask or external service availability.

## Phase 4: Implement Flask integration tests

1. Test every route and HTTP method with injected storage and fake scrapers.
2. Verify search parsing, source selection, slug validation, location handling, deduplication, contract/remote/salary filters, and saved markers.
3. Verify missing/invalid sources are rejected and valid WTTJ, Greenhouse, and Lever values are displayed correctly in responses and rendered pages.
4. Test `/save` validation, CSRF behavior, duplicate saves, labels, and JSON response shapes.
5. Test `/labels`, `/delete`, `/saved`, and `/clear`, including redirects, flash messages, empty states, and label cleanup.
6. Test provider failure behavior and the `/health` endpoint.
7. Add regression tests for every corrected P0/P1 issue.

**Exit criteria:** the public HTTP contract is deterministic, validated, and protected by tests.

## Phase 5: Add browser-level coverage

1. Extract complex browser JavaScript into a testable static module if needed.
2. Add Playwright tests for tags, source toggles, form submission, source display, the label modal, successful saves, failed saves, and saved-page actions.
3. Verify cancel behavior matches the Phase 0 decision.
4. Add keyboard navigation, focus visibility, responsive layout, and basic accessibility smoke checks.
5. Run the browser suite against a local server with stubbed provider responses.

**Exit criteria:** primary user flows work in a browser and provider/network failures cannot create false success states.

## Phase 6: Validate and harden the container

1. Build both test and production Docker targets.
2. Run the backend and browser suites in the test image.
3. Start the runtime image with an isolated writable database and verify `/` and `/health`.
4. Verify non-root execution, clean shutdown, configured port behavior, and absence of source-tree writes.
5. Verify persistence across restarts only when the expected volume is mounted.
6. Record the image digest and confirm configuration failures are explicit.

**Exit criteria:** the same Docker build is suitable for local development, CI validation, and release promotion.

## Phase 7: Implement GitHub Actions

1. Add `ci.yml` for pull requests and pushes to the protected default branch.
2. Build the Docker test target and run pytest, coverage, lint, type checks, browser tests, and container smoke tests inside Docker.
3. Use a Python 3.11/3.12 matrix if both versions remain supported and cache Docker layers.
4. Add `security.yml` for dependency auditing, Bandit, image scanning, SBOM generation, and any required CodeQL checks.
5. Configure read-only default workflow permissions, pinned action versions, secret masking, and concurrency cancellation.
6. Add required branch-protection checks and publish coverage/security artifacts.

**Exit criteria:** pull requests cannot merge with failing tests, security checks, or image validation.

## Phase 8: Configure release and Azure delivery

1. Add `release.yml` for version tags and approved manual releases.
2. Build the already-validated production target and publish it to GHCR with version, commit, and immutable digest references.
3. Generate provenance and SBOM artifacts.
4. Configure a protected production environment and Azure OIDC authentication.
5. Configure Azure App Service for Containers with the GHCR image digest, external secrets, HTTPS-only mode, health checks, and persistent SQLite storage under `/home`.
6. Deploy to staging or a slot, run post-deployment smoke checks, and require approval before production.
7. Document and verify rollback to the previous image digest.

**Exit criteria:** Azure runs the exact image digest validated by CI, deployment health is verified, and rollback does not require rebuilding.

## Phase 9: Operational documentation and maintenance

1. Document local Python and Docker commands, environment variables, test commands, and provider error behavior.
2. Document SQLite persistence limitations, backups, label retention, deployment, and rollback.
3. Add dependency update ownership and a process for expiring security exceptions.
4. Review coverage, flaky-test history, image vulnerabilities, and deferred issues after the first releases.

**Exit criteria:** a new contributor can run the same checks locally, and an operator can deploy, monitor, and roll back without reading implementation details.

## Suggested delivery order

| Change set | Contents | Depends on |
|---|---|---|
| 1 | Phase 0 decisions and issue ownership | None |
| 2 | P0/P1/P2 application remediation, source validation, dependency baseline, and runtime Docker image | Change set 1 |
| 3 | Test configuration, fixtures, and no-network test harness | Change set 2 |
| 4 | Storage and scraper unit tests | Change set 3 |
| 5 | Flask integration and regression tests | Change set 4 |
| 6 | Browser tests and frontend regression coverage | Change set 5 |
| 7 | Container hardening and full Docker validation | Change set 6 |
| 8 | CI and security workflows | Change set 7 |
| 9 | GHCR/Azure release workflow, deployment, and rollback | Change set 8 |
| 10 | Operational documentation and maintenance automation | Change set 9 |

## Definition of done

- The clean-start remediation gate has passed before test implementation.
- All P0 and P1 issues in `report.md` are fixed; any deferred P2 issue has an explicit owner and rationale.
- Missing job sources are rejected, valid sources are preserved, and the correct source is displayed throughout the application.
- Required backend, route, browser, container, and security tests pass in Docker without uncontrolled network calls.
- Coverage meets the configured threshold.
- The runtime image is minimal, non-root, health-checked, and contains no secrets.
- GitHub Actions enforce the checks on pull requests.
- Releases publish immutable GHCR images and deploy the same digest to Azure.
- SQLite persistence, environment variables, rollback, and local development commands are documented.
