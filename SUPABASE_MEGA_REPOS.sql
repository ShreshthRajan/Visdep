-- Mega-Repos Support: Additional Supabase Schema
-- Run these in Supabase SQL Editor after the main SUPABASE_SETUP.sql

-- 1. Repository Summaries table (HCGS - Hierarchical Code Graph Summarization)
-- Stores pre-computed summaries at repo, package, and file levels
CREATE TABLE IF NOT EXISTS repo_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id INTEGER NOT NULL,  -- Links to repositories table
    level TEXT NOT NULL CHECK (level IN ('repo', 'package', 'file')),
    path TEXT NOT NULL,  -- For repo: repo_name, for package: package/path, for file: file/path
    summary TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(repo_id, level, path)
);

CREATE INDEX IF NOT EXISTS idx_repo_summaries_repo ON repo_summaries(repo_id);
CREATE INDEX IF NOT EXISTS idx_repo_summaries_level ON repo_summaries(repo_id, level);

-- 2. Pre-computed Graph Positions table
-- Stores x,y positions for mega-repo graphs (computed with ForceAtlas2 server-side)
CREATE TABLE IF NOT EXISTS graph_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id INTEGER NOT NULL UNIQUE,  -- One row per repo
    positions JSONB NOT NULL,  -- {node_id: {x: float, y: float}, ...}
    algorithm TEXT DEFAULT 'forceAtlas2',
    iterations INTEGER DEFAULT 10000,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_graph_positions_repo ON graph_positions(repo_id);

-- 3. Pre-indexed Repos registry
-- Tracks which repos have been fully pre-indexed for instant loading
CREATE TABLE IF NOT EXISTS preindexed_repos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_name TEXT NOT NULL UNIQUE,  -- e.g., 'kubernetes/kubernetes'
    repo_id INTEGER NOT NULL,  -- Links to repositories table
    chunk_count INTEGER NOT NULL,
    node_count INTEGER NOT NULL,
    has_summaries BOOLEAN DEFAULT FALSE,
    has_positions BOOLEAN DEFAULT FALSE,
    has_bm25_index BOOLEAN DEFAULT FALSE,
    has_pagerank BOOLEAN DEFAULT FALSE,
    has_faiss_index BOOLEAN DEFAULT FALSE,
    processing_time_seconds INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_preindexed_repos_name ON preindexed_repos(repo_name);

-- 4. Apply updated_at trigger to new tables
CREATE TRIGGER update_repo_summaries_updated_at BEFORE UPDATE ON repo_summaries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_preindexed_repos_updated_at BEFORE UPDATE ON preindexed_repos
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

