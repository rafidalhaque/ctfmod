from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.supabase_client import get_supabase_client
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

settings_bp = Blueprint('settings', __name__)


def convert_datetime_to_iso_with_timezone(datetime_str, timezone_str):
    """Convert a datetime-local string to ISO 8601 format with timezone offset.
    
    Args:
        datetime_str: String in format 'YYYY-MM-DDTHH:MM' from datetime-local input
        timezone_str: IANA timezone string like 'Asia/Dhaka' or 'UTC'
    
    Returns:
        ISO 8601 formatted string with timezone offset, or None if input is invalid
    """
    if not datetime_str:
        return None
    
    try:
        # Parse the datetime-local string (which has no timezone info)
        naive_dt = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M')
        
        # Get the timezone object
        tz = ZoneInfo(timezone_str) if timezone_str else ZoneInfo('UTC')
        
        # Localize the naive datetime to the specified timezone
        localized_dt = naive_dt.replace(tzinfo=tz)
        
        # Return ISO 8601 format with timezone offset
        return localized_dt.isoformat()
    except (ValueError, ZoneInfoNotFoundError):
        # Return the original string if parsing fails
        return datetime_str


@settings_bp.route('/settings')
@login_required
def index():
    """Render the settings page."""
    supabase = get_supabase_client()
    settings = {}
    targets = []
    rounds = []
    categories = []
    difficulties = []
    
    if supabase:
        try:
            # Fetch site settings
            settings_response = supabase.table('settings').select('*').execute()
            if settings_response.data:
                for setting in settings_response.data:
                    settings[setting['key']] = setting['value']
            
            # Parse categories and difficulties from settings
            if settings.get('categories'):
                categories = [cat.strip() for cat in settings['categories'].split(',')]
            if settings.get('difficulties'):
                difficulties = [d.strip() for d in settings['difficulties'].split(',')]
            
            # Fetch targets
            targets_response = supabase.table('targets').select('*').execute()
            targets = targets_response.data if targets_response.data else []
            
            # Fetch rounds and format datetime for display
            try:
                rounds_response = supabase.table('rounds').select('*').execute()
                rounds = rounds_response.data if rounds_response.data else []
                
                # Format datetime for display and input fields
                for round_item in rounds:
                    if round_item.get('start_datetime'):
                        dt_str = round_item['start_datetime']
                        timezone_str = round_item.get('timezone', 'UTC')
                        # Parse and format for display and datetime-local input
                        try:
                            # Parse ISO format datetime
                            dt = datetime.fromisoformat(dt_str)
                            
                            # Convert to the round's timezone for display
                            tz = ZoneInfo(timezone_str)
                            dt_in_tz = dt.astimezone(tz)
                            
                            # Format for display (human readable)
                            round_item['start_datetime_display'] = dt_in_tz.strftime('%Y-%m-%d %H:%M')
                            # Format for datetime-local input (YYYY-MM-DDTHH:MM)
                            round_item['start_datetime_input'] = dt_in_tz.strftime('%Y-%m-%dT%H:%M')
                        except (ValueError, ZoneInfoNotFoundError):
                            # Fallback for legacy datetime formats without timezone
                            if 'T' in dt_str:
                                dt_part = dt_str.split('T')
                                date_part = dt_part[0]
                                time_part = dt_part[1][:5] if len(dt_part) > 1 else '00:00'
                                round_item['start_datetime_display'] = f"{date_part} {time_part}"
                                round_item['start_datetime_input'] = f"{date_part}T{time_part}"
                            else:
                                round_item['start_datetime_display'] = dt_str[:16].replace('T', ' ')
                                round_item['start_datetime_input'] = dt_str[:16]
                    else:
                        round_item['start_datetime_display'] = None
                        round_item['start_datetime_input'] = ''
            except Exception:
                # Table might not exist yet
                rounds = []
            
        except Exception as e:
            flash(f'Error fetching settings: {str(e)}', 'error')
    
    return render_template('settings/index.html', 
                          settings=settings, 
                          targets=targets, 
                          rounds=rounds,
                          categories=categories,
                          difficulties=difficulties)


