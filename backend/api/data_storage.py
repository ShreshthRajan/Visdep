# backend/api/data_storage.py

import sqlite3
import json
import os
from typing import Dict, Any

# Database path - uses Railway volume in production, local file in development
# Railway volume is mounted at /data (persistent across restarts)
DATABASE_PATH = os.getenv('DATABASE_PATH', 'data_storage.db')

# FAISS indexes directory - also on persistent volume in production
FAISS_DIR = os.getenv('FAISS_DIR', 'faiss_indexes')

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
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('INSERT INTO repositories (repo_name, metadata) VALUES (?, ?)', 
                   (repo_name, json.dumps(metadata)))
    
    repo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return repo_id

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
    """Store multiple chunks efficiently"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    chunk_data = [
        (chunk['chunk_id'], repo_id, chunk['file_path'], chunk['type'],
         chunk['name'], chunk['code'], chunk['start_line'], chunk['end_line'],
         json.dumps(chunk['metadata']))
        for chunk in chunks
    ]

    cursor.executemany('''
        INSERT OR REPLACE INTO chunks (chunk_id, repo_id, file_path, chunk_type, name, code,
                           start_line, end_line, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', chunk_data)

    conn.commit()
    conn.close()

def retrieve_chunks(repo_id: int) -> list:
    """Retrieve all chunks for a repository"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT chunk_id, file_path, chunk_type, name, code, start_line, end_line, metadata
        FROM chunks WHERE repo_id = ?
    ''', (repo_id,))

    rows = cursor.fetchall()
    conn.close()

    chunks = []
    for row in rows:
        chunks.append({
            'chunk_id': row[0],
            'file_path': row[1],
            'type': row[2],
            'name': row[3],
            'code': row[4],
            'start_line': row[5],
            'end_line': row[6],
            'metadata': json.loads(row[7])
        })

    return chunks

def get_chunk_by_id(chunk_id: str) -> Dict[str, Any]:
    """Retrieve a specific chunk by ID"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT chunk_id, file_path, chunk_type, name, code, start_line, end_line, metadata
        FROM chunks WHERE chunk_id = ?
    ''', (chunk_id,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'chunk_id': row[0],
            'file_path': row[1],
            'type': row[2],
            'name': row[3],
            'code': row[4],
            'start_line': row[5],
            'end_line': row[6],
            'metadata': json.loads(row[7])
        }
    return None


# ============================================================================
# QUERY CACHE FUNCTIONS (Task 2.1 - Latency Optimization)
# ============================================================================

import hashlib
from datetime import datetime, timedelta

def get_cached_response(query: str, repo_id: int, ttl_days: int = 7) -> str:
    """
    Get cached response for query

    Args:
        query: User query text
        repo_id: Repository ID
        ttl_days: Cache TTL in days (default 7)

    Returns:
        Cached response or None if not found/expired
    """
    try:
        query_hash = hashlib.sha256(query.encode()).hexdigest()

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # Check cache with TTL
        cursor.execute('''
            SELECT response, created_at FROM query_cache
            WHERE query_hash = ? AND repo_id = ?
        ''', (query_hash, repo_id))

        row = cursor.fetchone()
        conn.close()

        if row:
            response, created_at_str = row
            created_at = datetime.fromisoformat(created_at_str)

            # Check TTL
            if datetime.now() - created_at < timedelta(days=ttl_days):
                return response

        return None

    except Exception as e:
        # Graceful degradation: if cache fails, return None (will compute fresh)
        import logging
        logging.warning(f"Cache lookup failed: {e}, proceeding without cache")
        return None


def store_cached_response(query: str, repo_id: int, response: str):
    """
    Store query response in cache

    Args:
        query: User query text
        repo_id: Repository ID
        response: Generated response to cache
    """
    try:
        query_hash = hashlib.sha256(query.encode()).hexdigest()

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # Upsert: insert or update if exists
        cursor.execute('''
            INSERT INTO query_cache (query_hash, repo_id, response, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(query_hash, repo_id) DO UPDATE SET
                response = excluded.response,
                created_at = excluded.created_at
        ''', (query_hash, repo_id, response, datetime.now().isoformat()))

        conn.commit()
        conn.close()

    except Exception as e:
        # Graceful degradation: if cache store fails, just log and continue
        import logging
        logging.warning(f"Cache store failed: {e}, query still completed successfully")


def invalidate_cache_for_repo(repo_id: int):
    """
    Invalidate all cached queries for a repository

    Called when repo is re-uploaded to ensure fresh answers

    Args:
        repo_id: Repository ID
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM query_cache WHERE repo_id = ?', (repo_id,))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        import logging
        logging.info(f"Invalidated {deleted_count} cached queries for repo {repo_id}")

    except Exception as e:
        # Graceful degradation: if invalidation fails, log but don't crash
        import logging
        logging.warning(f"Cache invalidation failed: {e}, continuing anyway")
