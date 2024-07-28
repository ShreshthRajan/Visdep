import unittest
import sys
import os

# Add the parent directory to the sys.path to ensure modules can be found
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.data_storage import (
    initialize_database,
    store_repository_metadata,
    store_ast_data,
    retrieve_repository_metadata,
    retrieve_ast_data
)

class TestDataStorage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        initialize_database()

    def test_store_and_retrieve_repository_metadata(self):
        repo_name = 'test_repo'
        metadata = {'description': 'Test repository', 'owner': 'test_owner'}
        store_repository_metadata(repo_name, metadata)
        
        retrieved_metadata = retrieve_repository_metadata(repo_name)
        self.assertEqual(metadata, retrieved_metadata)
    
    def test_store_and_retrieve_ast_data(self):
        repo_name = 'test_repo'
        metadata = {'description': 'Test repository', 'owner': 'test_owner'}
        store_repository_metadata(repo_name, metadata)
        
        file_path = 'test_file.py'
        ast_info = {'functions': ['test_func'], 'classes': ['TestClass'], 'imports': ['os']}
        store_ast_data(repo_name, file_path, ast_info)
        
        retrieved_ast_data = retrieve_ast_data(repo_name)
        self.assertEqual({file_path: ast_info}, retrieved_ast_data)

if __name__ == '__main__':
    unittest.main()
