-- =============================================================================
-- SUPABASE MIGRATION SCRIPT
-- Run this in Supabase SQL Editor (Project → SQL Editor → New Query)
-- =============================================================================

-- 1. REPOSITORIES TABLE
CREATE TABLE IF NOT EXISTS repositories (
    id SERIAL PRIMARY KEY,
    repo_name TEXT NOT NULL,
    metadata JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_repositories_name ON repositories(repo_name);

-- 2. AST_DATA TABLE
CREATE TABLE IF NOT EXISTS ast_data (
    id SERIAL PRIMARY KEY,
    repo_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    ast_info JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ast_data_repo ON ast_data(repo_id);

-- 3. CHUNKS TABLE
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    chunk_id TEXT UNIQUE NOT NULL,
    repo_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    metadata JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunk_id ON chunks(chunk_id);
CREATE INDEX IF NOT EXISTS idx_repo_chunks ON chunks(repo_id);
CREATE INDEX IF NOT EXISTS idx_chunk_type ON chunks(chunk_type);

-- 4. QUERY_CACHE TABLE (Task 2.1 - Latency Optimization)
CREATE TABLE IF NOT EXISTS query_cache (
    id SERIAL PRIMARY KEY,
    query_hash TEXT NOT NULL,
    repo_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    response TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(query_hash, repo_id)
);

CREATE INDEX IF NOT EXISTS idx_query_cache_lookup ON query_cache(query_hash, repo_id);
CREATE INDEX IF NOT EXISTS idx_query_cache_created ON query_cache(created_at);

-- 5. ENABLE ROW LEVEL SECURITY (For Future Multi-User Support)
ALTER TABLE repositories ENABLE ROW LEVEL SECURITY;
ALTER TABLE ast_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE query_cache ENABLE ROW LEVEL SECURITY;

-- 6. CREATE POLICIES (Public access for now, restrict later with auth)
CREATE POLICY "Public access for repositories" ON repositories FOR ALL USING (true);
CREATE POLICY "Public access for ast_data" ON ast_data FOR ALL USING (true);
CREATE POLICY "Public access for chunks" ON chunks FOR ALL USING (true);
CREATE POLICY "Public access for query_cache" ON query_cache FOR ALL USING (true);

-- =============================================================================
-- VERIFICATION QUERIES (Run these to verify tables created)
-- =============================================================================

-- Check tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Expected output:
-- ast_data
-- chunks
-- query_cache
-- repositories

-- Check indexes
SELECT indexname FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY indexname;

-- =============================================================================
-- NOTES:
-- - SERIAL = auto-increment (Postgres equivalent of SQLite AUTOINCREMENT)
-- - JSONB = JSON with indexing (better than JSON type)
-- - TEXT = unlimited length string
-- - TIMESTAMP = datetime with timezone
-- - ON DELETE CASCADE = auto-delete child records when parent deleted
-- - Row Level Security enabled but set to public (for now)
-- =============================================================================
