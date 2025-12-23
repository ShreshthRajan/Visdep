"""
Supabase client for user management and session storage

Handles:
- User authentication
- Repository metadata (user-owned repos)
- Chat session persistence
"""

import os
from supabase import create_client, Client
import logging

# Initialize Supabase client
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    logging.warning("⚠️ Supabase credentials not found in environment variables")
    logging.warning("⚠️ Multi-user features will not work")
    supabase: Client = None
else:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logging.info("✅ Supabase client initialized")
    except Exception as e:
        logging.error(f"❌ Failed to initialize Supabase: {e}")
        supabase = None

def get_supabase_client() -> Client:
    """Get Supabase client instance"""
    if supabase is None:
        raise RuntimeError("Supabase not initialized. Check SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables.")
    return supabase
