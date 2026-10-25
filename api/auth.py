"""Auth: Bearer API token for every call, plus a separate reviewer key for human approval."""
import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException

DEFAULT_SECRETS = {"", "change-me-in-production", "generate_a_long_random_string_here"}


# Railway sets these on every deployment (see docs.railway.com/variables/reference)
_RAILWAY_VARS = ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_SERVICE_ID", "RAILWAY_PUBLIC_DOMAIN")


def _clean(name: str) -> str:
    """Environment variable, lower-cased, with stray spaces and quotes ignored."""
    return os.getenv(name, "").strip().strip("\"'").strip().lower()


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


def check_production_config() -> None:
    """Refuse to boot in production with missing / weak secrets."""
    if not is_production():
        return
    problems = []
    for var in ("KEJI_API_SECRET", "KEJI_REVIEWER_SECRET"):
        val = os.getenv(var, "")
        if val in DEFAULT_SECRETS or len(val) < 24:
            problems.append(f"{var} must be set to a random string of at least 24 characters")
    if os.getenv("KEJI_API_SECRET") and os.getenv("KEJI_API_SECRET") == os.getenv("KEJI_REVIEWER_SECRET"):
        problems.append("KEJI_API_SECRET and KEJI_REVIEWER_SECRET must be different")
    for var in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
        if not os.getenv(var):
            problems.append(f"{var} is not set")
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def verify_token(authorization: Optional[str] = Header(default=None)) -> bool:
    """Bearer token check. Skipped ONLY when KEJI_ENV=development."""
    if not is_production():
        return True
    secret = os.getenv("KEJI_API_SECRET", "")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    if not _same(authorization[7:].strip(), secret):
        raise HTTPException(401, "Invalid API token")
    return True


def verify_reviewer(x_reviewer_key: Optional[str] = Header(default=None)) -> bool:
    """Second key, held only by people allowed to approve/reject outputs."""
    secret = os.getenv("KEJI_REVIEWER_SECRET", "")
    if not secret:
        if is_production():
            raise HTTPException(503, "Reviewer key is not configured")
        return True  # development convenience
    if not x_reviewer_key or not _same(x_reviewer_key, secret):
        raise HTTPException(403, "Invalid reviewer key")
    return True
