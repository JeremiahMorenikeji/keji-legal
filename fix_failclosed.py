# fix_failclosed.py - on Railway the API can never run open, even if KEJI_ENV is forgotten or mistyped.
# Also: the startup log and /health now say which mode is running. Safe to run twice.
from pathlib import Path
import sys

for must in ("api/auth.py", "api/main.py"):
    if not Path(must).exists():
        sys.exit("Run this from inside the keji-legal folder.")

changes, problems, done, skipped = {}, [], [], []


def cur(rel):
    return changes[rel] if rel in changes else Path(rel).read_text(encoding="utf-8")


def edit(rel, pairs, marker, optional=False):
    if not Path(rel).exists():
        (skipped if optional else problems).append(f"{rel}: file not found")
        return
    s = cur(rel)
    if marker in s:
        done.append(f"{rel} ({marker})")
        return
    for old, new in pairs:
        if old not in s:
            (skipped if optional else problems).append(f"{rel}: could not find: {old.strip().splitlines()[0][:70]}")
            return
        s = s.replace(old, new, 1)
    changes[rel] = s


edit("api/auth.py", [(
    'def env_name() -> str:\n    return os.getenv("KEJI_ENV", "development").lower()\n\n\n'
    'def is_production() -> bool:\n    return env_name() == "production"\n',
    '''# Railway sets these on every deployment (see docs.railway.com/variables/reference)
_RAILWAY_VARS = ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_SERVICE_ID", "RAILWAY_PUBLIC_DOMAIN")


def _clean(name: str) -> str:
    """Environment variable, lower-cased, with stray spaces and quotes ignored."""
    return os.getenv(name, "").strip().strip("\\"'").strip().lower()


def on_railway() -> bool:
    return any(os.getenv(v) for v in _RAILWAY_VARS)


def is_production() -> bool:
    """
    Production when KEJI_ENV says so - and, failing closed, ALWAYS when running on Railway, so a forgotten or
    mistyped KEJI_ENV can never leave a public server open. (A deliberate staging server can set
    KEJI_ALLOW_INSECURE=true.)
    """
    if _clean("KEJI_ENV") in ("production", "prod"):
        return True
    return on_railway() and _clean("KEJI_ALLOW_INSECURE") not in ("1", "true", "yes")


def env_name() -> str:
    return "production" if is_production() else "development"
''')], "def on_railway")

edit("api/main.py", [
    ('    check_production_config()  # crash early (and loudly) on unsafe production config\n',
     '    print(f"[keji] starting in {\'PRODUCTION\' if is_production() else \'DEVELOPMENT\'} mode", flush=True)\n'
     '    check_production_config()  # crash early (and loudly) on unsafe production config\n'),
    ('    return {"status": "ok", "service": "KEJI Legal API", "version": VERSION}\n',
     '    return {"status": "ok", "service": "KEJI Legal API", "version": VERSION,\n'
     '            "mode": "production" if is_production() else "development"}\n'),
], "[keji] starting in")

edit("tests/conftest.py", [
    ('    for var in ("KEJI_API_SECRET", "KEJI_REVIEWER_SECRET", "KEJI_API_BASE_URL"):\n',
     '    for var in ("KEJI_API_SECRET", "KEJI_REVIEWER_SECRET", "KEJI_API_BASE_URL", "KEJI_ALLOW_INSECURE",\n'
     '                "RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_SERVICE_ID", "RAILWAY_PUBLIC_DOMAIN"):\n'),
], '"KEJI_ALLOW_INSECURE"', optional=True)

if problems:
    print("Nothing was changed, because:")
    for p in problems:
        print("  !!", p)
    print("Send me these lines.")
    sys.exit(1)

for rel, text in changes.items():
    Path(rel + ".bak11").write_text(Path(rel).read_text(encoding="utf-8"), encoding="utf-8")
    Path(rel).write_text(text, encoding="utf-8")
    print(f"  patched: {rel}")
for rel in done:
    print(f"  already up to date: {rel}")
for s in skipped:
    print(f"  (skipped, optional) {s}")

TEST = '''"""Fail closed: a public Railway server can never run open because KEJI_ENV was forgotten or mistyped."""
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
'''
p = Path("tests/test_failclosed.py")
if p.exists() and p.read_text(encoding="utf-8") == TEST:
    print("  already up to date: tests/test_failclosed.py")
else:
    p.write_text(TEST, encoding="utf-8")
    print("  wrote: tests/test_failclosed.py")
print("\nDone. Run: python -m pytest   then push to GitHub so Railway redeploys.")
