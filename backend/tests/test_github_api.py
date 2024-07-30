import unittest
from unittest.mock import patch
from backend.api.github_api import fetch_repo_content, fetch_repo_metadata

class TestGitHubAPI(unittest.TestCase):
    
    @patch('backend.api.github_api.requests.get')
    def test_fetch_repo_content(self, mock_get):
        mock_response = {
            'path': 'test_file.py',
            'content': 'aGVsbG8gd29ybGQ='  # Base64 encoded 'hello world'
        }
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [mock_response]
        
        repo_url = 'https://github.com/test/repo'
        auth_token = 'fake_token'
        content = fetch_repo_content(repo_url, auth_token)
        
        self.assertEqual(content, [mock_response])
    
    @patch('backend.api.github_api.requests.get')
    def test_fetch_repo_metadata(self, mock_get):
        mock_response = {
            'name': 'test_repo',
            'owner': {'login': 'test_owner'}
        }
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        
        repo_url = 'https://github.com/test/repo'
        auth_token = 'fake_token'
        metadata = fetch_repo_metadata(repo_url, auth_token)
        
        self.assertEqual(metadata, mock_response)

if __name__ == '__main__':
    unittest.main()
