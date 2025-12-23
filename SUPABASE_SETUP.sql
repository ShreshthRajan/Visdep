-- Visdep Supabase Database Schema
-- Run these in Supabase SQL Editor: https://supabase.com/dashboard/project/wbmqaztxfbuhnaegwnvd/editor

-- 1. Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_id TEXT UNIQUE NOT NULL,
    username TEXT NOT NULL,
    avatar_url TEXT,
    email TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Users can read their own data
CREATE POLICY "Users can read own data"
ON users FOR SELECT
USING (auth.uid()::text = id::text);

-- 2. User Repositories table (links users to their uploaded repos)
CREATE TABLE IF NOT EXISTS user_repos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repo_name TEXT NOT NULL,
    repo_url TEXT NOT NULL,
    is_private BOOLEAN DEFAULT FALSE,
    local_repo_id INTEGER NOT NULL,  -- Links to Railway SQLite repositories.id
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, repo_name)
);

CREATE INDEX IF NOT EXISTS idx_user_repos_user ON user_repos(user_id);
CREATE INDEX IF NOT EXISTS idx_user_repos_accessed ON user_repos(user_id, last_accessed DESC);

-- Enable RLS
ALTER TABLE user_repos ENABLE ROW LEVEL SECURITY;

-- Users can only see their own repos
CREATE POLICY "Users can manage own repos"
ON user_repos FOR ALL
USING (auth.uid()::text = user_id::text);

-- 3. Chat Sessions table (multiple sessions per repo)
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_repo_id UUID NOT NULL REFERENCES user_repos(id) ON DELETE CASCADE,
    title TEXT,
    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    context_nodes JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_repo ON chat_sessions(user_id, user_repo_id, updated_at DESC);

-- Enable RLS
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;

-- Users can manage their own sessions
CREATE POLICY "Users can manage own sessions"
ON chat_sessions FOR ALL
USING (auth.uid()::text = user_id::text);

-- 4. Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to tables
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_chat_sessions_updated_at BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
