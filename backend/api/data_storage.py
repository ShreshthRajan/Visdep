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
