import pytest
from api.rag import retriever
from tests.conftest import make_chunk


class FakeRPC:
    def __init__(self, dense, lex, fail=()):
        self.dense, self.lex, self.fail, self.calls = dense, lex, fail, []
    def rpc(self, name, params):
        self.calls.append((name, params))
        outer = self
        class E:
            def execute(s):
                if name in outer.fail: raise RuntimeError(f"{name} down")
                class R: data = outer.dense if name == "match_statute_chunks" else outer.lex
                return R()
        return E()


def test_rrf_prefers_docs_found_by_both_legs():
    a, b, c = make_chunk(1), make_chunk(2), make_chunk(3)
    merged = retriever.rrf_merge([b, a], [a, c], limit=5)
    assert [d["id"] for d in merged][0] == a["id"]            # in both lists → wins
    assert [d["rrf_rank"] for d in merged] == [1, 2, 3]
    assert merged[0]["dense_rank"] == 2 and merged[0]["lex_rank"] == 1


def test_rrf_respects_limit_and_lexical_only_hits_survive():
    docs = [make_chunk(i) for i in range(1, 9)]
    assert len(retriever.rrf_merge(docs, [], limit=3)) == 3
    only_lex = retriever.rrf_merge([], [docs[0]], limit=5)
    assert only_lex and only_lex[0]["rrf_rank"] == 1          # no fake 0.00 relevance dropping it


def test_retrieve_filters_by_jurisdiction_and_passes_k(monkeypatch):
    fake = FakeRPC([make_chunk(1)], [make_chunk(2)])
    monkeypatch.setattr(retriever, "get_supabase", lambda: fake)
    out = retriever.retrieve("director duties", "UK")
    assert len(out) == 2
    for _, params in fake.calls:
        assert params["jurisdiction_filter"] == "UK"
    assert fake.calls[0][1]["match_count"] == 10               # k*2 fetched for fusion


def test_one_failing_leg_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(retriever, "get_supabase", lambda: FakeRPC([make_chunk(1)], [], fail=("lexical_search_chunks",)))
    assert len(retriever.retrieve("q", "EU")) == 1


def test_both_legs_failing_raises(monkeypatch):
    monkeypatch.setattr(retriever, "get_supabase",
                        lambda: FakeRPC([], [], fail=("lexical_search_chunks", "match_statute_chunks")))
    with pytest.raises(RuntimeError):
        retriever.retrieve("q", "EU")


def test_invalid_jurisdiction_rejected():
    with pytest.raises(ValueError):
        retriever.retrieve("q", "XX")
