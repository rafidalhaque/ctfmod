import os
from supabase import create_client, Client

_supabase_client = None


def get_supabase_client() -> Client:
    """Get or create a Supabase client instance."""
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv('SUPABASE_URL', '')
        key = os.getenv('SUPABASE_KEY', '')
        if url and key:
            _supabase_client = create_client(url, key)
    return _supabase_client


def init_supabase(url: str, key: str) -> Client:
    """Initialize Supabase client with provided credentials."""
    global _supabase_client
    _supabase_client = create_client(url, key)
    return _supabase_client
