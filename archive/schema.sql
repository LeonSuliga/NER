-- Schema for Legal Acts entity linking (PostgreSQL + pgvector + pg_trgm)

-- Required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Table of legal acts
CREATE TABLE IF NOT EXISTS legal_acts (
    id VARCHAR PRIMARY KEY,
    publisher VARCHAR,
    year INT,
    position INT,
    title TEXT,
    title_clean TEXT,
    act_type VARCHAR,
    status VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now(),
    raw JSONB
);

-- B-tree index for exact lookups by publisher/year/position
CREATE INDEX IF NOT EXISTS idx_legal_acts_pub_year_pos ON legal_acts (publisher, year, position);

-- Trigram GIN index for fuzzy title search
CREATE INDEX IF NOT EXISTS idx_legal_acts_title_trgm ON legal_acts USING gin (title gin_trgm_ops);

-- Aliases table (official short names, colloquial names, abbreviations)
CREATE TABLE IF NOT EXISTS act_aliases (
    id SERIAL PRIMARY KEY,
    act_id VARCHAR REFERENCES legal_acts(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_type VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(act_id, alias, alias_type)
);

-- Embeddings table: stores one representative embedding per act (adjust dimension to your model)
-- Default dimension set to 768 (common for all-mpnet-base-v2). Change as needed.
CREATE TABLE IF NOT EXISTS act_embeddings (
    act_id VARCHAR PRIMARY KEY REFERENCES legal_acts(id) ON DELETE CASCADE,
    text_represented TEXT,
    embedding VECTOR(768),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ANN index for semantic search. Using ivfflat with cosine operator class.
-- Tune lists parameter depending on dataset size.
CREATE INDEX IF NOT EXISTS act_embeddings_embedding_ivfflat_idx
    ON act_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Notes:
-- - The VECTOR(768) dimension should match the embedding model output dimension used when populating act_embeddings.
-- - For HNSW indexes (pgvector >= 0.4) you can use:
--     CREATE INDEX ... USING hnsw (embedding);
--   if preferred.
