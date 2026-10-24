"""
Local embeddings — BAAI/bge-small-en-v1.5 (384-dim). No API cost.

The heavy sentence-transformers import happens lazily inside `_model()`, so
importing this module (e.g. in unit tests, or the /health check) is instant.
"""
import os
from functools import lru_cache

import numpy as np
from dotenv import load_dotenv

load_dotenv()

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
EMBEDDING_DIM = 384


@lru_cache(maxsize=1)
def _model():
    """Load once per process — never reload a model per request."""
    from sentence_transformers import SentenceTransformer

    name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    print(f"[embedder] loading {name}", flush=True)
    return SentenceTransformer(name)


def embed_query(text: str) -> np.ndarray:
    """Embed a search query (bge works better with an instruction prefix on queries only)."""
    return np.asarray(_model().encode(QUERY_PREFIX + text, normalize_embeddings=True))


def embed_documents(texts: list[str], show_progress: bool = True) -> np.ndarray:
    """Embed corpus text in a batch. No prefix on documents."""
    return np.asarray(
        _model().encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=show_progress,
        )
    )


def tokenizer_len(text: str) -> int:
    """
    Token count using the bge tokenizer (guide fix 4: chunk size is in TOKENS, not characters).
    """
    return len(_model().tokenizer.encode(text, add_special_tokens=False))
