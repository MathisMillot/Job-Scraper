"""Application configuration loaded from environment variables."""

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

VALID_SOURCES = frozenset({"WTTJ", "Greenhouse", "Lever"})
VALID_SOURCE_KEYS = frozenset({"wttj", "greenhouse", "lever"})


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean configuration value: {value!r}")


def _as_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    parsed = float(value)
    if parsed <= 0:
        raise ValueError("Timeout and delay values must be greater than zero")
    return parsed


@dataclass(frozen=True)
class Settings:
    """Runtime settings shared by the Flask app and its integrations."""

    environment: str
    secret_key: str
    db_path: Path
    wttj_app_id: str
    wttj_api_key: str
    wttj_index_name: str
    wttj_timeout: tuple[float, float]
    wttj_delay: float
    csrf_enabled: bool
    cookie_secure: bool
    truststore_enabled: bool
    testing: bool = False

    @property
    def production(self) -> bool:
        return self.environment in {"production", "prod"}

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        testing: bool = False,
    ) -> "Settings":
        env = os.environ if environ is None else environ
        environment = (
            env.get("APP_ENV")
            or ("production" if env.get("WEBSITE_SITE_NAME") else "development")
        ).strip().lower()
        production = environment in {"production", "prod"}

        secret_key = env.get("SECRET_KEY", "").strip()
        if production and not secret_key:
            raise RuntimeError("SECRET_KEY must be set in production")
        if not secret_key:
            secret_key = secrets.token_urlsafe(32)

        app_id = env.get("WTTJ_APP_ID", "").strip()
        api_key = env.get("WTTJ_API_KEY", "").strip()
        if production and (not app_id or not api_key):
            raise RuntimeError(
                "WTTJ_APP_ID and WTTJ_API_KEY must be set in production"
            )

        db_value = env.get("DB_PATH", "").strip()
        if db_value:
            db_path = Path(db_value)
        elif env.get("WEBSITE_SITE_NAME"):
            db_path = Path("/home/jobs.db")
        else:
            db_path = Path(__file__).parent / "data" / "jobs.db"

        connect_timeout = _as_float(env.get("WTTJ_CONNECT_TIMEOUT"), 10.0)
        read_timeout = _as_float(env.get("WTTJ_READ_TIMEOUT"), 30.0)

        return cls(
            environment=environment,
            secret_key=secret_key,
            db_path=db_path,
            wttj_app_id=app_id,
            wttj_api_key=api_key,
            wttj_index_name=env.get(
                "WTTJ_INDEX_NAME", "wttj_jobs_production_fr"
            ).strip(),
            wttj_timeout=(connect_timeout, read_timeout),
            wttj_delay=_as_float(env.get("WTTJ_DELAY"), 0.5),
            csrf_enabled=_as_bool(env.get("CSRF_ENABLED"), True),
            cookie_secure=_as_bool(env.get("COOKIE_SECURE"), production),
            truststore_enabled=_as_bool(env.get("TRUSTSTORE_ENABLED"), True),
            testing=testing,
        )
