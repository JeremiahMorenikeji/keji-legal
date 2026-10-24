"""
LIVE connection test — needs your real .env. Run:
    python tests/test_db.py            (prints ✅ lines)
    KEJI_LIVE=1 pytest tests/test_db.py
"""
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()


def _client(key_env):
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv(key_env))


@pytest.mark.live
def test_connection_and_functions():
    c = _client("SUPABASE_ANON_KEY")
    rows = c.table("statute_chunks").select("id").limit(1).execute()
    print(f"✅ Supabase connected. statute_chunks readable (sample rows: {len(rows.data)})")
    c.rpc("match_statute_chunks", {"query_embedding": [0.0] * 384, "jurisdiction_filter": "UK", "match_count": 1}).execute()
    print("✅ match_statute_chunks function callable.")
    c.rpc("lexical_search_chunks", {"query_text": "test", "jurisdiction_filter": "UK", "match_count": 1}).execute()
    print("✅ lexical_search_chunks function callable.")


@pytest.mark.live
def test_public_key_cannot_write_corpus():
    """The anon key is public. It must NOT be able to insert into the legal corpus."""
    c = _client("SUPABASE_ANON_KEY")
    try:
        c.table("statute_chunks").insert({"jurisdiction": "UK", "statute_name": "INJECTED", "content": "should fail"}).execute()
    except Exception:
        print("✅ anon key cannot write to statute_chunks (RLS working).")
        return
    pytest.fail("SECURITY: the anon key could write to statute_chunks — re-run database/schema.sql to enable RLS")


if __name__ == "__main__":
    test_connection_and_functions()
    test_public_key_cannot_write_corpus()
