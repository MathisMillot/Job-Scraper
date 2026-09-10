import pytest

from config import Settings


def test_development_configuration_has_safe_nonproduction_defaults(tmp_path):
    settings = Settings.from_env(
        {
            "APP_ENV": "development",
            "DB_PATH": str(tmp_path / "jobs.db"),
        }
    )

    assert settings.secret_key
    assert len(settings.secret_key) >= 32
    assert settings.production is False
    assert settings.db_path == tmp_path / "jobs.db"


def test_production_requires_secret_and_wttj_credentials():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings.from_env({"APP_ENV": "production"})

    with pytest.raises(RuntimeError, match="WTTJ_APP_ID"):
        Settings.from_env(
            {
                "APP_ENV": "production",
                "SECRET_KEY": "strong-secret",
            }
        )


def test_boolean_and_timeout_values_are_parsed():
    settings = Settings.from_env(
        {
            "APP_ENV": "testing",
            "SECRET_KEY": "secret",
            "WTTJ_APP_ID": "app",
            "WTTJ_API_KEY": "key",
            "CSRF_ENABLED": "false",
            "COOKIE_SECURE": "true",
            "WTTJ_CONNECT_TIMEOUT": "2",
            "WTTJ_READ_TIMEOUT": "4",
        },
        testing=True,
    )

    assert settings.csrf_enabled is False
    assert settings.cookie_secure is True
    assert settings.wttj_timeout == (2.0, 4.0)


@pytest.mark.parametrize(
    "environment",
    [
        {"CSRF_ENABLED": "maybe"},
        {"WTTJ_DELAY": "0"},
    ],
)
def test_invalid_configuration_values_are_rejected(environment):
    with pytest.raises(ValueError):
        Settings.from_env(
            {
                "APP_ENV": "testing",
                "SECRET_KEY": "secret",
                **environment,
            },
            testing=True,
        )
