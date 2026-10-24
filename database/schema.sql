-- ============================================================================
-- KEJI Legal — database schema (run once in Supabase → SQL Editor → New query)
-- Safe to re-run: every statement is idempotent.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ── Statute chunks (RAG corpus) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS statute_chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction  CHAR(2) NOT NULL CHECK (jurisdiction IN ('US','CA','UK','EU')),
    corpus_type   TEXT NOT NULL DEFAULT 'statute',
    statute_name  TEXT NOT NULL,
    section       TEXT NOT NULL DEFAULT '',
    year          INT,
    content       TEXT NOT NULL,
    -- md5 is IMMUTABLE (required for generated columns) and only used to
    -- de-duplicate identical text, so collision resistance is irrelevant here.
    content_hash  TEXT GENERATED ALWAYS AS (md5(content)) STORED,
    embedding     vector(384),
    ts_content    tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    metadata      JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Prevents re-ingesting identical text (guide fix 7)
CREATE UNIQUE INDEX IF NOT EXISTS statute_chunks_hash_idx
    ON statute_chunks (jurisdiction, content_hash);

-- HNSW works on an empty table (guide fix 21)
CREATE INDEX IF NOT EXISTS statute_chunks_hnsw_idx
    ON statute_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS statute_chunks_jurisdiction_idx
    ON statute_chunks (jurisdiction);

-- GIN index for Postgres full-text search (guide fix 3)
CREATE INDEX IF NOT EXISTS statute_chunks_ts_idx
    ON statute_chunks USING gin (ts_content);

-- ── Matters ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS matters (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    matter_ref    TEXT UNIQUE NOT NULL
                  DEFAULT 'KEJ-' || upper(substr(gen_random_uuid()::text, 1, 8)),
    user_id       UUID NOT NULL REFERENCES auth.users(id),
    jurisdiction  CHAR(2) NOT NULL CHECK (jurisdiction IN ('US','CA','UK','EU')),
    matter_type   TEXT NOT NULL,
    party_a       TEXT DEFAULT '',
    party_b       TEXT DEFAULT '',
    description   TEXT DEFAULT '',
    status        TEXT DEFAULT 'intake',
    metadata      JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── Compliance checks (human-in-the-loop audit trail) ───────────────────────
CREATE TABLE IF NOT EXISTS compliance_checks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    matter_id        UUID REFERENCES matters(id) ON DELETE CASCADE,
    check_type       TEXT NOT NULL DEFAULT 'compliance',   -- 'compliance' | 'contract'
    jurisdiction     CHAR(2) CHECK (jurisdiction IN ('US','CA','UK','EU')),
    query            TEXT NOT NULL,
    citations        JSONB NOT NULL DEFAULT '[]',
    raw_output       TEXT NOT NULL DEFAULT '',
    validated_output TEXT,
    status           TEXT NOT NULL DEFAULT 'pending_review'
                     CHECK (status IN ('pending_review','approved','rejected')),
    reviewer_id      UUID REFERENCES auth.users(id),
    reviewer_note    TEXT,
    reviewed_at      TIMESTAMPTZ,
    agent_log        JSONB DEFAULT '[]',
    ragas_scores     JSONB DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS compliance_checks_status_idx
    ON compliance_checks (status, created_at DESC);

-- ── Generated documents ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS generated_documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    matter_id           UUID REFERENCES matters(id) ON DELETE CASCADE,
    doc_type            TEXT NOT NULL,
    content             TEXT NOT NULL,
    version             INT DEFAULT 1,
    compliance_check_id UUID REFERENCES compliance_checks(id),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ── Dense (pgvector) search ──────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION match_statute_chunks(
    query_embedding     vector(384),
    jurisdiction_filter TEXT,
    match_count         INT DEFAULT 10
)
RETURNS TABLE (
    id UUID, statute_name TEXT, section TEXT, jurisdiction CHAR(2),
    year INT, content TEXT, metadata JSONB, similarity FLOAT
)
LANGUAGE SQL STABLE AS $$
    SELECT id, statute_name, section, jurisdiction, year, content, metadata,
           1 - (embedding <=> query_embedding) AS similarity
    FROM statute_chunks
    WHERE jurisdiction = jurisdiction_filter
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;

-- ── Lexical (Postgres full-text) search ──────────────────────────────────────
-- Natural-language questions contain words that never appear in a statute, so
-- requiring ALL terms (plainto_tsquery) returns nothing. We turn the parsed
-- query into an OR query instead; ts_rank then favours chunks matching more terms.
CREATE OR REPLACE FUNCTION lexical_search_chunks(
    query_text          TEXT,
    jurisdiction_filter TEXT,
    match_count         INT DEFAULT 10
)
RETURNS TABLE (
    id UUID, statute_name TEXT, section TEXT, jurisdiction CHAR(2),
    year INT, content TEXT, metadata JSONB, ts_rank FLOAT
)
LANGUAGE SQL STABLE AS $$
    WITH q AS (
        SELECT replace(websearch_to_tsquery('english', query_text)::text, ' & ', ' | ')::tsquery AS tq
    )
    SELECT c.id, c.statute_name, c.section, c.jurisdiction, c.year, c.content, c.metadata,
           ts_rank(c.ts_content, q.tq)::float AS ts_rank
    FROM statute_chunks c, q
    WHERE c.jurisdiction = jurisdiction_filter
      AND c.ts_content @@ q.tq
    ORDER BY ts_rank DESC
    LIMIT match_count;
$$;

-- ── Row Level Security ───────────────────────────────────────────────────────
-- IMPORTANT: Supabase gives the public "anon" key read/write on every table
-- that has RLS switched off. The statute corpus is public law, so anyone may
-- READ it, but nobody except the server (service_role key) may write to it.
ALTER TABLE statute_chunks      ENABLE ROW LEVEL SECURITY;
ALTER TABLE matters             ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_checks   ENABLE ROW LEVEL SECURITY;
ALTER TABLE generated_documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public_read_statutes" ON statute_chunks;
CREATE POLICY "public_read_statutes" ON statute_chunks
    FOR SELECT USING (true);

DROP POLICY IF EXISTS "own_matters" ON matters;
CREATE POLICY "own_matters" ON matters
    FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "own_compliance_checks" ON compliance_checks;
CREATE POLICY "own_compliance_checks" ON compliance_checks
    FOR ALL USING (matter_id IN (SELECT id FROM matters WHERE user_id = auth.uid()));

DROP POLICY IF EXISTS "own_generated_documents" ON generated_documents;
CREATE POLICY "own_generated_documents" ON generated_documents
    FOR ALL USING (matter_id IN (SELECT id FROM matters WHERE user_id = auth.uid()));
