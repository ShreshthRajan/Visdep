"""
Chat session management endpoints

Handles:
- Creating new chat sessions
- Loading session data
- Updating sessions (auto-save)
- Deleting sessions
- Listing sessions per repo
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import logging
from .supabase_client import get_supabase_client

router = APIRouter()


class SessionCreate(BaseModel):
    user_id: str
    user_repo_id: str


class SessionUpdate(BaseModel):
    messages: List[dict]
    context_nodes: List[dict]
    highlighted_nodes: Optional[List[str]] = []  # Graph state (cyan nodes)
    title: Optional[str] = None


@router.get("/user/{user_id}/repo/{user_repo_id}/sessions")
async def list_sessions(user_id: str, user_repo_id: str):
    """
    List all chat sessions for a user's repo

    Returns sessions sorted by updated_at (most recent first)
    """
    try:
        supabase = get_supabase_client()

        result = supabase.table('chat_sessions')\
            .select('id, title, created_at, updated_at, messages')\
            .eq('user_id', user_id)\
            .eq('user_repo_id', user_repo_id)\
            .order('updated_at', desc=True)\
            .execute()

        # Add message count
        sessions = []
        for session in result.data:
            sessions.append({
                **session,
                'message_count': len(session.get('messages', []))
            })

        logging.info(f"✅ Found {len(sessions)} sessions for user {user_id}, repo {user_repo_id}")

        return sessions

    except Exception as e:
        logging.error(f"❌ Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """
    Get full session data

    Returns: messages, context_nodes, title
    """
    try:
        supabase = get_supabase_client()

        result = supabase.table('chat_sessions')\
            .select('*')\
            .eq('id', session_id)\
            .single()\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Session not found")

        logging.info(f"✅ Loaded session {session_id}")

        return result.data

    except Exception as e:
        logging.error(f"❌ Error getting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions")
async def create_session(session: SessionCreate):
    """
    Create new chat session

    Returns: session_id
    """
    try:
        supabase = get_supabase_client()

        result = supabase.table('chat_sessions').insert({
            'user_id': session.user_id,
            'user_repo_id': session.user_repo_id,
            'title': None,  # Will be set on first query
            'messages': [],
            'context_nodes': []
        }).execute()

        session_id = result.data[0]['id']

        logging.info(f"✅ Created new session {session_id}")

        return {'session_id': session_id, 'session': result.data[0]}

    except Exception as e:
        logging.error(f"❌ Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/sessions/{session_id}")
async def update_session(session_id: str, update: SessionUpdate):
    """
    Update session (auto-save)

    Updates: messages, context_nodes, title
    """
    try:
        supabase = get_supabase_client()

        update_data = {
            'messages': update.messages,
            'context_nodes': update.context_nodes,
            'highlighted_nodes': update.highlighted_nodes,
            'updated_at': 'now()'
        }

        if update.title:
            update_data['title'] = update.title

        result = supabase.table('chat_sessions')\
            .update(update_data)\
            .eq('id', session_id)\
            .execute()

        logging.info(f"✅ Updated session {session_id}")

        return {'message': 'Session updated'}

    except Exception as e:
        logging.error(f"❌ Error updating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete session"""
    try:
        supabase = get_supabase_client()

        supabase.table('chat_sessions').delete().eq('id', session_id).execute()

        logging.info(f"✅ Deleted session {session_id}")

        return {'message': 'Session deleted'}

    except Exception as e:
        logging.error(f"❌ Error deleting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))
