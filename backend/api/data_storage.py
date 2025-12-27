# backend/api/data_storage.py

import sqlite3
import json
import os
from typing import Dict, Any, List

# Database path - uses Railway volume in production, local file in development
# Railway volume is mounted at /data (persistent across restarts)
DATABASE_PATH = os.getenv('DATABASE_PATH', 'data_storage.db')

# FAISS indexes directory - also on persistent volume in production
FAISS_DIR = os.getenv('FAISS_DIR', 'faiss_indexes')

# In-memory chunks cache for production performance (eliminates repeated Supabase fetches)
# Cleared on repo re-upload, persists across query sessions
_chunks_cache = {}


def initialize_database():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS repositories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo_name TEXT NOT NULL,
        metadata TEXT NOT NULL
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ast_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo_id INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        ast_info TEXT NOT NULL,
        FOREIGN KEY (repo_id) REFERENCES repositories (id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chunk_id TEXT UNIQUE NOT NULL,
        repo_id INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        chunk_type TEXT NOT NULL,
        name TEXT NOT NULL,
        code TEXT NOT NULL,
        start_line INTEGER,
        end_line INTEGER,
        metadata TEXT NOT NULL,
        FOREIGN KEY (repo_id) REFERENCES repositories (id)
    )
    ''')

    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_chunk_id ON chunks(chunk_id)
    ''')

    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_repo_chunks ON chunks(repo_id)
    ''')

    # Query cache table for latency optimization (Task 2.1)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS query_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query_hash TEXT NOT NULL,
        repo_id INTEGER NOT NULL,
        response TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(query_hash, repo_id)
    )
    ''')

    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_query_cache_lookup ON query_cache(query_hash, repo_id)
    ''')

    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_query_cache_created ON query_cache(created_at)
    ''')

    conn.commit()
    conn.close()

def store_repository_metadata(repo_name: str, metadata: Dict[str, Any]):
    """
    Store repository metadata in Supabase (production scale)

    Returns unique repo_id from Supabase BIGSERIAL (handles unlimited concurrent uploads).
    Replaces SQLite AUTOINCREMENT which had race conditions with concurrent users.
    """
    from .supabase_client import get_supabase_client
    import logging

    try:
        supabase = get_supabase_client()

        # Insert into Supabase repositories table
        result = supabase.table('repositories').insert({
            'repo_name': repo_name,
            'metadata': metadata  # JSONB in Supabase, no need to serialize
        }).execute()

        if not result.data or len(result.data) == 0:
            raise Exception("Failed to insert repository metadata")

        repo_id = result.data[0]['id']
        logging.info(f"✅ Stored repository metadata in Supabase, repo_id={repo_id}")

        return repo_id

    except Exception as e:
        logging.error(f"❌ Error storing repository metadata: {e}")
        raise

def store_ast_data(repo_id: int, file_path: str, ast_info: Dict[str, Any]):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('INSERT INTO ast_data (repo_id, file_path, ast_info) VALUES (?, ?, ?)', 
                   (repo_id, file_path, json.dumps(ast_info)))
    
    conn.commit()
    conn.close()

def retrieve_repository_metadata(repo_name: str) -> Dict[str, Any]:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT metadata FROM repositories WHERE repo_name = ?', (repo_name,))
    row = cursor.fetchone()
    
    conn.close()
    if row:
        return json.loads(row[0])
    return {}

def retrieve_ast_data(repo_id: int) -> Dict[str, Any]:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT file_path, ast_info FROM ast_data WHERE repo_id = ?', (repo_id,))
    rows = cursor.fetchall()

    conn.close()
    ast_data = {row[0]: json.loads(row[1]) for row in rows}
    return ast_data

