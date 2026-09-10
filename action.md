# Docker-based CI/CD

## Objectives

The repository should build, test, scan, and release one reproducible Docker image. Pull requests must prove that the application is testable without live job-board APIs. Production releases must promote the exact image that passed CI instead of rebuilding source code on the deployment host.

The proposed delivery target is Azure App Service for Containers, matching the existing Azure deployment. GitHub Container Registry (GHCR) stores release images.

## Required repository artifacts

Add these files as part of the implementation:

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage Python image with `test` and minimal non-root `runtime` targets. |
| `.dockerignore` | Exclude `.git`, virtual environments, databases, caches, local secrets, and test artifacts. |
| `requirements-dev.txt` or `pyproject.toml` | Reproducible test, lint, type-check, and security tooling. |
| `pytest.ini` or tool configuration | Test discovery, warnings, coverage, and consistent options. |
| `.github/workflows/ci.yml` | Pull request and branch validation. |
| `.github/workflows/security.yml` | Dependency and image security checks. |
| `.github/workflows/release.yml` | Tag/manual build, publish, and deployment. |
| Optional `compose.ci.yml` | Useful if the test suite later needs a database or additional service; not required for the current single-container app. |

## Docker image design

Use a multi-stage build based on a supported slim Python image:

1. A dependency stage installs locked production dependencies.
2. A test stage installs development dependencies, copies application code and tests, and is used only by CI.
3. A runtime stage copies only production dependencies and application files, runs Gunicorn, and uses a dedicated non-root user.

The runtime image must:

- Expose the configured HTTP port, defaulting to `8000`.
- Use `gunicorn --bind=0.0.0.0:8000 --timeout 120 app:app` or the application factory equivalent.
- Receive `SECRET_KEY`, database path, provider configuration, and logging settings through environment variables.
- Store SQLite under a configurable path; Azure must mount persistent storage for that path.
- Include a health check after a `/health` endpoint exists.
- Avoid copying `.env`, `*.db`, credentials, caches, or test-only dependencies.
- Fail clearly when required production configuration is missing.

## Pull request and branch CI

Create `ci.yml` on `pull_request` and pushes to the protected default branch.

### Job: test

Run entirely with Docker:

1. Check out the repository.
2. Set up Docker Buildx and cache layers with GitHub Actions cache.
3. Build `job-scraper:test` from the `test` target.
4. Run the backend tests with coverage in an ephemeral container and publish the coverage artifact.
5. Run linting and type checking in the same test image.
6. Run the application/container smoke test with a temporary database and a health request.

Use a matrix for the supported Python versions, at minimum Python 3.11 and 3.12 if both remain supported. The image tag must include the matrix version so jobs cannot overwrite each other's results.

### Job: image validation

After tests pass:

- Build the production target.
- Confirm the image starts as a non-root user.
- Verify `/` and `/health` respond.
- Record the image digest as a workflow artifact.

The required status checks should be the test matrix and production-image smoke test. Branch protection should require these checks before merging.

## Security workflow

Create `security.yml` for pull requests, pushes to the default branch, and a weekly schedule.

- Run `pip-audit` against the locked dependency set.
- Run Bandit or the selected Python security scanner.
- Scan the built Docker image with Trivy or the organization-approved scanner.
- Fail on defined high/critical vulnerabilities unless an explicit allowlist entry has an owner and expiry.
- Generate a software bill of materials (SBOM) for release candidates.
- Run CodeQL if enabled by the organization.

The workflow must use read-only `GITHUB_TOKEN` permissions unless a job specifically needs package publishing. Never print provider keys, Azure credentials, or environment files.

## Release and deployment workflow

Create `release.yml` with:

- Trigger on version tags such as `v1.2.3`.
- A manual `workflow_dispatch` input for a non-production environment.
- A dependency on successful CI/security jobs.
- Docker metadata tags for the version, commit SHA, and an immutable release identifier.
- Build and push to `ghcr.io/mathismillot/job-scraper`.
- Generate provenance/SBOM and retain the image digest.
- Deploy the exact digest to Azure App Service for Containers.

Use a protected GitHub `production` environment with approval rules. Prefer Azure OIDC federation with these repository/environment secrets or variables:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- Azure resource group and web app name as non-secret variables

Configure the Azure app with:

- The GHCR image digest to run.
- `SECRET_KEY` from Azure-managed secrets.
- The configured persistent SQLite path under `/home`.
- Provider configuration from Azure-managed settings.
- HTTPS-only and health-check settings.

Do not use `latest` as the deployment reference. Keep the previous image digest available for rollback. A failed health check must fail the workflow and leave the previous healthy deployment in place where the Azure deployment strategy allows it.

## Suggested workflow shape

```text
pull request / main push
        |
        v
Docker test image -> pytest + coverage + lint + type checks
        |
        v
production image -> startup + /health smoke test
        |
        +--> security scan

version tag
        |
        v
repeat validated build -> GHCR immutable digest -> Azure staging
        |
        v
protected production approval -> Azure production
```

## Operational requirements

- Add Dependabot or the organization-approved dependency update process for Python packages and GitHub Actions.
- Pin action versions, preferably to approved immutable SHAs where policy requires it.
- Use workflow concurrency so a superseded deployment is cancelled before it reaches production.
- Retain test reports, image digest, SBOM, and security results for each release.
- Add log-level configuration and ensure logs do not contain secrets or full provider payloads.
- Document local commands equivalent to CI: Docker build, Docker test, Docker run, and Docker smoke check.
- Add a post-deployment smoke test and a documented rollback command based on the prior image digest.

## Definition of CI/CD done

CI/CD is complete when a clean checkout can build the test and runtime images, all required checks run inside Docker, pull requests are blocked by failing checks, release tags publish an immutable image to GHCR, Azure runs that same digest with persistent storage and secrets configured outside Git, and rollback can be performed without rebuilding the application.
