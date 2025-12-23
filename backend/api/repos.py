"""
Repository management endpoints

Handles:
- Fetching user's repos from Supabase
- Loading specific repo
- Repo metadata
"""

from fastapi import APIRouter, HTTPException
import logging
from .supabase_client import get_supabase_client

router = APIRouter()


@router.get("/user/{user_id}/repos")
async def get_user_repos(user_id: str):
    """
    Get all repositories for a user

    Returns repos sorted by last_accessed (most recent first)
    """
    try:
        supabase = get_supabase_client()

        result = supabase.table('user_repos')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('last_accessed', desc=True)\
            .execute()

        logging.info(f"✅ Found {len(result.data)} repos for user {user_id}")

        return result.data

    except Exception as e:
        logging.error(f"❌ Error fetching user repos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/repos/{local_repo_id}/activate")
async def activate_repo(local_repo_id: int):
    """
    Set a repo as the active one (sets global latest_repo_id)

    Used when switching between repos in history panel
    """
    try:
        # Import here to avoid circular dependency
        import backend.main as main_module

        main_module.latest_repo_id = local_repo_id

        logging.info(f"✅ Activated repo {local_repo_id}")

        return {"message": "Repo activated", "repo_id": local_repo_id}

    except Exception as e:
        logging.error(f"❌ Error activating repo: {e}")
        raise HTTPException(status_code=500, detail=str(e))
