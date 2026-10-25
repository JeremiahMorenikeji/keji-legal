"""The bare address answers, and production does not publish the API docs."""
import importlib

from fastapi.testclient import TestClient


def _fresh_app(monkeypatch, env):
    monkeypatch.setenv("KEJI_ENV", env)
    import api.main
    return importlib.reload(api.main).app


def test_root_answers_in_development(monkeypatch):
    app = _fresh_app(monkeypatch, "development")
    c = TestClient(app)
    assert c.get("/").json()["status"] == "running"
    assert c.get("/docs").status_code == 200


def test_production_hides_the_docs_but_keeps_root_and_health(monkeypatch):
    app = _fresh_app(monkeypatch, "production")
    c = TestClient(app)          # (no "with": startup checks are tested elsewhere)
    assert c.get("/").status_code == 200 and c.get("/health").status_code == 200
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404
    _fresh_app(monkeypatch, "development")   # leave the module as other tests expect it
