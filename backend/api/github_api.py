# dependency_extraction/backend/api/github_api.py
import requests
from requests.auth import HTTPBasicAuth
import base64
import re
import subprocess
import tempfile
import os
import shutil
import logging

def normalize_repo_url(repo_url):
    # Remove trailing slash if present
    repo_url = repo_url.rstrip('/')
    # Extract owner and repo name
    match = re.match(r'https://github.com/([^/]+)/([^/]+)(/.*)?', repo_url)
    if match:
        owner, repo, path = match.groups()
        return f'https://github.com/{owner}/{repo}', path
    else:
        raise ValueError("Invalid GitHub repository URL")


def fetch_repo_content_via_git(repo_url, sub_directory=None):
    """
    Fetch repository content using git clone (FAST, no rate limits).

    Uses shallow clone (--depth 1) for maximum performance.
    Industry-standard approach used by GitHub Copilot, Sourcegraph, etc.

    Args:
        repo_url: GitHub repository URL
        sub_directory: Optional subdirectory to focus on

    Returns:
        List of {path, content} dicts
    """
    temp_dir = None
    try:
        # Create temporary directory for clone
        temp_dir = tempfile.mkdtemp(prefix='visdep_clone_')

        # Parse repo URL
        repo_url, _ = normalize_repo_url(repo_url)

        logging.info(f"🚀 Cloning repository via git (fast, no API limits): {repo_url}")

        # Shallow clone for maximum speed (only latest commit, single branch)
        clone_cmd = [
            'git', 'clone',
            '--depth', '1',  # Shallow clone (only latest commit)
            '--single-branch',  # Only main branch
            '--quiet',  # Suppress output
            repo_url,
            temp_dir
        ]

        result = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            raise RuntimeError(f"Git clone failed: {result.stderr}")

        logging.info(f"✅ Clone complete, parsing files...")

        # Walk directory and collect file contents
        repo_content = []
        target_dir = os.path.join(temp_dir, sub_directory) if sub_directory else temp_dir

        for root, dirs, files in os.walk(target_dir):
            # Skip .git directory
            if '.git' in root:
                continue

            for filename in files:
                file_path = os.path.join(root, filename)

                # Get relative path from repo root
                relative_path = os.path.relpath(file_path, temp_dir)

                # Only process text files (skip binaries, images, etc.)
                if not _is_text_file(filename):
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    repo_content.append({
                        'path': relative_path,
                        'content': content,
                        'name': filename,
                        'type': 'file'
                    })
                except (UnicodeDecodeError, IOError):
                    # Skip files that can't be read as text
                    continue

        logging.info(f"✅ Parsed {len(repo_content)} files from repository")
        return repo_content

    finally:
        # Always cleanup temp directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def _is_text_file(filename):
    """Check if file is likely a text file (code) vs binary."""
    text_extensions = {
        '.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go', '.rs',
        '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.swift',
        '.kt', '.scala', '.sh', '.bash', '.yml', '.yaml', '.json',
        '.md', '.txt', '.rst', '.html', '.css', '.sql'
    }
    _, ext = os.path.splitext(filename)
    return ext.lower() in text_extensions

def fetch_repo_content(repo_url, auth_token, sub_directory=None):
    def fetch_directory_content(api_url, headers):
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        return response.json()

    def fetch_file_content(file_path, headers):
        file_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
        file_response = requests.get(file_url, headers=headers)
        file_response.raise_for_status()
        file_data = file_response.json()
        if 'content' in file_data:
            try:
                file_data['content'] = base64.b64decode(file_data['content']).decode('utf-8')
            except UnicodeDecodeError:
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
                if file_content['content'] is not None:
                    result.append(file_content)
        return result

    try:
        repo_url, path = normalize_repo_url(repo_url)
        repo_owner, repo_name = repo_url.split('github.com/')[-1].split('/')
        
        if sub_directory:
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{sub_directory}"
        elif path:
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents{path}"
        else:
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents"
        
        headers = {'Authorization': f'token {auth_token}'}
        repo_content = fetch_recursive(api_url, headers)
        return repo_content
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error fetching repository content: {e}")

def fetch_repo_metadata(repo_url, auth_token):
    try:
        repo_url, _ = normalize_repo_url(repo_url)
        api_url = f"https://api.github.com/repos/{repo_url.split('github.com/')[-1]}"
        headers = {'Authorization': f'token {auth_token}'}
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error fetching repository metadata: {e}")
