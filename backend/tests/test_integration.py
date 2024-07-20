import unittest
from unittest.mock import patch
from api.github_api import fetch_repo_content, fetch_repo_metadata
from api.ast_parser import parse_code_to_ast

class TestIntegration(unittest.TestCase):
    
    @patch('api.github_api.requests.get')
    def test_integration(self, mock_get):
        mock_content_response = [
            {
                'path': 'test_file.py',
                'content': 'ZGVmIGhlbGxvX3dvcmxkKCk6XG4gICAgcHJpbnQoIkhlbGxvLCB3b3JsZCEiKQ=='  # Base64 encoded Python code
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
        
        # Check if the parsed data contains expected function names
        self.assertIn('hello_world', parsed_data['/path/to/local/repo/test_file.py']['functions'])
    
if __name__ == '__main__':
    unittest.main()
