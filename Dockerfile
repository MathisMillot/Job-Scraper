# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS production-deps

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt constraints.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt -c constraints.txt

FROM python:${PYTHON_VERSION}-slim-bookworm AS test

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt requirements-dev.txt constraints.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements-dev.txt -c constraints.txt
COPY . .
CMD ["pytest", "-m", "not e2e"]

FROM test AS e2e

RUN playwright install --with-deps chromium
CMD ["pytest", "-m", "e2e"]

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DB_PATH=/home/jobs.db \
    APP_ENV=production

WORKDIR /app
COPY --from=production-deps /usr/local /usr/local
COPY app.py config.py ./
COPY data ./data
COPY scraper ./scraper
COPY web ./web

# Packaging tools are not needed by the runtime image.
RUN site_packages="$(python -c 'import site; print(site.getsitepackages()[0])')" \
    && find "$site_packages" -maxdepth 1 \
        \( -name "pip" -o -name "pip-*.dist-info" \
        -o -name "setuptools" -o -name "setuptools-*.dist-info" \) \
        -exec rm -rf {} + \
    && find /usr/local/bin -maxdepth 1 -type f -name "pip*" -delete \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /home/appuser \
    && chown -R appuser:appuser /app /home

USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/health', timeout=3)"

CMD ["sh", "-c", "gunicorn --bind=0.0.0.0:${PORT} --timeout=120 app:app"]
