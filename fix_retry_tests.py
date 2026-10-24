# fix_retry_tests.py - (1) retry on Supabase 5xx errors, (2) make tests ignore your real .env. Safe to run twice.
from pathlib import Path
import re
import sys

if not Path("corpus/common.py").exists() or not Path("tests/conftest.py").exists():
    sys.exit("Run this from inside the keji-legal folder.")

HELPER = '''def _is_transient(e):
    """Network drops AND temporary server errors (HTTP 500-599, e.g. Cloudflare 520) are worth retrying."""
    if isinstance(e, (httpx.TransportError, OSError)):
        return True
    code = getattr(e, "code", None)
    if code is None and e.args and isinstance(e.args[0], dict):
        code = e.args[0].get("code")
    try:
        return 500 <= int(str(code)) <= 599
    except (TypeError, ValueError):
        return False


'''
EXCEPT_OLD = "        except (httpx.TransportError, OSError) as e:\n            last = e\n"
EXCEPT_NEW = "        except Exception as e:\n            if not _is_transient(e):\n                raise\n            last = e\n"


def patch_common():
    p = Path("corpus/common.py")
    s = p.read_text(encoding="utf-8")
    orig = s
    sig = re.search(r"def with_retry\([^)]*\):", s)
    if not sig:
        print("  !! corpus/common.py has no with_retry function. Run fix_keji.py first, or tell me.")
        return False
    if "def _is_transient" not in s:
        s = s.replace(sig.group(0), HELPER + "def with_retry(fn, attempts=6, base_delay=5.0):", 1)
    if "if not _is_transient(e)" not in s:
        if EXCEPT_OLD not in s:
            print("  !! could not patch corpus/common.py (the except clause differs). Nothing was changed. Tell me.")
            return False
        s = s.replace(EXCEPT_OLD, EXCEPT_NEW, 1)
    if "def _is_transient" not in s or "if not _is_transient(e)" not in s:
        print("  !! patch incomplete - nothing was changed. Tell me.")
        return False
    if s == orig:
        print("  already up to date: corpus/common.py")
        return True
    Path("corpus/common.py.bak4").write_text(orig, encoding="utf-8")
    p.write_text(s, encoding="utf-8")
    print("  patched: corpus/common.py (retries 5xx server errors too)")
    return True


def patch_conftest():
    p = Path("tests/conftest.py")
    s = p.read_text(encoding="utf-8")
    if "def clean_env" in s:
        print("  already up to date: tests/conftest.py")
        return
    old = ('# Safe defaults so imports never depend on a developer\'s real .env\n'
           'os.environ.setdefault("KEJI_ENV", "development")\n'
           'os.environ.setdefault("RAG_TOP_K", "5")\n')
    new = '''# Offline tests must NEVER depend on a developer's real .env. (For example, a KEJI_REVIEWER_SECRET in
# .env makes the review endpoints demand that key, which would turn the tests' calls into 403s.)
import dotenv  # noqa: E402

if os.getenv("KEJI_LIVE") != "1":
    dotenv.load_dotenv = lambda *a, **k: False  # modules imported later get this harmless no-op
os.environ["KEJI_ENV"] = "development"
os.environ.setdefault("RAG_TOP_K", "5")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Start every test with no KEJI secrets, whatever is in .env or your shell."""
    for var in ("KEJI_API_SECRET", "KEJI_REVIEWER_SECRET", "KEJI_API_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KEJI_ENV", "development")
'''
    if old not in s:
        print("  !! could not patch tests/conftest.py (its text differs). Nothing was changed. Tell me.")
        return
    Path("tests/conftest.py.bak4").write_text(s, encoding="utf-8")
    p.write_text(s.replace(old, new, 1), encoding="utf-8")
    print("  patched: tests/conftest.py (tests ignore your real .env)")


TESTS = '''"""Retry behaviour: temporary server errors are retried, real errors are not."""
import pytest
from postgrest.exceptions import APIError

from corpus import common


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(common.time, "sleep", lambda s: None)


def _flaky(error, fail_times):
    state = {"n": 0}

    def fn():
        state["n"] += 1
        if state["n"] <= fail_times:
            raise error
        return "ok"
    return fn, state


def test_supabase_520_is_retried_then_succeeds():
    err = APIError({"message": "JSON could not be generated", "code": 520, "details": "<html>"})
    fn, state = _flaky(err, fail_times=2)
    assert common.with_retry(fn) == "ok" and state["n"] == 3


@pytest.mark.parametrize("code", [500, 502, 503, 504, 522, "520"])
def test_other_5xx_codes_are_retried(code):
    fn, state = _flaky(APIError({"message": "x", "code": code}), fail_times=1)
    assert common.with_retry(fn) == "ok" and state["n"] == 2


@pytest.mark.parametrize("code", ["PGRST205", "23505", "42501", 400, 404, 409])
def test_real_errors_are_not_retried(code):
    fn, state = _flaky(APIError({"message": "x", "code": code}), fail_times=99)
    with pytest.raises(APIError):
        common.with_retry(fn)
    assert state["n"] == 1


def test_persistent_5xx_gives_a_clear_message():
    fn, state = _flaky(APIError({"message": "x", "code": 520}), fail_times=99)
    with pytest.raises(RuntimeError, match="re-run the same command"):
        common.with_retry(fn)
    assert state["n"] == 6
'''


def put_tests():
    tp = Path("tests/test_retry.py")
    if tp.exists() and tp.read_text(encoding="utf-8") == TESTS:
        print("  already up to date: tests/test_retry.py")
        return
    tp.write_text(TESTS, encoding="utf-8")
    print("  wrote: tests/test_retry.py")


common_ok = patch_common()
patch_conftest()
if common_ok:
    put_tests()
else:
    print("  (skipped tests/test_retry.py because corpus/common.py was not patched)")
print("\nDone.")
