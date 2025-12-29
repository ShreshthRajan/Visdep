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

# =============================================================================
# DIRECTORY FILTERING: Exclude dependency/build directories from processing
# =============================================================================
# These directories contain third-party code, build artifacts, or caches that:
# 1. Are not part of the actual codebase
# 2. Dramatically inflate node counts (10K+ files in node_modules alone)
# 3. Cause browser freezes when rendering graphs
# 4. Reduce answer quality by polluting retrieval with irrelevant code
# =============================================================================
EXCLUDED_DIRS = {
    # Version control
    '.git', '.svn', '.hg',

    # Python virtual environments & caches
    '.venv', 'venv', 'env', '.env', 'virtualenv', '.virtualenv',
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    '.tox', '.nox', '.eggs', '*.egg-info',

    # Node.js / JavaScript
    'node_modules', '.npm', '.yarn', '.pnpm-store',

    # PHP
    'vendor',

    # Ruby
    'bundle', '.bundle',

    # Go
    'vendor',  # Go modules vendor

    # Rust
    'target',

    # Java / Kotlin
    'target', 'build', '.gradle', '.mvn',

    # .NET
    'bin', 'obj', 'packages',

    # iOS / macOS
    'Pods', 'Carthage', '.build',

    # Build outputs
    'build', 'dist', 'out', '_build', 'output',

    # Coverage & test artifacts
    'coverage', '.coverage', 'htmlcov', '.nyc_output',

    # IDE & editor
    '.idea', '.vscode', '.vs', '.eclipse',

    # Next.js / Nuxt / Svelte
    '.next', '.nuxt', '.output', '.svelte-kit', '.vercel',

    # Documentation builds (generated)
    '_site', 'site', '.docusaurus',

    # Misc caches
    '.cache', '.parcel-cache', '.turbo', '.nx',
}

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


def fetch_repo_content_via_git(repo_url, sub_directory=None, oauth_token=None):
    """
    Fetch repository content using git clone (FAST, no rate limits).

    Uses shallow clone (--depth 1) for maximum performance.
    Industry-standard approach used by GitHub Copilot, Sourcegraph, etc.

    Args:
        repo_url: GitHub repository URL
        sub_directory: Optional subdirectory to focus on
        oauth_token: Optional GitHub OAuth token for private repo access

    Returns:
        List of {path, content} dicts
    """
    temp_dir = None
    try:
        # Create temporary directory for clone
        temp_dir = tempfile.mkdtemp(prefix='visdep_clone_')

        # Parse repo URL
        repo_url, _ = normalize_repo_url(repo_url)

        # Inject OAuth token for private repo access
        clone_url = repo_url
        if oauth_token:
            # Use x-access-token format for OAuth (standard GitHub pattern)
            clone_url = repo_url.replace(
                "https://github.com/",
                f"https://x-access-token:{oauth_token}@github.com/"
            )
            if not clone_url.endswith('.git'):
                clone_url += '.git'
            logging.info(f"🔒 Cloning private repository with OAuth token")
        else:
            logging.info(f"🚀 Cloning public repository (no auth)")

        # Shallow clone for maximum speed (only latest commit, single branch)
        clone_cmd = [
            'git', 'clone',
            '--depth', '1',  # Shallow clone (only latest commit)
            '--single-branch',  # Only main branch
            '--quiet',  # Suppress output
            clone_url,
            temp_dir
        ]

        result = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            raise RuntimeError(f"Git clone failed: {result.stderr}")

        logging.info(f"✅ Clone complete, parsing files...")

        # Walk directory and collect file contents
        repo_content = []
        target_dir = os.path.join(temp_dir, sub_directory) if sub_directory else temp_dir

        excluded_count = 0
        for root, dirs, files in os.walk(target_dir):
            # CRITICAL: Filter directories IN-PLACE to prevent os.walk from descending
            # This is the standard Python pattern for pruning directory traversal
            original_dir_count = len(dirs)
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            excluded_count += original_dir_count - len(dirs)

            # Also skip if we're already inside an excluded directory (belt and suspenders)
            if any(excluded in root for excluded in EXCLUDED_DIRS):
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

        if excluded_count > 0:
            logging.info(f"🚫 Filtered {excluded_count} dependency/build directories (node_modules, vendor, .venv, etc.)")
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
