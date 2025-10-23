# backend/api/data_storage.py

import sqlite3
import json
from typing import Dict, Any

DATABASE_PATH = 'data_storage.db'

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
