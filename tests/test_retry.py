"""Retry behaviour: temporary server errors are retried, real errors are not."""
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
