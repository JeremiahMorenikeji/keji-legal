# fix_root.py - friendly root page ("/") and no public API docs in production. Safe to run twice.
from pathlib import Path
import sys

p = Path("api/main.py")
if not p.exists():
    sys.exit("Run this from inside the keji-legal folder.")
s = p.read_text(encoding="utf-8")
if "def root()" in s:
    print("  already up to date: api/main.py")
    sys.exit(0)

A_OLD = "    lifespan=lifespan,\n)\n"
A_NEW = ("    lifespan=lifespan,\n"
         "    docs_url=None if is_production() else \"/docs\",     # no public API docs in production\n"
         "    redoc_url=None,\n"
         "    openapi_url=None if is_production() else \"/openapi.json\",\n)\n")
B_OLD = '    return {"status": "ok", "service": "KEJI Legal API", "version": VERSION}\n'
B_NEW = B_OLD + '''

@app.get("/", include_in_schema=False)
def root():
    """So that opening the bare address in a browser shows a sign of life instead of 'Not Found'."""
    return {"service": "KEJI Legal API", "status": "running", "version": VERSION, "health": "/health"}
'''
if A_OLD not in s or B_OLD not in s:
    sys.exit("  !! could not find the expected text in api/main.py - nothing was changed. Tell me.")
Path("api/main.py.bak10").write_text(s, encoding="utf-8")
p.write_text(s.replace(A_OLD, A_NEW, 1).replace(B_OLD, B_NEW, 1), encoding="utf-8")
print("  patched: api/main.py")

T = '''"""The bare address answers, and production does not publish the API docs."""
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
'''
t = Path("tests/test_root.py")
if not t.exists():
    t.write_text(T, encoding="utf-8")
    print("  wrote: tests/test_root.py")
print("\nDone. Push to GitHub so Railway redeploys.")
