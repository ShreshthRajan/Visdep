import unittest
from unittest.mock import patch
from api.github_api import fetch_repo_content, fetch_repo_metadata
from api.ast_parser import parse_code_to_ast
import base64
import tempfile
import os

class TestIntegration(unittest.TestCase):
    
    @patch('api.github_api.requests.get')
    def test_integration(self, mock_get):
        python_code = "def hello_world():\n    print('Hello, world!')"
        encoded_content = base64.b64encode(python_code.encode('utf-8')).decode('utf-8')
        
        mock_content_response = [
            {
                'path': 'test_file.py',
                'content': encoded_content  # Base64 encoded Python code
            }
        ]
        mock_metadata_response = {
            'name': 'test_repo',
            'owner': {'login': 'test_owner'}
        }
        
        mock_get.side_effect = [
            unittest.mock.Mock(status_code=200, json=lambda: mock_content_response),
            unittest.mock.Mock(status_code=200, json=lambda: mock_metadata_response)
        ]
        
        repo_url = 'https://github.com/test/repo'
        auth_token = 'fake_token'
        
        # Fetch repository content and metadata
        repo_content = fetch_repo_content(repo_url, auth_token)
        repo_metadata = fetch_repo_metadata(repo_url, auth_token)
        
        # Parse the repository content to AST
        parsed_data = parse_code_to_ast(repo_content)
        
        # Capture the actual path used for the downloaded file
        expected_file_path = 'test_file.py'  # Relative path
        
        # Check if the parsed data contains expected function names
        self.assertIn('hello_world', parsed_data[expected_file_path]['functions'])
    
if __name__ == '__main__':
    unittest.main()