def store_chunk(repo_id: int, chunk_id: str, file_path: str, chunk_type: str,
                name: str, code: str, start_line: int, end_line: int,
                metadata: Dict[str, Any]):
    """Store a code chunk in the database"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO chunks (chunk_id, repo_id, file_path, chunk_type, name, code,
                           start_line, end_line, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (chunk_id, repo_id, file_path, chunk_type, name, code,
          start_line, end_line, json.dumps(metadata)))

    conn.commit()
    conn.close()

def store_chunks_batch(repo_id: int, chunks: list):
    """
    Store multiple chunks efficiently in Supabase (scalable for 1000+ concurrent users)

    Migration from SQLite → Supabase for multi-tenant production scale.
    Supabase handles unlimited concurrent writes (vs SQLite's ~5-10 limit).
    """
    from .supabase_client import get_supabase_client
    import logging

    if not chunks:
        return

    supabase = get_supabase_client()

    # Convert chunks to Supabase format
    chunk_records = []
    for chunk in chunks:
        chunk_records.append({
            'chunk_id': chunk['chunk_id'],
            'repo_id': repo_id,
            'file_path': chunk['file_path'],
            'chunk_type': chunk['type'],
            'name': chunk['name'],
            'code': chunk['code'],
            'start_line': chunk['start_line'],
            'end_line': chunk['end_line'],
            'metadata': chunk['metadata']  # JSONB in Supabase, no need to serialize
        })

    # CRITICAL: Deduplicate by chunk_id before batching
    # TypeScript/JavaScript files can have duplicate start_lines (decorators, exports)
    # Postgres upsert fails if same chunk_id appears twice in one batch
    # Keep last occurrence (most complete data from AST parser)
    seen = {}
    for record in chunk_records:
        seen[record['chunk_id']] = record
    chunk_records = list(seen.values())

    if len(chunks) != len(chunk_records):
        duplicates_removed = len(chunks) - len(chunk_records)
        logging.warning(f"⚠️ Removed {duplicates_removed} duplicate chunk_ids (AST parser issue)")

    # Batch insert (Supabase supports up to 1000 rows per request)
    # For mega-repos, split into batches
    batch_size = 1000
    total_batches = (len(chunk_records) + batch_size - 1) // batch_size

    for i in range(0, len(chunk_records), batch_size):
        batch = chunk_records[i:i + batch_size]
        batch_num = (i // batch_size) + 1

        try:
            supabase.table('chunks').upsert(batch, on_conflict='chunk_id').execute()
            logging.info(f"✅ Stored batch {batch_num}/{total_batches} ({len(batch)} chunks)")
        except Exception as e:
            logging.error(f"❌ Failed to store batch {batch_num}: {e}")
            raise

    logging.info(f"✅ Stored {len(chunks)} total chunks in Supabase for repo_id={repo_id}")

def retrieve_chunks(repo_id: int) -> list:
    """
    Retrieve all chunks for a repository from Supabase with in-memory caching.

    Performance optimization:
    - First query: Fetches from Supabase (2-3s network latency)
    - Subsequent queries: Returns from memory cache (<1ms)
    - Cache invalidated on repo re-upload

    Optimized for multi-tenant production scale (1000+ concurrent users).
    """
    from .supabase_client import get_supabase_client
    import logging

    # Check in-memory cache first (massive speedup for repeated queries)
    global _chunks_cache
    if repo_id in _chunks_cache:
        logging.info(f"✅ Chunks cache HIT for repo_id={repo_id} ({len(_chunks_cache[repo_id])} chunks from memory)")
        return _chunks_cache[repo_id]

    try:
        supabase = get_supabase_client()

        # Query chunks for this repo with pagination (Supabase default limit is 1000)
        # For mega-repos (100K+ chunks), we must paginate
        all_data = []
        page_size = 1000
        offset = 0
        
        while True:
            result = supabase.table('chunks')\
                .select('chunk_id, file_path, chunk_type, name, code, start_line, end_line, metadata')\
                .eq('repo_id', repo_id)\
                .range(offset, offset + page_size - 1)\
                .execute()
            
            if not result.data:
                break
                
            all_data.extend(result.data)
            
            # Log progress for mega-repos
            if len(all_data) % 10000 == 0:
                logging.info(f"   Loading chunks: {len(all_data):,} loaded...")
            
            # If we got less than page_size, we've reached the end
            if len(result.data) < page_size:
                break
                
            offset += page_size

        if not all_data:
            logging.warning(f"⚠️ No chunks found for repo_id={repo_id}")
            return []

        # Convert Supabase format to internal format
        chunks = []
        for row in all_data:
            chunks.append({
                'chunk_id': row['chunk_id'],
                'file_path': row['file_path'],
                'type': row['chunk_type'],
                'name': row['name'],
                'code': row['code'],
                'start_line': row['start_line'],
                'end_line': row['end_line'],
                'metadata': row['metadata']  # Already deserialized from JSONB
            })

        # Store in cache for future queries
        _chunks_cache[repo_id] = chunks
        logging.info(f"✅ Chunks cache MISS for repo_id={repo_id}, fetched {len(chunks):,} chunks from Supabase (cached for future)")

        return chunks

    except Exception as e:
        logging.error(f"❌ Error retrieving chunks from Supabase: {e}")
        # Fallback to empty for graceful degradation
        return []

def get_chunk_by_id(chunk_id: str) -> Dict[str, Any]:
    """
    Retrieve a specific chunk by ID from Supabase

    Used for inspector and explain features.
    """
    from .supabase_client import get_supabase_client
    import logging

    try:
        supabase = get_supabase_client()

        result = supabase.table('chunks')\
            .select('*')\
            .eq('chunk_id', chunk_id)\
            .limit(1)\
            .execute()

        if not result.data or len(result.data) == 0:
            return None

        row = result.data[0]
        return {
            'chunk_id': row['chunk_id'],
            'file_path': row['file_path'],
            'type': row['chunk_type'],
            'name': row['name'],
            'code': row['code'],
            'start_line': row['start_line'],
            'end_line': row['end_line'],
            'metadata': row['metadata']
        }

    except Exception as e:
        logging.error(f"❌ Error retrieving chunk {chunk_id}: {e}")
        return None


# ============================================================================
# QUERY CACHE FUNCTIONS (Task 2.1 - Latency Optimization)
# ============================================================================

import hashlib
from datetime import datetime, timedelta

def get_cached_response(query: str, repo_id: int, ttl_days: int = 7) -> str:
    """
    Get cached response for query from Supabase

    Migrated to Supabase for production scale (eliminates SQLite write locks).

    Args:
        query: User query text
        repo_id: Repository ID
        ttl_days: Cache TTL in days (default 7)

    Returns:
        Cached response or None if not found/expired
    """
    try:
        from .supabase_client import get_supabase_client
        import logging

        query_hash = hashlib.sha256(query.encode()).hexdigest()
        supabase = get_supabase_client()

        # Check cache with TTL (Postgres handles concurrent reads efficiently)
        result = supabase.table('query_cache')\
            .select('response, created_at')\
            .eq('query_hash', query_hash)\
            .eq('repo_id', repo_id)\
            .limit(1)\
            .execute()

        if result.data and len(result.data) > 0:
            row = result.data[0]
            created_at = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))

            # Check TTL
            if datetime.now(created_at.tzinfo) - created_at < timedelta(days=ttl_days):
                return row['response']

        return None

    except Exception as e:
        # Graceful degradation: if cache fails, return None (will compute fresh)
        import logging
        logging.warning(f"Cache lookup failed: {e}, proceeding without cache")
        return None


def store_cached_response(query: str, repo_id: int, response: str):
    """
    Store query response in cache (Supabase)

    Migrated to Supabase for production scale (eliminates SQLite write locks).

    Args:
        query: User query text
        repo_id: Repository ID
        response: Generated response to cache
    """
    try:
        from .supabase_client import get_supabase_client
        import logging

        query_hash = hashlib.sha256(query.encode()).hexdigest()
        supabase = get_supabase_client()

        # Upsert: insert or update if exists
        cache_record = {
            'query_hash': query_hash,
            'repo_id': repo_id,
            'response': response,
            'created_at': datetime.now().isoformat()
        }

        supabase.table('query_cache').upsert(cache_record, on_conflict='query_hash,repo_id').execute()

    except Exception as e:
        # Graceful degradation: if cache store fails, just log and continue
        import logging
        logging.warning(f"Cache store failed: {e}, query still completed successfully")


def invalidate_cache_for_repo(repo_id: int):
    """
    Invalidate all cached queries for a repository (Supabase)

    Called when repo is re-uploaded to ensure fresh answers.
    Migrated to Supabase for production scale.

    Also clears in-memory chunks cache for this repo.

    Args:
        repo_id: Repository ID
    """
    try:
        from .supabase_client import get_supabase_client
        import logging

        supabase = get_supabase_client()

        # Delete all cache entries for this repo
        result = supabase.table('query_cache').delete().eq('repo_id', repo_id).execute()

        deleted_count = len(result.data) if result.data else 0
        logging.info(f"✅ Invalidated {deleted_count} cached queries for repo {repo_id}")

        # Clear in-memory chunks cache
        global _chunks_cache
        if repo_id in _chunks_cache:
            del _chunks_cache[repo_id]
            logging.info(f"✅ Cleared chunks cache for repo {repo_id}")

    except Exception as e:
        # Graceful degradation: if invalidation fails, log but don't crash
        import logging
        logging.warning(f"⚠️ Cache invalidation failed: {e}, continuing anyway")


# ============================================================================
# CITATION MAPPING FUNCTIONS (Phase 3 - Graph Highlighting)
# ============================================================================

def map_citation_to_chunk_id(citation: Dict[str, Any], repo_id: int) -> str:
    """
    Map a single citation (file + line range) to chunk_id with fuzzy file path matching.

    Migrated to Supabase for production scale.

    Args:
        citation: {'file': 'main.py', 'start_line': 42, 'end_line': 68}
        repo_id: Repository ID

    Returns:
        chunk_id if found, None otherwise
    """
    try:
        import logging
        from .supabase_client import get_supabase_client
        supabase = get_supabase_client()

        cited_file = citation['file']
        start_line = citation['start_line']

        # Try exact match first
        result = supabase.table('chunks')\
            .select('chunk_id')\
            .eq('repo_id', repo_id)\
            .eq('file_path', cited_file)\
            .lte('start_line', start_line)\
            .gte('end_line', start_line)\
            .order('end_line', desc=False)\
            .limit(1)\
            .execute()

        if result.data and len(result.data) > 0:
            return result.data[0]['chunk_id']

        # If no exact match, try fuzzy matching (file_path contains cited filename)
        result = supabase.table('chunks')\
            .select('chunk_id, file_path')\
            .eq('repo_id', repo_id)\
            .like('file_path', f'%{cited_file}')\
            .lte('start_line', start_line)\
            .gte('end_line', start_line)\
            .order('end_line', desc=False)\
            .limit(1)\
            .execute()

        if result.data and len(result.data) > 0:
            logging.debug(f"Fuzzy matched citation '{cited_file}' to chunk file_path '{result.data[0]['file_path']}'")
            return result.data[0]['chunk_id']

        return None

    except Exception as e:
        import logging
        logging.warning(f"Failed to map citation to chunk: {e}")
        return None


def map_citations_to_chunk_ids(citations: List[Dict[str, Any]], repo_id: int) -> List[str]:
    """
    Map multiple citations to chunk IDs for graph highlighting

    Args:
        citations: List of citation dicts from extract_citations_from_response()
                  Format: [{'file': 'main.py', 'start_line': 42, 'end_line': 68}, ...]
        repo_id: Repository ID

    Returns:
        List of unique chunk_ids (may be shorter than citations if some not found)
    """
    import logging

    if not citations or not repo_id:
        logging.warning(f"⚠️ Citation mapping skipped: citations={len(citations) if citations else 0}, repo_id={repo_id}")
        return []

    logging.info(f"🎯 CITATION MAPPING DEBUG: Processing {len(citations)} citations for repo_id={repo_id}")

    chunk_ids = []

    for i, citation in enumerate(citations, 1):
        logging.info(f"   Citation {i}: {citation.get('file', '?')}:{citation.get('start_line', '?')}-{citation.get('end_line', '?')}")

        chunk_id = map_citation_to_chunk_id(citation, repo_id)

        if chunk_id:
            if chunk_id not in chunk_ids:
                chunk_ids.append(chunk_id)
                logging.info(f"     ✅ Mapped to chunk_id: {chunk_id}")
            else:
                logging.info(f"     ⚠️ Duplicate chunk_id (skipped): {chunk_id}")
        else:
            logging.warning(f"     ❌ No chunk found for citation: {citation.get('file', '?')}:{citation.get('start_line', '?')}")

    logging.info(f"✅ Final mapping: {len(citations)} citations → {len(chunk_ids)} unique chunk IDs")
    if chunk_ids:
        logging.info(f"   Highlighted chunks: {chunk_ids}")

    return chunk_ids
