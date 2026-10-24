import numpy as np
from api.rag import embedder
from api.rag.chunker import chunk_text, CHUNK_TOKENS


def test_embed_query_shape_and_norm():
    v = embedder.embed_query("What is a contract?")
    assert v.shape == (384,)
    assert abs(np.linalg.norm(v) - 1.0) < 1e-6


def test_query_prefix_applied_but_documents_unprefixed(monkeypatch):
    seen = []
    class M:
        tokenizer = embedder._model().tokenizer
        def encode(self, t, **kw): seen.append(t); return np.zeros(384)
    monkeypatch.setattr(embedder, "_model", lambda: M())
    embedder.embed_query("hello")
    embedder.embed_documents(["doc one"], show_progress=False)
    assert seen[0].startswith(embedder.QUERY_PREFIX)
    assert seen[1] == ["doc one"]


def test_chunk_metadata_and_header():
    chunks = chunk_text("Section 1. All persons are equal.\n\nSection 2. No discrimination.", "Test Act", "UK", 2020)
    assert chunks and all(c["jurisdiction"] == "UK" and c["year"] == 2020 for c in chunks)
    assert chunks[0]["content"].startswith("Test Act — ")          # statute name searchable
    assert chunks[0]["metadata"]["token_count"] > 0


def test_known_section_is_used_verbatim():
    chunks = chunk_text("Some provision text here.", "Act", "CA", section="Section 42")
    assert chunks[0]["section"] == "Section 42"
    assert chunks[0]["content"].startswith("Act — Section 42")


def test_long_text_splits_within_token_budget():
    text = " ".join(f"word{i}" for i in range(3000))   # fake tokenizer: 1 word = 1 token
    chunks = chunk_text(text, "Big Act", "EU")
    assert len(chunks) >= 5
    assert all(c["metadata"]["token_count"] <= CHUNK_TOKENS for c in chunks)


def test_empty_text_returns_nothing():
    assert chunk_text("   ", "Act", "UK") == []
