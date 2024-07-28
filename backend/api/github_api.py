import requests
from requests.auth import HTTPBasicAuth
import base64

def fetch_repo_content(repo_url, auth_token):
    def fetch_directory_content(api_url, headers):
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        return response.json()

    def fetch_file_content(file_path, headers):
        file_url = f"https://api.github.com/repos/{repo_url.split('github.com/')[-1]}/contents/{file_path}"
        file_response = requests.get(file_url, headers=headers)
        file_response.raise_for_status()
        file_data = file_response.json()
        if 'content' in file_data:
            try:
                file_data['content'] = base64.b64decode(file_data['content']).decode('utf-8')
            except UnicodeDecodeError:
                # Skip binary files or non UTF-8 files
                file_data['content'] = None
        else:
            file_data['content'] = ''
        return file_data

    def fetch_recursive(api_url, headers):
        content = fetch_directory_content(api_url, headers)
        result = []
        for file in content:
            if file['type'] == 'dir':
                result.extend(fetch_recursive(file['url'], headers))
            else:
                file_content = fetch_file_content(file['path'], headers)
                if file_content['content'] is not None:  # Filter out binary files or non UTF-8 files
                    result.append(file_content)
        return result

    try:
        api_url = f"https://api.github.com/repos/{repo_url.split('github.com/')[-1]}/contents"
        headers = {'Authorization': f'token {auth_token}'}
        repo_content = fetch_recursive(api_url, headers)
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
