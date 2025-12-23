"""
Authentication endpoints for GitHub OAuth

Handles:
- GitHub OAuth redirect
- OAuth callback (code exchange)
- User session management
- Token verification
"""

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import os
import requests
import logging
from typing import Optional
from .supabase_client import get_supabase_client

router = APIRouter()

# GitHub OAuth configuration
GITHUB_CLIENT_ID = os.getenv('GITHUB_OAUTH_CLIENT_ID')
GITHUB_CLIENT_SECRET = os.getenv('GITHUB_OAUTH_CLIENT_SECRET')

# Detect environment for callback URL
# Railway sets RAILWAY_PROJECT_ID in production
IS_PRODUCTION = bool(os.getenv('RAILWAY_PROJECT_ID'))
CALLBACK_URL = 'https://visdep.com/auth/callback' if IS_PRODUCTION else 'http://localhost:3000/auth/callback'


@router.get("/auth/github")
async def github_oauth_redirect():
    """
    Redirect user to GitHub OAuth authorization page

    Scopes requested:
    - user:email - Get user email
    - repo - Access private repositories
    """
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    # GitHub OAuth URL
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={CALLBACK_URL}"
        f"&scope=user:email repo"
    )

    logging.info(f"🔐 Redirecting to GitHub OAuth: {github_auth_url}")
    return RedirectResponse(github_auth_url)


@router.get("/auth/callback")
async def github_oauth_callback(code: str):
    """
    Handle GitHub OAuth callback

    Exchanges authorization code for access token
    Creates or updates user in Supabase
    Returns user data
    """
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    try:
        # Exchange code for access token
        token_response = requests.post(
            'https://github.com/login/oauth/access_token',
            headers={'Accept': 'application/json'},
            data={
                'client_id': GITHUB_CLIENT_ID,
                'client_secret': GITHUB_CLIENT_SECRET,
                'code': code
            }
        )

        token_data = token_response.json()

        if 'error' in token_data:
            raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {token_data.get('error_description')}")

        access_token = token_data.get('access_token')

        if not access_token:
            raise HTTPException(status_code=400, detail="No access token received from GitHub")

        # Get user info from GitHub
        user_response = requests.get(
            'https://api.github.com/user',
            headers={'Authorization': f'token {access_token}'}
        )

        github_user = user_response.json()

        # Create or update user in Supabase
        supabase = get_supabase_client()

        # Check if user exists
        existing_user = supabase.table('users').select('*').eq('github_id', str(github_user['id'])).execute()

        user_data = {
            'github_id': str(github_user['id']),
            'username': github_user['login'],
            'avatar_url': github_user.get('avatar_url'),
            'email': github_user.get('email')
        }

        if existing_user.data and len(existing_user.data) > 0:
            # Update existing user
            result = supabase.table('users').update(user_data).eq('github_id', str(github_user['id'])).execute()
            user_id = existing_user.data[0]['id']
            logging.info(f"✅ Updated existing user: {github_user['login']}")
        else:
            # Create new user
            result = supabase.table('users').insert(user_data).execute()
            user_id = result.data[0]['id']
            logging.info(f"✅ Created new user: {github_user['login']}")

        # Return user info + access token for frontend storage
        return {
            'user': {
                'id': user_id,
                'github_id': str(github_user['id']),
                'username': github_user['login'],
                'avatar_url': github_user.get('avatar_url'),
                'email': github_user.get('email')
            },
            'access_token': access_token  # Frontend stores this for git clone
        }

    except Exception as e:
        logging.error(f"❌ OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.post("/auth/logout")
async def logout():
    """Sign out user"""
    return {"message": "Logged out successfully"}


@router.get("/auth/me")
async def get_current_user(user_id: str):
    """
    Get current user from Supabase

    Args:
        user_id: UUID of user

    Returns:
        User object
    """
    try:
        supabase = get_supabase_client()

        result = supabase.table('users').select('*').eq('id', user_id).execute()

        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="User not found")

        return result.data[0]

    except Exception as e:
        logging.error(f"❌ Error fetching user: {e}")
        raise HTTPException(status_code=500, detail=str(e))
