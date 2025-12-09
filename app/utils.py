"""
Common utility functions for the CTF Manager application.
"""
import logging
from flask import current_app

logger = logging.getLogger(__name__)


def get_ctfd_config():
    """Get CTFd configuration from database settings, with fallback to environment variables.
    
    This function prioritizes database settings over environment variables, allowing
    users to update CTFd configuration through the UI without modifying environment files.
    
    Returns:
        tuple: (ctfd_url, ctfd_api_key) where both are strings or empty strings if not found
    """
    from app.supabase_client import get_supabase_client
    
    supabase = get_supabase_client()
    
    # Default to environment variables
    ctfd_url = current_app.config.get('CTFD_URL', '')
    ctfd_api_key = current_app.config.get('CTFD_API_KEY', '')
    
    # Try to get from database settings (overrides environment variables)
    if supabase:
        try:
            settings_response = supabase.table('settings').select('key, value').in_('key', ['ctfd_url', 'ctfd_api_key']).execute()
            if settings_response.data:
                for setting in settings_response.data:
                    if setting['key'] == 'ctfd_url' and setting['value']:
                        ctfd_url = setting['value']
                    elif setting['key'] == 'ctfd_api_key' and setting['value']:
                        ctfd_api_key = setting['value']
        except Exception as e:
            logger.warning(f"Failed to fetch CTFd config from database: {str(e)}")
    
    return ctfd_url, ctfd_api_key
