"""
Hybrid retrieval: pgvector (dense) + Postgres full-text (lexical), merged with
Reciprocal Rank Fusion (RRF). Every query is pre-filtered by jurisdiction.
"""
import logging
import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import create_client

from api.rag import embedder

load_dotenv()
log = logging.getLogger("keji.retriever")

VALID_JURISDICTIONS = ("US", "CA", "UK", "EU")
RRF_K = 60


def top_k() -> int:
    return int(os.getenv("RAG_TOP_K", "5"))


@lru_cache(maxsize=1)
def get_supabase():
    """One shared server-side client (service-role key — never expose to the browser)."""
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY are not set.")
    return create_client(url, key)


def _dense(query: str, jurisdiction: str, k: int) -> list[dict]:
    vec = embedder.embed_query(query).tolist()
    r = get_supabase().rpc(
        "match_statute_chunks",
        {"query_embedding": vec, "jurisdiction_filter": jurisdiction, "match_count": k * 2},
    ).execute()
    return r.data or []


def _lexical(query: str, jurisdiction: str, k: int) -> list[dict]:
    r = get_supabase().rpc(
        "lexical_search_chunks",
        {"query_text": query, "jurisdiction_filter": jurisdiction, "match_count": k * 2},
    ).execute()
    return r.data or []


def rrf_merge(dense: list[dict], lexical: list[dict], limit: int) -> list[dict]:
    """
    Reciprocal Rank Fusion: score(doc) = Σ 1 / (RRF_K + rank).
    The fused rank (1 = best) is attached as `rrf_rank`; there is no fake
    'relevance score' for downstream code to misread.
    """
    scores: dict[str, dict] = {}
    for rank, doc in enumerate(dense):
        e = scores.setdefault(doc["id"], {"doc": dict(doc), "rrf": 0.0, "dense_rank": None, "lex_rank": None})
        e["rrf"] += 1.0 / (RRF_K + rank + 1)
        e["dense_rank"] = rank + 1
    for rank, doc in enumerate(lexical):
        e = scores.setdefault(doc["id"], {"doc": dict(doc), "rrf": 0.0, "dense_rank": None, "lex_rank": None})
        e["rrf"] += 1.0 / (RRF_K + rank + 1)
        e["lex_rank"] = rank + 1

    fused = sorted(scores.values(), key=lambda x: x["rrf"], reverse=True)
    out = []
    for i, item in enumerate(fused[:limit]):
        doc = item["doc"]
        doc["rrf_rank"] = i + 1
        doc["dense_rank"] = item["dense_rank"]
        doc["lex_rank"] = item["lex_rank"]
        out.append(doc)
    return out


def retrieve(query: str, jurisdiction: str) -> list[dict]:
    """Main entry point used by the agents."""
    if jurisdiction not in VALID_JURISDICTIONS:
        raise ValueError(f"jurisdiction must be one of {VALID_JURISDICTIONS}, got {jurisdiction!r}")
    k = top_k()

    dense, lex = [], []
    errors = []
    try:
        dense = _dense(query, jurisdiction, k)
    except Exception as e:  # one failing leg should not take the whole search down
        errors.append(("dense", e))
        log.warning("dense retrieval failed: %s", e)
    try:
        lex = _lexical(query, jurisdiction, k)
    except Exception as e:
        errors.append(("lexical", e))
        log.warning("lexical retrieval failed: %s", e)

    if len(errors) == 2:  # both legs down = real outage, surface it
        raise RuntimeError(f"Retrieval failed: {errors[0][1]} / {errors[1][1]}")
    return rrf_merge(dense, lex, k)
