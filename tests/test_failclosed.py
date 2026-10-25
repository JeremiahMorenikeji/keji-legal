"""Fail closed: a public Railway server can never run open because KEJI_ENV was forgotten or mistyped."""
import pytest
from fastapi.testclient import TestClient

from api import auth
from api.main import app


@pytest.fixture(autouse=True)
def no_railway(monkeypatch):
    for v in (*auth._RAILWAY_VARS, "KEJI_ALLOW_INSECURE"):
        monkeypatch.delenv(v, raising=False)


@pytest.mark.parametrize("value", ["production", " Production ", '"production"', "'prod'", "PRODUCTION"])
def test_keji_env_is_read_tolerantly(monkeypatch, value):
    monkeypatch.setenv("KEJI_ENV", value)
    assert auth.is_production()


def test_local_default_is_development(monkeypatch):
    monkeypatch.delenv("KEJI_ENV", raising=False)
    assert not auth.is_production() and auth.env_name() == "development"


@pytest.mark.parametrize("keji_env", [None, "", "development", "Development", "dev", "garbage"])
def test_on_railway_it_is_production_whatever_keji_env_says(monkeypatch, keji_env):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p-123")
    if keji_env is None:
        monkeypatch.delenv("KEJI_ENV", raising=False)
    else:
        monkeypatch.setenv("KEJI_ENV", keji_env)
    assert auth.is_production()


def test_a_deliberate_staging_server_can_opt_out(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p-123")
    monkeypatch.setenv("KEJI_ENV", "development")
    monkeypatch.setenv("KEJI_ALLOW_INSECURE", "true")
    assert not auth.is_production()


def test_forgotten_keji_env_on_railway_still_demands_the_token(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p-123")
    monkeypatch.delenv("KEJI_ENV", raising=False)
    monkeypatch.setenv("KEJI_API_SECRET", "a" * 40)
    monkeypatch.setenv("KEJI_REVIEWER_SECRET", "b" * 40)
    c, body = TestClient(app), {"text": "GDPR breach"}
    assert c.post("/jurisdiction/classify", json=body).status_code == 401
    assert c.post("/jurisdiction/classify", json=body, headers={"Authorization": "Bearer " + "a" * 40}).status_code == 200


def test_health_reports_the_mode(monkeypatch):
    c = TestClient(app)
    assert c.get("/health").json()["mode"] == "development"
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p-123")
    assert c.get("/health").json()["mode"] == "production"


def test_railway_without_secrets_refuses_to_start(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p-123")
    monkeypatch.delenv("KEJI_ENV", raising=False)
    for v in ("KEJI_API_SECRET", "KEJI_REVIEWER_SECRET"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        with TestClient(app):
            pass
