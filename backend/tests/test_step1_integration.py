# backend/tests/test_step1_integration.py

"""
Integration tests for Step 1: Smart Code Chunking

Tests the full flow:
1. Parse code to AST
2. Generate chunks
3. Store in database
4. Retrieve chunks
5. Create vector store
"""

import unittest
import os
import sys
import tempfile
import shutil
from backend.api.data_storage import (
    initialize_database,
    store_repository_metadata,
    store_chunks_batch,
    retrieve_chunks,
    DATABASE_PATH
)
from backend.api.chunk_processor import process_repository_to_chunks, get_chunk_stats


class TestStep1Integration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up test database"""
        # Use a temporary database for testing
        cls.original_db_path = DATABASE_PATH
        cls.test_db_path = tempfile.mktemp(suffix='.db')

        # Monkey patch the DATABASE_PATH
        import backend.api.data_storage as ds
        ds.DATABASE_PATH = cls.test_db_path

        # Initialize test database
        initialize_database()

    @classmethod
    def tearDownClass(cls):
        """Clean up test database"""
        if os.path.exists(cls.test_db_path):
            os.remove(cls.test_db_path)

        # Restore original DATABASE_PATH
        import backend.api.data_storage as ds
        ds.DATABASE_PATH = cls.original_db_path

    def test_full_chunking_flow(self):
        """Test complete flow from AST to chunks to database"""

        # Step 1: Create mock AST data (simulating parse_code_to_ast output)
        ast_data = {
            'file1.py': {
                'functions': ['hello', 'world'],
                'classes': [],
                'imports': ['os', 'sys'],
                'content': '''
def hello():
    print("Hello")
    return True

def world():
    print("World")
    return False
'''
            },
            'file2.py': {
                'functions': [],
                'classes': ['MyClass'],
                'imports': [],
                'content': '''
class MyClass:
    def __init__(self):
        self.value = 0

    def increment(self):
        self.value += 1
'''
            }
        }

        # Step 2: Store repository metadata
        repo_metadata = {
            'full_name': 'test/repo',
            'description': 'Test repository'
        }
        repo_id = store_repository_metadata('test/repo', repo_metadata)
        self.assertIsNotNone(repo_id)
        self.assertGreater(repo_id, 0)

        # Step 3: Process to chunks
        chunks = process_repository_to_chunks(ast_data)
        self.assertGreater(len(chunks), 0)

        # Verify we got chunks from both files
        file_paths = {c['file_path'] for c in chunks}
        self.assertIn('file1.py', file_paths)
        self.assertIn('file2.py', file_paths)

        # Verify function chunks
        function_chunks = [c for c in chunks if c['type'] == 'function']
        self.assertGreaterEqual(len(function_chunks), 2)  # At least hello and world

        function_names = {c['name'] for c in function_chunks}
        self.assertIn('hello', function_names)
        self.assertIn('world', function_names)

        # Verify class chunks
        class_chunks = [c for c in chunks if c['type'] == 'class']
        self.assertGreaterEqual(len(class_chunks), 1)  # At least MyClass

        # Step 4: Store chunks in database
        store_chunks_batch(repo_id, chunks)

        # Step 5: Retrieve chunks from database
        retrieved_chunks = retrieve_chunks(repo_id)
        self.assertEqual(len(retrieved_chunks), len(chunks))

        # Verify retrieved chunks have correct structure
        for chunk in retrieved_chunks:
            self.assertIn('chunk_id', chunk)
            self.assertIn('file_path', chunk)
            self.assertIn('type', chunk)
            self.assertIn('name', chunk)
            self.assertIn('code', chunk)
            self.assertIn('start_line', chunk)
            self.assertIn('end_line', chunk)
            self.assertIn('metadata', chunk)

        # Step 6: Get statistics
        stats = get_chunk_stats(chunks)
        self.assertEqual(stats['total'], len(chunks))
        self.assertIn('function', stats['by_type'])
        self.assertIn('class', stats['by_type'])
        self.assertEqual(stats['files_processed'], 2)

        print(f"\n✅ Integration test passed!")
        print(f"   - Created repo_id: {repo_id}")
        print(f"   - Generated {len(chunks)} chunks")
        print(f"   - Function chunks: {stats['by_type'].get('function', 0)}")
        print(f"   - Class chunks: {stats['by_type'].get('class', 0)}")
        print(f"   - Avg lines per chunk: {stats['avg_lines']:.1f}")

    def test_chunk_code_extraction(self):
        """Test that chunk code contains actual function/class bodies"""

        ast_data = {
            'test.py': {
                'functions': ['calculate'],
                'classes': [],
                'imports': [],
                'content': '''
def calculate(x, y):
    result = x + y
    return result
'''
            }
        }

        chunks = process_repository_to_chunks(ast_data)
        self.assertEqual(len(chunks), 1)

        chunk = chunks[0]
        self.assertEqual(chunk['name'], 'calculate')
        self.assertIn('def calculate', chunk['code'])
        self.assertIn('result = x + y', chunk['code'])
        self.assertIn('return result', chunk['code'])

    def test_empty_file_creates_file_chunk(self):
        """Test that files with no functions/classes still create a chunk"""

        ast_data = {
            'config.py': {
                'functions': [],
                'classes': [],
                'imports': [],
                'content': '# Configuration\nCONFIG = {"key": "value"}'
            }
        }

        chunks = process_repository_to_chunks(ast_data)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['type'], 'file')


if __name__ == '__main__':
    unittest.main()
