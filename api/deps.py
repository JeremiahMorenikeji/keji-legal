"""FastAPI dependencies (override these in tests with app.dependency_overrides)."""
from functools import lru_cache

from api.agents.compliance_agent import ComplianceAgent
from api.rag.retriever import get_supabase


def get_db():
    return get_supabase()


@lru_cache(maxsize=1)
def _agent() -> ComplianceAgent:
    return ComplianceAgent()


def get_agent() -> ComplianceAgent:
    return _agent()
