import requests
from requests.auth import HTTPBasicAuth
import base64

def fetch_repo_content(repo_url, auth_token):
    try:
        api_url = f"https://api.github.com/repos/{repo_url.split('github.com/')[-1]}/contents"
        headers = {'Authorization': f'token {auth_token}'}
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        repo_content = response.json()

        # Decode content if present
        for file in repo_content:
            if 'content' in file:
                file['content'] = base64.b64decode(file['content']).decode('utf-8')
            else:
                # Handle files that need to be fetched individually
                file_path = file['path']
                file_url = f"https://api.github.com/repos/{repo_url.split('github.com/')[-1]}/contents/{file_path}"
                file_response = requests.get(file_url, headers=headers)
                file_response.raise_for_status()
                file_data = file_response.json()
                if 'content' in file_data:
                    file['content'] = base64.b64decode(file_data['content']).decode('utf-8')
                else:
                    file['content'] = ''

        return repo_content
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error fetching repository content: {e}")

def fetch_repo_metadata(repo_url, auth_token):
    try:
        api_url = f"https://api.github.com/repos/{repo_url.split('github.com/')[-1]}"
        headers = {'Authorization': f'token {auth_token}'}
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error fetching repository metadata: {e}")