@settings_bp.route('/settings/update', methods=['POST'])
@login_required
def update_settings():
    """Update site settings."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        
        for key, value in data.items():
            # Upsert setting
            supabase.table('settings').upsert({
                'key': key,
                'value': value
            }, on_conflict='key').execute()
        
        return jsonify({'success': True, 'message': 'Settings updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/targets', methods=['POST'])
@login_required
def update_targets():
    """Update or create challenge targets."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        category = data.get('category')
        difficulty = data.get('difficulty')
        target_count = data.get('target_count', 0)
        round_id = data.get('round_id')
        
        if not category or not difficulty:
            return jsonify({'error': 'Category and difficulty are required'}), 400
        
        target_data = {
            'category': category,
            'difficulty': difficulty,
            'target_count': target_count
        }
        
        # Add round_id if provided, otherwise set to None explicitly
        target_data['round_id'] = round_id if round_id else None
        
        # Check if a target already exists with same category, difficulty, and round_id
        query = supabase.table('targets').select('id').eq('category', category).eq('difficulty', difficulty)
        if round_id:
            query = query.eq('round_id', round_id)
        else:
            query = query.is_('round_id', 'null')
        
        existing = query.execute()
        
        if existing.data:
            # Update existing target
            supabase.table('targets').update({'target_count': target_count}).eq('id', existing.data[0]['id']).execute()
        else:
            # Insert new target
            supabase.table('targets').insert(target_data).execute()
        
        return jsonify({'success': True, 'message': 'Target updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/targets/<int:target_id>', methods=['PUT'])
@login_required
def update_target(target_id):
    """Update an existing challenge target."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        category = data.get('category')
        difficulty = data.get('difficulty')
        target_count = data.get('target_count', 0)
        round_id = data.get('round_id')
        
        if not category or not difficulty:
            return jsonify({'error': 'Category and difficulty are required'}), 400
        
        # First check if the target exists
        existing = supabase.table('targets').select('id').eq('id', target_id).execute()
        if not existing.data:
            return jsonify({'error': 'Target not found'}), 404
        
        update_data = {
            'category': category,
            'difficulty': difficulty,
            'target_count': target_count,
            'round_id': round_id if round_id else None
        }
        
        supabase.table('targets').update(update_data).eq('id', target_id).execute()
        return jsonify({'success': True, 'message': 'Target updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/targets/<int:target_id>', methods=['DELETE'])
@login_required
def delete_target(target_id):
    """Delete a challenge target."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        supabase.table('targets').delete().eq('id', target_id).execute()
        return jsonify({'success': True, 'message': 'Target deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/rounds', methods=['POST'])
@login_required
def create_round():
    """Create a new round."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        name = data.get('name')
        
        if not name:
            return jsonify({'error': 'Round name is required'}), 400
        
        timezone = data.get('timezone', 'UTC')
        round_data = {
            'name': name,
            'description': data.get('description', ''),
            'timezone': timezone
        }
        
        # Add schedule fields if provided - convert to ISO 8601 with timezone offset
        if data.get('start_datetime'):
            round_data['start_datetime'] = convert_datetime_to_iso_with_timezone(
                data.get('start_datetime'), timezone
            )
        
        response = supabase.table('rounds').insert(round_data).execute()
        return jsonify({'success': True, 'data': response.data[0] if response.data else None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/rounds/<int:round_id>', methods=['PUT'])
@login_required
def update_round(round_id):
    """Update an existing round."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        name = data.get('name')
        
        if not name:
            return jsonify({'error': 'Round name is required'}), 400
        
        # First check if the round exists
        existing = supabase.table('rounds').select('id').eq('id', round_id).execute()
        if not existing.data:
            return jsonify({'error': 'Round not found'}), 404
        
        timezone = data.get('timezone', 'UTC')
        update_data = {
            'name': name,
            'description': data.get('description', ''),
            'timezone': timezone
        }
        
        # Add schedule fields - convert to ISO 8601 with timezone offset
        if data.get('start_datetime'):
            update_data['start_datetime'] = convert_datetime_to_iso_with_timezone(
                data.get('start_datetime'), timezone
            )
        else:
            update_data['start_datetime'] = None
        
        supabase.table('rounds').update(update_data).eq('id', round_id).execute()
        return jsonify({'success': True, 'message': 'Round updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/rounds/<int:round_id>', methods=['DELETE'])
@login_required
def delete_round(round_id):
    """Delete a round."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # First, update targets to remove round_id reference
        supabase.table('targets').update({'round_id': None}).eq('round_id', round_id).execute()
        # Then delete the round
        supabase.table('rounds').delete().eq('id', round_id).execute()
        return jsonify({'success': True, 'message': 'Round deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/api-key/generate', methods=['POST'])
@login_required
def generate_api_key():
    """Generate a new stats API key."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Generate a secure random API key
        api_key = 'ctfm_' + secrets.token_urlsafe(32)
        
        # Save to settings
        supabase.table('settings').upsert({
            'key': 'stats_api_key',
            'value': api_key
        }, on_conflict='key').execute()
        
        return jsonify({'success': True, 'api_key': api_key})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/api-key/revoke', methods=['POST'])
@login_required
def revoke_api_key():
    """Revoke the current stats API key."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Delete the API key from settings
        supabase.table('settings').delete().eq('key', 'stats_api_key').execute()
        
        return jsonify({'success': True, 'message': 'API key revoked successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/users')
@login_required
def users_list():
    """List all registered users with their emails."""
    supabase = get_supabase_client()
    users = []
    
    if supabase:
        try:
            # Fetch users from Supabase auth - this requires admin/service key
            # For now, we'll get a list of unique setters from challenges as a fallback
            # and also any users we can get from auth if available
            
            # Get unique setters from challenges
            challenges_response = supabase.table('challenges').select('setter').execute()
            setters = set()
            if challenges_response.data:
                for challenge in challenges_response.data:
                    if challenge.get('setter'):
                        setters.add(challenge['setter'])
            
            # Try to get users from auth.users (requires service key)
            try:
                auth_users = supabase.auth.admin.list_users()
                if auth_users:
                    for user in auth_users:
                        users.append({
                            'id': user.id,
                            'email': user.email,
                            'created_at': str(user.created_at) if user.created_at else None,
                            'last_sign_in_at': str(user.last_sign_in_at) if user.last_sign_in_at else None,
                            'email_confirmed': user.email_confirmed_at is not None,
                            'role': user.user_metadata.get('role', 'user') if user.user_metadata else 'user'
                        })
            except Exception:
                # If we can't access auth.users, use setters as a fallback
                for setter in sorted(setters):
                    users.append({
                        'id': None,
                        'email': setter,
                        'created_at': None,
                        'last_sign_in_at': None,
                        'email_confirmed': None,
                        'role': 'setter'
                    })
                    
        except Exception as e:
            flash(f'Error fetching users: {str(e)}', 'error')
    
    return render_template('settings/users.html', users=users)
