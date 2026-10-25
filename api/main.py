"""KEJI Legal — FastAPI backend (research assistant; never legal advice)."""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api.auth import check_production_config, is_production  # noqa: E402
from api.routers import compliance, contracts, matters  # noqa: E402

VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_production_config()  # crash early (and loudly) on unsafe production config
    yield


app = FastAPI(
    title="KEJI Legal API",
    description="Legal research assistant · US · CA · UK · EU",
    version=VERSION,
    lifespan=lifespan,
    docs_url=None if is_production() else "/docs",     # no public API docs in production
    redoc_url=None,
    openapi_url=None if is_production() else "/openapi.json",
)


def _origins() -> list[str]:
    if not is_production():
        return ["*"]
    base = ["https://keji.legal", "https://www.keji.legal"]
    host = os.getenv("HF_SPACE_HOST", "").strip()
    if host:
        base.append(f"https://{host}")
    base += [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return sorted(set(base))


app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type", "X-Reviewer-Key"],
)

app.include_router(compliance.router)
app.include_router(contracts.router)
app.include_router(matters.router)


@app.get("/health")
def health():
    """Unauthenticated, cheap, never touches the DB or the model (used by Railway's health check)."""
    return {"status": "ok", "service": "KEJI Legal API", "version": VERSION}


@app.get("/", include_in_schema=False)
def root():
    """So that opening the bare address in a browser shows a sign of life instead of 'Not Found'."""
    return {"service": "KEJI Legal API", "status": "running", "version": VERSION, "health": "/health"}
