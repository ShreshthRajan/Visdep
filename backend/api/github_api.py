import requests
from requests.auth import HTTPBasicAuth

def fetch_repo_content(repo_url, auth_token):
    try:
        api_url = f"https://api.github.com/repos/{repo_url.split('github.com/')[-1]}/contents"
        headers = {'Authorization': f'token {auth_token}'}
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        return response.json()
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