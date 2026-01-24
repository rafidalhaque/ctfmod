from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, send_from_directory, Response
from flask_login import login_required, current_user
from app.supabase_client import get_supabase_client
from app.ctfd_client import CTFdAPIClient, CTFdAPIException
from app.utils import get_ctfd_config
from app.email_queue import email_queue, EmailTask
import secrets
import os
import uuid
import logging
import string
import random
import csv
import io
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__)

# Allowed file extensions for email attachments
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Minimum phone number length for deduplication check (validates meaningful phone numbers)
MIN_PHONE_LENGTH = 7


def allowed_file(filename):
    """Check if a file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image(filename):
    """Check if a file is an allowed image type."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def validate_finalist_fields(data):
    """Validate finalist-specific fields.
    
    Args:
        data: Dictionary with optional keys 'finalist_position' and 'finalist_score_previous_round'
    
    Returns:
        Tuple (is_valid, error_message, validated_data)
        where validated_data is a dict with validated/converted values
    
    Raises:
        None - returns error info instead
    """
    validated = {}
    
    # Validate position if provided
    if 'finalist_position' in data and data['finalist_position']:
        try:
            pos = int(data['finalist_position'])
            if pos < 1:
                return False, 'Finalist position must be a positive integer', None
            validated['finalist_position'] = pos
        except (ValueError, TypeError):
            return False, 'Finalist position must be a valid integer', None
    
    # Validate score if provided
    if 'finalist_score_previous_round' in data and data['finalist_score_previous_round'] is not None:
        try:
            validated['finalist_score_previous_round'] = float(data['finalist_score_previous_round'])
        except (ValueError, TypeError):
            return False, 'Finalist score must be a valid number', None
    
    # Include round_id if provided (no validation needed, DB constraint handles it)
    if 'finalist_round_id' in data and data['finalist_round_id']:
        validated['finalist_round_id'] = data['finalist_round_id']
    
    return True, None, validated


def clear_ctfd_credentials_for_team(supabase, registration_id):
    """Clear CTFd credentials for a team and its members.
    
    This clears:
    - ctfd_team_id and ctfd_team_password from ctfd_team_credentials
    - ctfd_user_id and ctfd_password from ctfd_user_credentials for all team members
    
    Args:
        supabase: Supabase client instance
        registration_id: The team's registration_id (used as the foreign key 
                        in ctfd_team_credentials.team_id and team_members.team_id)
    
    Returns:
        None
    
    Raises:
        Exception: If database operations fail
    
    Note:
        This function updates member credentials individually in a loop.
        For teams with many members, this could result in N+1 queries, but
        it's acceptable since: (1) teams typically don't have hundreds of members,
        (2) this operation is infrequent (only when status changes to finalist).
    """
    try:
        # Clear team credentials (set ctfd_team_id and password to NULL)
        supabase.table('ctfd_team_credentials').update({
            'ctfd_team_id': None,
            'ctfd_team_password': None
        }).eq('team_id', registration_id).execute()
        
        # Get all members of this team
        members_response = supabase.table('team_members').select('id').eq('team_id', registration_id).execute()
        if members_response.data:
            # Clear credentials for each member
            for member in members_response.data:
                supabase.table('ctfd_user_credentials').update({
                    'ctfd_user_id': None,
                    'ctfd_password': None
                }).eq('member_id', member['id']).execute()
        
        logger.info(f'Cleared CTFd credentials for team {registration_id} and its members')
    except Exception as e:
        logger.error(f'Error clearing CTFd credentials for team {registration_id}: {str(e)}')
        raise


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


@settings_bp.route('/settings/ctfd/test', methods=['POST'])
@login_required
def test_ctfd_settings():
    """Test CTFd API connection and functionality."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    # Length of random ID suffix for test challenge name
    TEST_CHALLENGE_ID_LENGTH = 8
    
    try:
        # Get CTFd configuration from database settings
        ctfd_url, ctfd_api_key = get_ctfd_config()
        
        if not ctfd_url or not ctfd_api_key:
            return jsonify({'error': 'CTFd URL and API key are required'}), 400
        
        # Initialize CTFd client
        try:
            client = CTFdAPIClient(ctfd_url, ctfd_api_key)
        except CTFdAPIException as e:
            logger.error(f"CTFd client initialization failed: {e.message}")
            log_entry = {
                'operation_type': 'test_connection',
                'status': 'failed',
                'error_message': f'Configuration error: {e.message}',
                'request_data': {'ctfd_url': ctfd_url},
                'response_data': e.details
            }
            supabase.table('ctfd_operation_logs').insert(log_entry).execute()
            return jsonify({'error': e.message, 'details': e.details}), 400
        
        # Test 1: Create a test challenge
        test_challenge_data = {
            'name': f'_TEST_CHALLENGE_{uuid.uuid4().hex[:TEST_CHALLENGE_ID_LENGTH]}',
            'category': 'Test',
            'description': 'This is a temporary test challenge to verify CTFd API connectivity. It will be deleted automatically.',
            'value': 100,
            'type': 'standard',
            'state': 'hidden'
        }
        
        challenge_id = None
        test_results = {
            'connection': {'status': 'pending', 'message': ''},
            'create_challenge': {'status': 'pending', 'message': ''},
            'cleanup': {'status': 'pending', 'message': ''}
        }
        
        log_entry = {
            'operation_type': 'test_connection',
            'status': 'pending',
            'request_data': {'ctfd_url': ctfd_url, 'test_challenge': test_challenge_data['name']}
        }
        
        try:
            # Step 1: Test connection by creating a challenge
            logger.info("Testing CTFd connection by creating test challenge")
            challenge_result = client.create_challenge(test_challenge_data)
            challenge_id = challenge_result.get('id')
            
            test_results['connection']['status'] = 'success'
            test_results['connection']['message'] = 'Successfully connected to CTFd API'
            
            test_results['create_challenge']['status'] = 'success'
            test_results['create_challenge']['message'] = f'Test challenge created with ID: {challenge_id}'
            test_results['create_challenge']['challenge_id'] = challenge_id
            
            log_entry['ctfd_entity_id'] = challenge_id
            log_entry['response_data'] = challenge_result
            
            # Step 2: Clean up - delete the test challenge
            logger.info(f"Cleaning up test challenge {challenge_id}")
            client.delete_challenge(challenge_id)
            
            test_results['cleanup']['status'] = 'success'
            test_results['cleanup']['message'] = 'Test challenge deleted successfully'
            
            log_entry['status'] = 'success'
            log_entry['error_message'] = None
            
            supabase.table('ctfd_operation_logs').insert(log_entry).execute()
            
            return jsonify({
                'success': True,
                'message': 'CTFd API connection test successful! All operations completed.',
                'results': test_results,
                'ctfd_url': ctfd_url
            })
            
        except CTFdAPIException as e:
            logger.error(f"CTFd API test failed: {e.message}")
            
            # Update test results with error
            if not challenge_id:
                test_results['connection']['status'] = 'failed'
                test_results['connection']['message'] = f'Connection failed: {e.message}'
                test_results['create_challenge']['status'] = 'failed'
                test_results['create_challenge']['message'] = e.message
            else:
                test_results['cleanup']['status'] = 'failed'
                test_results['cleanup']['message'] = f'Cleanup failed: {e.message}'
            
            log_entry['status'] = 'failed'
            log_entry['error_message'] = e.message
            log_entry['response_data'] = e.details
            
            supabase.table('ctfd_operation_logs').insert(log_entry).execute()
            
            return jsonify({
                'error': e.message,
                'error_type': e.error_type.value,
                'results': test_results,
                'details': e.details
            }), 500
            
    except Exception as e:
        logger.error(f"CTFd test error: {str(e)}")
        return jsonify({'error': f'Test failed: {str(e)}'}), 500


@settings_bp.route('/settings/smtp', methods=['POST'])
@login_required
def update_smtp_settings():
    """Update SMTP email settings."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        
        # SMTP settings keys
        smtp_keys = ['smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 
                     'smtp_sender_email', 'smtp_sender_name', 'smtp_use_tls', 'smtp_use_ssl']
        
        for key in smtp_keys:
            if key in data:
                value = data[key]
                # Skip empty password to preserve existing value
                if key == 'smtp_password' and not value:
                    continue
                supabase.table('settings').upsert({
                    'key': key,
                    'value': str(value) if value is not None else ''
                }, on_conflict='key').execute()
        
        return jsonify({'success': True, 'message': 'SMTP settings updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/smtp/test', methods=['POST'])
@login_required
def test_smtp_settings():
    """Test SMTP connection by sending a test email."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        test_email = data.get('test_email')
        
        if not test_email:
            return jsonify({'error': 'Test email address is required'}), 400
        
        # Fetch SMTP settings
        settings_response = supabase.table('settings').select('*').execute()
        settings = {}
        if settings_response.data:
            for setting in settings_response.data:
                settings[setting['key']] = setting['value']
        
        smtp_host = settings.get('smtp_host', '')
        smtp_port = int(settings.get('smtp_port', 587))
        smtp_username = settings.get('smtp_username', '')
        smtp_password = settings.get('smtp_password', '')
        sender_email = settings.get('smtp_sender_email', '')
        sender_name = settings.get('smtp_sender_name', 'CTF Manager')
        use_tls = settings.get('smtp_use_tls', 'true').lower() == 'true'
        use_ssl = settings.get('smtp_use_ssl', 'false').lower() == 'true'
        
        if not smtp_host or not sender_email:
            return jsonify({'error': 'SMTP host and sender email are required'}), 400
        
        # Create test message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'CTF Manager - Test Email'
        msg['From'] = f'{sender_name} <{sender_email}>'
        msg['To'] = test_email
        
        text_content = 'This is a test email from CTF Manager. Your SMTP settings are configured correctly!'
        html_content = '''
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #667eea;">CTF Manager - Test Email</h2>
            <p>This is a test email from CTF Manager.</p>
            <p style="color: #22c55e; font-weight: bold;">✓ Your SMTP settings are configured correctly!</p>
        </body>
        </html>
        '''
        
        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        # Send email
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            if use_tls:
                server.starttls()
        
        if smtp_username and smtp_password:
            server.login(smtp_username, smtp_password)
        
        server.sendmail(sender_email, test_email, msg.as_string())
        server.quit()
        
        return jsonify({'success': True, 'message': f'Test email sent successfully to {test_email}'})
    except smtplib.SMTPAuthenticationError:
        return jsonify({'error': 'SMTP authentication failed. Check username and password.'}), 400
    except smtplib.SMTPConnectError:
        return jsonify({'error': 'Failed to connect to SMTP server. Check host and port.'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to send test email: {str(e)}'}), 500


@settings_bp.route('/settings/email-templates')
@login_required
def email_templates():
    """List all email templates."""
    supabase = get_supabase_client()
    templates = []
    
    if supabase:
        try:
            response = supabase.table('email_templates').select('*').order('name').execute()
            templates = response.data if response.data else []
        except Exception as e:
            flash(f'Error fetching email templates: {str(e)}', 'error')
    
    return render_template('settings/email_templates.html', templates=templates)


@settings_bp.route('/settings/email-templates/list', methods=['GET'])
@login_required
def list_email_templates():
    """Get all email templates as JSON for dropdowns."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        response = supabase.table('email_templates').select('id, name, subject, description').order('name').execute()
        templates = response.data if response.data else []
        return jsonify({'success': True, 'data': templates})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/email-templates', methods=['POST'])
@login_required
def create_email_template():
    """Create a new email template."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        name = data.get('name', '').strip()
        subject = data.get('subject', '').strip()
        body = data.get('body', '').strip()
        description = data.get('description', '').strip()
        
        if not name:
            return jsonify({'error': 'Template name is required'}), 400
        if not subject:
            return jsonify({'error': 'Email subject is required'}), 400
        if not body:
            return jsonify({'error': 'Email body is required'}), 400
        
        template_data = {
            'name': name,
            'subject': subject,
            'body': body,
            'description': description
        }
        
        response = supabase.table('email_templates').insert(template_data).execute()
        return jsonify({'success': True, 'data': response.data[0] if response.data else None})
    except Exception as e:
        error_msg = str(e)
        if 'duplicate key' in error_msg.lower() or 'unique constraint' in error_msg.lower():
            template_name = data.get('name', 'unknown') if 'data' in dir() else 'unknown'
            return jsonify({'error': f'A template with this name already exists'}), 400
        return jsonify({'error': error_msg}), 500


@settings_bp.route('/settings/email-templates/<int:template_id>', methods=['GET'])
@login_required
def get_email_template(template_id):
    """Get a specific email template."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        response = supabase.table('email_templates').select('*').eq('id', template_id).execute()
        if not response.data:
            return jsonify({'error': 'Template not found'}), 404
        return jsonify({'success': True, 'data': response.data[0]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/email-templates/<int:template_id>', methods=['PUT'])
@login_required
def update_email_template(template_id):
    """Update an existing email template."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        name = data.get('name', '').strip()
        subject = data.get('subject', '').strip()
        body = data.get('body', '').strip()
        description = data.get('description', '').strip()
        
        if not name:
            return jsonify({'error': 'Template name is required'}), 400
        if not subject:
            return jsonify({'error': 'Email subject is required'}), 400
        if not body:
            return jsonify({'error': 'Email body is required'}), 400
        
        # Check if template exists
        existing = supabase.table('email_templates').select('id').eq('id', template_id).execute()
        if not existing.data:
            return jsonify({'error': 'Template not found'}), 404
        
        update_data = {
            'name': name,
            'subject': subject,
            'body': body,
            'description': description
        }
        
        supabase.table('email_templates').update(update_data).eq('id', template_id).execute()
        return jsonify({'success': True, 'message': 'Template updated successfully'})
    except Exception as e:
        error_msg = str(e)
        if 'duplicate key' in error_msg.lower() or 'unique constraint' in error_msg.lower():
            return jsonify({'error': 'A template with this name already exists'}), 400
        return jsonify({'error': error_msg}), 500


@settings_bp.route('/settings/email-templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_email_template(template_id):
    """Delete an email template."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        supabase.table('email_templates').delete().eq('id', template_id).execute()
        return jsonify({'success': True, 'message': 'Template deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/email-templates/preview', methods=['POST'])
@login_required
def preview_email_template():
    """Preview an email template with sample variable replacements."""
    try:
        data = request.json
        subject = data.get('subject', '')
        body = data.get('body', '')
        
        # Sample variable values for preview
        sample_variables = {
            'user_name': 'John Doe',
            'user_email': 'john@example.com',
            'user_ctfd_username': 'john_doe',
            'user_ctfd_password': 'SecurePass123',
            'team_name': 'Sample Team',
            'team_ctfd_username': 'sample_team',
            'team_ctfd_password': 'TeamPass456',
            'registration_id': 'REG-12345',
            'event_name': 'Science Fest CTF',
            'site_name': 'CTF Manager',
            'challenge_name': 'Sample Challenge',
            'category': 'Web',
            'difficulty': 'Medium',
            'setter': 'admin',
            'round_name': 'Preliminary',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%H:%M')
        }
        
        # Replace variables in subject and body
        preview_subject = subject
        preview_body = body
        
        for var_name, var_value in sample_variables.items():
            preview_subject = preview_subject.replace('{{' + var_name + '}}', var_value)
            preview_body = preview_body.replace('{{' + var_name + '}}', var_value)
        
        return jsonify({
            'success': True,
            'preview_subject': preview_subject,
            'preview_body': preview_body
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/email-templates/test-send', methods=['POST'])
@login_required
def test_send_email_template():
    """Send a test email using a template to a specific email address."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.image import MIMEImage
    from email import encoders
    import re
    
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        template_id = data.get('template_id')
        test_email = data.get('test_email', '').strip()
        attachment_ids = data.get('attachments', [])  # List of attachment IDs
        
        if not template_id:
            return jsonify({'error': 'Template ID is required'}), 400
        
        if not test_email:
            return jsonify({'error': 'Test email address is required'}), 400
        
        # Basic email validation
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, test_email):
            return jsonify({'error': 'Invalid email address format'}), 400
        
        # Fetch the template
        template_response = supabase.table('email_templates').select('*').eq('id', template_id).execute()
        if not template_response.data:
            return jsonify({'error': 'Template not found'}), 404
        
        template = template_response.data[0]
        
        # Fetch SMTP settings
        settings_response = supabase.table('settings').select('*').execute()
        settings = {}
        if settings_response.data:
            for setting in settings_response.data:
                settings[setting['key']] = setting['value']
        
        smtp_host = settings.get('smtp_host', '')
        smtp_port = int(settings.get('smtp_port', 587))
        smtp_username = settings.get('smtp_username', '')
        smtp_password = settings.get('smtp_password', '')
        sender_email = settings.get('smtp_sender_email', '')
        sender_name = settings.get('smtp_sender_name', 'CTF Manager')
        use_tls = settings.get('smtp_use_tls', 'true').lower() == 'true'
        use_ssl = settings.get('smtp_use_ssl', 'false').lower() == 'true'
        event_name = settings.get('event_name', 'CTF Event')
        site_name = settings.get('site_name', 'CTF Manager')
        
        if not smtp_host or not sender_email:
            return jsonify({'error': 'SMTP settings not configured. Please configure SMTP first.'}), 400
        
        # Sample variable values for test send
        sample_variables = {
            'user_name': 'Test User',
            'user_email': test_email,
            'user_ctfd_username': 'test_user',
            'user_ctfd_password': 'TestPass123',
            'team_name': 'Test Team',
            'team_ctfd_username': 'test_team',
            'team_ctfd_password': 'TeamPass456',
            'registration_id': 'REG-TEST-001',
            'event_name': event_name,
            'site_name': site_name,
            'challenge_name': 'Test Challenge',
            'category': 'Web',
            'difficulty': 'Medium',
            'setter': 'admin',
            'round_name': 'Test Round',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%H:%M')
        }
        
        # Replace variables in template
        subject = template['subject']
        body = template['body']
        
        for var_name, var_value in sample_variables.items():
            subject = subject.replace('{{' + var_name + '}}', str(var_value or ''))
            body = body.replace('{{' + var_name + '}}', str(var_value or ''))
        
        # Create message with mixed type to support both alternative content and attachments
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = f'{sender_name} <{sender_email}>'
        msg['To'] = test_email
        
        # Create alternative part for text and HTML
        msg_alternative = MIMEMultipart('alternative')
        
        # Create related part for HTML with inline images
        msg_related = MIMEMultipart('related')
        
        # Plain text version - strip HTML tags
        text_content = body.replace('<br>', '\n').replace('<p>', '\n').replace('</p>', '\n')
        text_content = re.sub('<[^<]+?>', '', text_content)
        
        msg_alternative.attach(MIMEText(text_content, 'plain'))
        
        # Process inline images in body (replace image URLs with cid references)
        inline_images = []
        upload_folder = current_app.config.get('UPLOAD_FOLDER', '')
        
        # Find and process inline images in the template body
        # Look for patterns like src="/uploads/email_attachments/..." or src="{{image:filename}}"
        img_pattern = r'src=["\'](?:/uploads/email_attachments/|{{image:)([^"\']+)["\']'
        matches = re.findall(img_pattern, body)
        
        for i, match in enumerate(matches):
            filename = match.rstrip('}}')
            file_path = os.path.join(upload_folder, secure_filename(filename))
            
            if os.path.exists(file_path) and allowed_image(filename):
                cid = f'image{i}'
                # Replace the src with cid reference
                body = re.sub(
                    r'src=["\'](?:/uploads/email_attachments/|{{image:)' + re.escape(match) + r'["\']',
                    f'src="cid:{cid}"',
                    body
                )
                inline_images.append((file_path, cid, filename))
        
        # Attach HTML content
        msg_related.attach(MIMEText(body, 'html'))
        
        # Attach inline images
        for file_path, cid, filename in inline_images:
            with open(file_path, 'rb') as img_file:
                img_data = img_file.read()
                ext = filename.rsplit('.', 1)[1].lower()
                mime_subtype = 'jpeg' if ext == 'jpg' else ext
                img = MIMEImage(img_data, _subtype=mime_subtype)
                img.add_header('Content-ID', f'<{cid}>')
                img.add_header('Content-Disposition', 'inline', filename=filename)
                msg_related.attach(img)
        
        msg_alternative.attach(msg_related)
        msg.attach(msg_alternative)
        
        # Fetch and attach files from attachment_ids
        if attachment_ids:
            attachments_response = supabase.table('email_attachments').select('*').in_('id', attachment_ids).execute()
            attachments = attachments_response.data if attachments_response.data else []
            
            for attachment in attachments:
                file_path = os.path.join(upload_folder, attachment['stored_filename'])
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename="{attachment["original_filename"]}"'
                        )
                        msg.attach(part)
        
        # Send email
        server = None
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
                if use_tls:
                    server.starttls()
            
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            
            server.sendmail(sender_email, test_email, msg.as_string())
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
        
        return jsonify({
            'success': True,
            'message': f'Test email sent successfully to {test_email}'
        })
        
    except smtplib.SMTPAuthenticationError:
        return jsonify({'error': 'SMTP authentication failed. Check username and password.'}), 400
    except smtplib.SMTPConnectError:
        return jsonify({'error': 'Failed to connect to SMTP server. Check host and port.'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to send test email: {str(e)}'}), 500


@settings_bp.route('/settings/email-attachments', methods=['GET'])
@login_required
def list_email_attachments():
    """List all email attachments."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        response = supabase.table('email_attachments').select('*').order('created_at', desc=True).execute()
        attachments = response.data if response.data else []
        return jsonify({'success': True, 'data': attachments})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/email-attachments/upload', methods=['POST'])
@login_required
def upload_email_attachment():
    """Upload a file attachment for email templates."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
        
        # Generate unique filename
        original_filename = secure_filename(file.filename)
        ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
        stored_filename = f'{uuid.uuid4().hex}.{ext}'
        
        # Save file
        upload_folder = current_app.config.get('UPLOAD_FOLDER', '')
        file_path = os.path.join(upload_folder, stored_filename)
        file.save(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Determine if it's an image
        is_image = allowed_image(original_filename)
        
        # Save to database
        attachment_data = {
            'original_filename': original_filename,
            'stored_filename': stored_filename,
            'file_size': file_size,
            'mime_type': file.content_type or 'application/octet-stream',
            'is_image': is_image
        }
        
        response = supabase.table('email_attachments').insert(attachment_data).execute()
        
        if response.data:
            attachment = response.data[0]
            # Add URL for accessing the file
            attachment['url'] = url_for('settings.serve_email_attachment', filename=stored_filename, _external=True)
            return jsonify({'success': True, 'data': attachment})
        else:
            return jsonify({'error': 'Failed to save attachment info'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/email-attachments/<int:attachment_id>', methods=['DELETE'])
@login_required
def delete_email_attachment(attachment_id):
    """Delete an email attachment."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Get attachment info
        response = supabase.table('email_attachments').select('*').eq('id', attachment_id).execute()
        if not response.data:
            return jsonify({'error': 'Attachment not found'}), 404
        
        attachment = response.data[0]
        
        # Delete file from disk
        upload_folder = current_app.config.get('UPLOAD_FOLDER', '')
        file_path = os.path.join(upload_folder, attachment['stored_filename'])
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Delete from database
        supabase.table('email_attachments').delete().eq('id', attachment_id).execute()
        
        return jsonify({'success': True, 'message': 'Attachment deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/uploads/email_attachments/<filename>')
@login_required
def serve_email_attachment(filename):
    """Serve an uploaded email attachment."""
    upload_folder = current_app.config.get('UPLOAD_FOLDER', '')
    return send_from_directory(upload_folder, filename)


@settings_bp.route('/settings/email-templates/bulk-send', methods=['POST'])
@login_required
def bulk_send_email():
    """Send bulk emails to participants using a template via background task queue."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        template_id = data.get('template_id')
        include_team_captains = data.get('include_team_captains', False)
        attachment_ids = data.get('attachments', [])  # List of attachment IDs
        status_filter = data.get('status_filter', [])  # List of statuses to filter by (empty = all)
        
        # Validate and parse delay_seconds
        try:
            delay_seconds = int(data.get('delay_seconds', 0))
            if delay_seconds < 0:
                return jsonify({'error': 'Delay seconds must be non-negative'}), 400
            if delay_seconds > 3600:
                return jsonify({'error': 'Delay seconds cannot exceed 3600 (1 hour)'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid delay_seconds value. Must be a non-negative integer.'}), 400
        
        if not template_id:
            return jsonify({'error': 'Template ID is required'}), 400
        
        # Fetch the template
        template_response = supabase.table('email_templates').select('*').eq('id', template_id).execute()
        if not template_response.data:
            return jsonify({'error': 'Template not found'}), 404
        
        template = template_response.data[0]
        
        # Fetch SMTP settings
        settings_response = supabase.table('settings').select('*').execute()
        settings = {}
        if settings_response.data:
            for setting in settings_response.data:
                settings[setting['key']] = setting['value']
        
        smtp_host = settings.get('smtp_host', '')
        smtp_port = int(settings.get('smtp_port', 587))
        smtp_username = settings.get('smtp_username', '')
        smtp_password = settings.get('smtp_password', '')
        sender_email = settings.get('smtp_sender_email', '')
        sender_name = settings.get('smtp_sender_name', 'CTF Manager')
        use_tls = settings.get('smtp_use_tls', 'true').lower() == 'true'
        use_ssl = settings.get('smtp_use_ssl', 'false').lower() == 'true'
        event_name = settings.get('event_name', 'CTF Event')
        site_name = settings.get('site_name', 'CTF Manager')
        
        if not smtp_host or not sender_email:
            return jsonify({'error': 'SMTP settings not configured. Please configure SMTP first.'}), 400
        
        # Fetch all team members with their credentials
        members_response = supabase.table('team_members').select('*').execute()
        members = members_response.data if members_response.data else []
        
        # Fetch teams for team name lookup, optionally filtered by status
        teams_response = supabase.table('teams').select('*').execute()
        all_teams = teams_response.data or []
        
        # Filter teams by status if status_filter is provided
        if status_filter and len(status_filter) > 0:
            filtered_teams = [team for team in all_teams if team.get('status') in status_filter]
        else:
            filtered_teams = all_teams
        
        # Use registration_id as key since team_members.team_id references teams.registration_id
        teams = {team['registration_id']: team for team in filtered_teams if team.get('registration_id')}
        
        # Fetch team credentials (keyed by team_id which is registration_id)
        team_creds_response = supabase.table('ctfd_team_credentials').select('*').execute()
        team_credentials = {cred['team_id']: cred for cred in (team_creds_response.data or [])}
        
        # Fetch user credentials
        user_creds_response = supabase.table('ctfd_user_credentials').select('*').execute()
        user_credentials = {cred['member_id']: cred for cred in (user_creds_response.data or [])}
        
        # Prepare recipients - only include members from filtered teams
        # Use a dict keyed by email to prevent duplicates (same email receiving multiple emails)
        recipients_by_email = {}
        for member in members:
            email = member.get('email')
            if email:
                # Normalize email to lowercase for deduplication
                email_lower = email.lower().strip()
                
                # Skip if we already have this email
                if email_lower in recipients_by_email:
                    continue
                
                team_id = member.get('team_id')  # This references teams.registration_id
                # Only include if team is in the filtered list
                if team_id not in teams:
                    continue
                    
                team = teams.get(team_id, {})
                team_cred = team_credentials.get(team_id, {})
                user_cred = user_credentials.get(member.get('id'), {})
                
                recipients_by_email[email_lower] = {
                    'email': email,
                    'user_name': member.get('name', ''),
                    'user_email': email,
                    'user_ctfd_username': user_cred.get('ctfd_username', ''),
                    'user_ctfd_password': user_cred.get('ctfd_password', ''),
                    'team_name': team.get('team_name', ''),
                    'team_db_id': team.get('id'),
                    'registration_id': str(team_id) if team_id else '',
                    'team_ctfd_username': team_cred.get('ctfd_team_username', ''),
                    'team_ctfd_password': team_cred.get('ctfd_team_password', '')
                }
        
        # Add team captains if requested (from filtered teams only)
        if include_team_captains:
            for registration_id, team in teams.items():
                captain_email = team.get('captain_email')
                if captain_email:
                    captain_email_lower = captain_email.lower().strip()
                    team_cred = team_credentials.get(registration_id, {})
                    # Check if captain email is not already in recipients
                    if captain_email_lower not in recipients_by_email:
                        recipients_by_email[captain_email_lower] = {
                            'email': captain_email,
                            'user_name': team.get('captain_name', ''),
                            'user_email': captain_email,
                            'user_ctfd_username': '',
                            'user_ctfd_password': '',
                            'team_name': team.get('team_name', ''),
                            'team_db_id': team.get('id'),
                            'registration_id': str(registration_id) if registration_id else '',
                            'team_ctfd_username': team_cred.get('ctfd_team_username', ''),
                            'team_ctfd_password': team_cred.get('ctfd_team_password', '')
                        }
        
        # Convert recipients dict back to a list
        recipients = list(recipients_by_email.values())
        
        if not recipients:
            return jsonify({'error': 'No recipients found with valid email addresses'}), 400
        
        # Fetch attachments if provided
        attachments = []
        upload_folder = current_app.config.get('UPLOAD_FOLDER', '')
        if attachment_ids:
            attachments_response = supabase.table('email_attachments').select('*').in_('id', attachment_ids).execute()
            attachments = attachments_response.data if attachments_response.data else []
        
        # Prepare SMTP settings for the task
        smtp_settings = {
            'host': smtp_host,
            'port': smtp_port,
            'username': smtp_username,
            'password': smtp_password,
            'sender_email': sender_email,
            'sender_name': sender_name,
            'use_tls': use_tls,
            'use_ssl': use_ssl,
            'event_name': event_name,
            'site_name': site_name
        }
        
        # Prepare template data
        template_data = {
            'subject': template['subject'],
            'body': template['body']
        }
        
        # Create email task
        task_id = str(uuid.uuid4())
        task = EmailTask(
            task_id=task_id,
            template_id=template_id,
            template_name=template.get('name', ''),
            recipients=recipients,
            smtp_settings=smtp_settings,
            template_data=template_data,
            attachments=attachments,
            upload_folder=upload_folder,
            delay_seconds=delay_seconds
        )
        
        # Set supabase client for the queue
        email_queue.set_supabase_client(supabase)
        
        # Add task to queue
        email_queue.add_task(task)
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'total': len(recipients),
            'delay_seconds': delay_seconds,
            'message': f'Bulk email task queued with {len(recipients)} recipients. Delay: {delay_seconds}s between emails.'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to queue bulk emails: {str(e)}'}), 500


@settings_bp.route('/settings/email-tasks/<task_id>/status', methods=['GET'])
@login_required
def get_email_task_status(task_id):
    """Get the status of a background email task."""
    status = email_queue.get_task_status(task_id)
    
    if not status:
        return jsonify({'error': 'Task not found'}), 404
    
    return jsonify({
        'success': True,
        'data': status
    })


@settings_bp.route('/settings/teams/<int:team_id>/send-email', methods=['POST'])
@login_required
def send_email_to_team(team_id):
    """Send email to all members of a single team using a template."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.image import MIMEImage
    from email import encoders
    import re
    
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        template_id = data.get('template_id')
        include_team_captain = data.get('include_team_captain', False)
        attachment_ids = data.get('attachments', [])
        
        if not template_id:
            return jsonify({'error': 'Template ID is required'}), 400
        
        # Fetch the team
        team_response = supabase.table('teams').select('*').eq('id', team_id).execute()
        if not team_response.data:
            return jsonify({'error': 'Team not found'}), 404
        
        team = team_response.data[0]
        registration_id = team.get('registration_id')
        
        # Fetch the template
        template_response = supabase.table('email_templates').select('*').eq('id', template_id).execute()
        if not template_response.data:
            return jsonify({'error': 'Template not found'}), 404
        
        template = template_response.data[0]
        
        # Fetch SMTP settings
        settings_response = supabase.table('settings').select('*').execute()
        settings = {}
        if settings_response.data:
            for setting in settings_response.data:
                settings[setting['key']] = setting['value']
        
        smtp_host = settings.get('smtp_host', '')
        smtp_port = int(settings.get('smtp_port', 587))
        smtp_username = settings.get('smtp_username', '')
        smtp_password = settings.get('smtp_password', '')
        sender_email = settings.get('smtp_sender_email', '')
        sender_name = settings.get('smtp_sender_name', 'CTF Manager')
        use_tls = settings.get('smtp_use_tls', 'true').lower() == 'true'
        use_ssl = settings.get('smtp_use_ssl', 'false').lower() == 'true'
        event_name = settings.get('event_name', 'CTF Event')
        site_name = settings.get('site_name', 'CTF Manager')
        
        if not smtp_host or not sender_email:
            return jsonify({'error': 'SMTP settings not configured. Please configure SMTP first.'}), 400
        
        # Fetch team members
        members = []
        if registration_id:
            members_response = supabase.table('team_members').select('*').eq('team_id', registration_id).execute()
            members = members_response.data if members_response.data else []
        
        # Fetch team credentials
        team_cred = {}
        if registration_id:
            team_creds_response = supabase.table('ctfd_team_credentials').select('*').eq('team_id', registration_id).execute()
            if team_creds_response.data:
                team_cred = team_creds_response.data[0]
        
        # Fetch user credentials
        user_creds_response = supabase.table('ctfd_user_credentials').select('*').execute()
        user_credentials = {cred['member_id']: cred for cred in (user_creds_response.data or [])}
        
        # Prepare recipients
        recipients_by_email = {}
        for member in members:
            email = member.get('email')
            if email:
                email_lower = email.lower().strip()
                if email_lower in recipients_by_email:
                    continue
                
                user_cred = user_credentials.get(member.get('id'), {})
                
                recipients_by_email[email_lower] = {
                    'email': email,
                    'user_name': member.get('name', ''),
                    'user_email': email,
                    'user_ctfd_username': user_cred.get('ctfd_username', ''),
                    'user_ctfd_password': user_cred.get('ctfd_password', ''),
                    'team_name': team.get('team_name', ''),
                    'team_db_id': team.get('id'),
                    'registration_id': str(registration_id) if registration_id else '',
                    'team_ctfd_username': team_cred.get('ctfd_team_username', ''),
                    'team_ctfd_password': team_cred.get('ctfd_team_password', '')
                }
        
        # Add team captain if requested
        if include_team_captain:
            captain_email = team.get('captain_email')
            if captain_email:
                captain_email_lower = captain_email.lower().strip()
                if captain_email_lower not in recipients_by_email:
                    recipients_by_email[captain_email_lower] = {
                        'email': captain_email,
                        'user_name': team.get('captain_name', ''),
                        'user_email': captain_email,
                        'user_ctfd_username': '',
                        'user_ctfd_password': '',
                        'team_name': team.get('team_name', ''),
                        'team_db_id': team.get('id'),
                        'registration_id': str(registration_id) if registration_id else '',
                        'team_ctfd_username': team_cred.get('ctfd_team_username', ''),
                        'team_ctfd_password': team_cred.get('ctfd_team_password', '')
                    }
        
        recipients = list(recipients_by_email.values())
        
        if not recipients:
            return jsonify({'error': 'No recipients found with valid email addresses for this team'}), 400
        
        # Fetch attachments if provided
        attachments = []
        upload_folder = current_app.config.get('UPLOAD_FOLDER', '')
        if attachment_ids:
            attachments_response = supabase.table('email_attachments').select('*').in_('id', attachment_ids).execute()
            attachments = attachments_response.data if attachments_response.data else []
        
        # Connect to SMTP server and send emails
        server = None
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
                if use_tls:
                    server.starttls()
            
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            
            sent_count = 0
            failed_count = 0
            audit_logs = []
            
            for recipient in recipients:
                error_message = None
                try:
                    # Replace variables in template
                    subject = template['subject']
                    body = template['body']
                    
                    variables = {
                        'user_name': recipient['user_name'],
                        'user_email': recipient['user_email'],
                        'user_ctfd_username': recipient['user_ctfd_username'],
                        'user_ctfd_password': recipient['user_ctfd_password'],
                        'team_name': recipient['team_name'],
                        'registration_id': recipient.get('registration_id', ''),
                        'team_ctfd_username': recipient['team_ctfd_username'],
                        'team_ctfd_password': recipient['team_ctfd_password'],
                        'event_name': event_name,
                        'site_name': site_name,
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'time': datetime.now().strftime('%H:%M')
                    }
                    
                    for var_name, var_value in variables.items():
                        subject = subject.replace('{{' + var_name + '}}', str(var_value or ''))
                        body = body.replace('{{' + var_name + '}}', str(var_value or ''))
                    
                    # Create message
                    msg = MIMEMultipart('mixed')
                    msg['Subject'] = subject
                    msg['From'] = f'{sender_name} <{sender_email}>'
                    msg['To'] = recipient['email']
                    
                    msg_alternative = MIMEMultipart('alternative')
                    msg_related = MIMEMultipart('related')
                    
                    # Plain text version
                    text_content = body.replace('<br>', '\n').replace('<p>', '\n').replace('</p>', '\n')
                    text_content = re.sub('<[^<]+?>', '', text_content)
                    
                    msg_alternative.attach(MIMEText(text_content, 'plain'))
                    
                    # Process inline images
                    inline_images = []
                    img_pattern = r'src=["\'](?:/uploads/email_attachments/|\{\{cid:)([^"\']+)["\']'
                    matches = re.findall(img_pattern, body)
                    
                    for i, match in enumerate(matches):
                        filename = match.rstrip('}}')
                        file_path = os.path.join(upload_folder, secure_filename(filename))
                        
                        if os.path.exists(file_path) and allowed_image(filename):
                            cid = f'image{i}'
                            body = re.sub(
                                r'src=["\'](?:/uploads/email_attachments/|\{\{cid:)' + re.escape(match) + r'["\']',
                                f'src="cid:{cid}"',
                                body
                            )
                            inline_images.append((file_path, cid, filename))
                    
                    msg_related.attach(MIMEText(body, 'html'))
                    
                    for file_path, cid, filename in inline_images:
                        with open(file_path, 'rb') as img_file:
                            img_data = img_file.read()
                            ext = filename.rsplit('.', 1)[1].lower()
                            mime_subtype = 'jpeg' if ext == 'jpg' else ext
                            img = MIMEImage(img_data, _subtype=mime_subtype)
                            img.add_header('Content-ID', f'<{cid}>')
                            img.add_header('Content-Disposition', 'inline', filename=filename)
                            msg_related.attach(img)
                    
                    msg_alternative.attach(msg_related)
                    msg.attach(msg_alternative)
                    
                    # Attach file attachments
                    for attachment in attachments:
                        file_path = os.path.join(upload_folder, attachment['stored_filename'])
                        if os.path.exists(file_path):
                            with open(file_path, 'rb') as f:
                                part = MIMEBase('application', 'octet-stream')
                                part.set_payload(f.read())
                                encoders.encode_base64(part)
                                part.add_header(
                                    'Content-Disposition',
                                    f'attachment; filename="{attachment["original_filename"]}"'
                                )
                                msg.attach(part)
                    
                    server.sendmail(sender_email, recipient['email'], msg.as_string())
                    sent_count += 1
                    
                    audit_logs.append({
                        'template_id': template_id,
                        'template_name': template.get('name', ''),
                        'recipient_email': recipient['email'],
                        'recipient_name': recipient['user_name'],
                        'team_id': recipient.get('team_db_id'),
                        'team_name': recipient['team_name'],
                        'status': 'sent',
                        'error_message': None
                    })
                except Exception as e:
                    failed_count += 1
                    error_message = str(e)
                    
                    audit_logs.append({
                        'template_id': template_id,
                        'template_name': template.get('name', ''),
                        'recipient_email': recipient['email'],
                        'recipient_name': recipient['user_name'],
                        'team_id': recipient.get('team_db_id'),
                        'team_name': recipient['team_name'],
                        'status': 'failed',
                        'error_message': error_message
                    })
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
        
        # Insert audit logs
        if audit_logs:
            try:
                supabase.table('email_audit_logs').insert(audit_logs).execute()
            except Exception as log_error:
                logger.warning("Failed to save email audit logs: %s", log_error)
        
        return jsonify({
            'success': True,
            'sent': sent_count,
            'failed': failed_count,
            'total': len(recipients),
            'message': f'Sent {sent_count} emails to {team.get("team_name", "team")}, {failed_count} failed'
        })
        
    except smtplib.SMTPAuthenticationError:
        return jsonify({'error': 'SMTP authentication failed. Check username and password.'}), 400
    except smtplib.SMTPConnectError:
        return jsonify({'error': 'Failed to connect to SMTP server. Check host and port.'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to send emails to team: {str(e)}'}), 500


@settings_bp.route('/settings/teams')
@login_required
def teams_list():
    """List all teams with their credentials with pagination support."""
    supabase = get_supabase_client()
    teams = []
    total_count = 0
    status_counts = {}
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '', type=str).strip()
    status_filter = request.args.get('status', '', type=str).strip()
    
    # Ensure valid values
    page = max(1, page)
    per_page = min(max(10, per_page), 100)  # Between 10 and 100
    
    if supabase:
        try:
            # Get status counts for teams
            valid_statuses = ['pending', 'approved', 'rejected', 'waitlisted', 'cancelled', 'finalist']
            for status in valid_statuses:
                response = supabase.table('teams').select('id', count='exact').eq('status', status).execute()
                if hasattr(response, 'count') and response.count is not None:
                    status_counts[status] = response.count
                elif response.data:
                    status_counts[status] = len(response.data)
                else:
                    status_counts[status] = 0
            
            # Build base query
            query = supabase.table('teams').select('*', count='exact')
            
            # Apply search filter
            # For text fields use ilike, for registration_id (BIGINT) check if search is numeric
            if search:
                # Check if search term is numeric (for registration_id search)
                if search.isdigit():
                    # Search by registration_id (exact match) OR text fields
                    query = query.or_(f'registration_id.eq.{search},team_name.ilike.%{search}%,captain_name.ilike.%{search}%,captain_email.ilike.%{search}%')
                else:
                    # Search only text fields
                    query = query.or_(f'team_name.ilike.%{search}%,captain_name.ilike.%{search}%,captain_email.ilike.%{search}%')
            
            # Apply status filter
            if status_filter:
                query = query.eq('status', status_filter)
            
            # Get total count first
            count_response = query.execute()
            total_count = count_response.count if hasattr(count_response, 'count') and count_response.count else len(count_response.data) if count_response.data else 0
            
            # Apply pagination
            offset = (page - 1) * per_page
            teams_response = query.order('team_name').range(offset, offset + per_page - 1).execute()
            teams = teams_response.data if teams_response.data else []
            
            # Fetch team credentials and attach to teams
            for team in teams:
                # Get team credentials (using registration_id as foreign key)
                registration_id = team.get('registration_id')
                if registration_id:
                    creds_response = supabase.table('ctfd_team_credentials').select('*').eq('team_id', registration_id).execute()
                    team['credentials'] = creds_response.data[0] if creds_response.data else None
                    
                    # Get member count (team_members.team_id references teams.registration_id)
                    members_response = supabase.table('team_members').select('id', count='exact').eq('team_id', registration_id).execute()
                    team['member_count'] = members_response.count if hasattr(members_response, 'count') else len(members_response.data) if members_response.data else 0
                else:
                    team['credentials'] = None
                    team['member_count'] = 0
                
        except Exception as e:
            flash(f'Error fetching teams: {str(e)}', 'error')
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    return render_template('settings/teams.html', 
                          teams=teams,
                          page=page,
                          per_page=per_page,
                          total_count=total_count,
                          total_pages=total_pages,
                          search=search,
                          status_filter=status_filter,
                          status_counts=status_counts)


@settings_bp.route('/settings/teams/export-csv')
@login_required
def export_teams_csv():
    """Export teams and participants data as CSV.
    
    CSV format (one member per line):
    Position, Team ID, Team Name, Total Members, Captain Name, 
    Member's Name, Member's Class, Member's Institution, Member's Email, Member's Phone, T-Shirt Size
    
    Query parameters:
    - status: Filter by team status (optional)
    - columns: Selected columns to export (optional, repeatable)
    """
    supabase = get_supabase_client()
    
    if not supabase:
        flash('Database not configured', 'error')
        return redirect(url_for('settings.teams_list'))
    
    try:
        # Get status filter from query params
        status_filter = request.args.get('status', '', type=str).strip()
        
        # Get selected columns from query params (can be multiple)
        selected_columns = request.args.getlist('columns')
        
        # Define column mappings (internal key -> display name)
        column_map = {
            'position': 'Position',
            'team_id': 'Team ID',
            'team_name': 'Team Name',
            'total_members': 'Total Members',
            'captain_name': 'Captain Name',
            'member_name': 'Member Name',
            'member_class': 'Member Class',
            'member_institution': 'Member Institution',
            'member_email': 'Member Email',
            'member_phone': 'Member Phone',
            't_shirt_size': 'T-Shirt Size'
        }
        
        # If no columns selected, use all columns
        if not selected_columns:
            selected_columns = list(column_map.keys())
        
        # Build query for teams
        query = supabase.table('teams').select('*')
        
        # Apply status filter if provided
        if status_filter:
            query = query.eq('status', status_filter)
        
        # Order by team_name for consistent ordering
        query = query.order('team_name')
        
        # Get all teams
        teams_response = query.execute()
        teams = teams_response.data if teams_response.data else []
        
        # Sort teams: those with finalist_position first (sorted by position), then others
        teams_with_position = [t for t in teams if t.get('finalist_position') is not None]
        teams_without_position = [t for t in teams if t.get('finalist_position') is None]
        
        # Sort teams with position by their finalist_position
        teams_with_position.sort(key=lambda t: t.get('finalist_position'))
        
        # Combine: finalist teams first, then others
        sorted_teams = teams_with_position + teams_without_position
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header with selected columns only
        header = [column_map[col] for col in selected_columns if col in column_map]
        writer.writerow(header)
        
        # Track position for teams without finalist_position
        # Start from max finalist_position + 1, or 1 if no finalist teams
        max_finalist_position = max([t.get('finalist_position') for t in teams_with_position], default=0)
        next_sequential_position = max_finalist_position + 1
        
        # Process each team
        for team in sorted_teams:
            registration_id = team.get('registration_id')
            team_name = team.get('team_name', '')
            captain_name = team.get('captain_name', '')
            finalist_position = team.get('finalist_position')
            
            # Use finalist_position if available, otherwise use sequential number
            if finalist_position:
                position = finalist_position
            else:
                position = next_sequential_position
                next_sequential_position += 1
            
            # Get team members
            if registration_id:
                members_response = supabase.table('team_members').select('*').eq('team_id', registration_id).order('id').execute()
                members = members_response.data if members_response.data else []
            else:
                members = []
            
            total_members = len(members)
            
            # Build row data dictionary
            def build_row_data(member_data=None):
                row_data = {
                    'position': position,
                    'team_id': registration_id or '',
                    'team_name': team_name,
                    'total_members': total_members,
                    'captain_name': captain_name,
                    'member_name': member_data.get('name', '') if member_data else '',
                    'member_class': member_data.get('class', '') if member_data else '',
                    'member_institution': member_data.get('institution', '') if member_data else '',
                    'member_email': member_data.get('email', '') if member_data else '',
                    'member_phone': member_data.get('phone', '') if member_data else '',
                    't_shirt_size': member_data.get('t_shirt_size', '') if member_data else ''
                }
                # Return only selected columns in the correct order
                return [row_data[col] for col in selected_columns if col in row_data]
            
            # If team has no members, write one line with team info only
            if not members:
                writer.writerow(build_row_data())
            else:
                # Write one line per member
                for member in members:
                    writer.writerow(build_row_data(member))
        
        # Prepare response
        output.seek(0)
        
        # Generate filename with status filter if provided
        filename = f'teams_export'
        if status_filter:
            filename += f'_{status_filter}'
        filename += f'_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
        
    except Exception as e:
        logger.error(f'Error exporting teams CSV: {str(e)}')
        flash(f'Error exporting teams: {str(e)}', 'error')
        return redirect(url_for('settings.teams_list'))


@settings_bp.route('/settings/teams/<int:team_id>')
@login_required
def team_detail(team_id):
    """View team details with members and credentials."""
    supabase = get_supabase_client()
    team = None
    members = []
    team_credentials = None
    
    if supabase:
        try:
            # Fetch team
            team_response = supabase.table('teams').select('*').eq('id', team_id).execute()
            if team_response.data:
                team = team_response.data[0]
            else:
                flash('Team not found', 'error')
                return redirect(url_for('settings.teams_list'))
            
            # Fetch team credentials (using registration_id as foreign key)
            registration_id = team.get('registration_id')
            if registration_id:
                creds_response = supabase.table('ctfd_team_credentials').select('*').eq('team_id', registration_id).execute()
                team_credentials = creds_response.data[0] if creds_response.data else None
                
                # Fetch team members with their credentials (team_members.team_id references teams.registration_id)
                members_response = supabase.table('team_members').select('*').eq('team_id', registration_id).execute()
                members = members_response.data if members_response.data else []
            else:
                team_credentials = None
                members = []
            
            # Attach user credentials to each member
            for member in members:
                user_creds_response = supabase.table('ctfd_user_credentials').select('*').eq('member_id', member['id']).execute()
                member['credentials'] = user_creds_response.data[0] if user_creds_response.data else None
            
            # Fetch finalist round information if team is finalist
            if team.get('is_finalist') and team.get('finalist_round_id'):
                round_response = supabase.table('rounds').select('name').eq('id', team['finalist_round_id']).execute()
                if round_response.data:
                    team['finalist_round_name'] = round_response.data[0]['name']
                
        except Exception as e:
            flash(f'Error fetching team details: {str(e)}', 'error')
    
    return render_template('settings/team_detail.html', team=team, members=members, team_credentials=team_credentials)


@settings_bp.route('/settings/participants')
@login_required
def participants_list():
    """List all participants with their credentials with pagination support."""
    supabase = get_supabase_client()
    participants = []
    total_count = 0
    status_counts = {}
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '', type=str).strip()
    
    # Ensure valid values
    page = max(1, page)
    per_page = min(max(10, per_page), 100)  # Between 10 and 100
    
    if supabase:
        try:
            # Get team names lookup first (for efficiency) with status
            teams_response = supabase.table('teams').select('id, registration_id, team_name, status').execute()
            teams_by_registration_id = {}
            if teams_response.data:
                for team in teams_response.data:
                    if team.get('registration_id'):
                        teams_by_registration_id[team['registration_id']] = {
                            'id': team['id'],
                            'team_name': team['team_name'],
                            'status': team.get('status', 'pending')
                        }
            
            # Calculate participant counts by team status
            all_members_response = supabase.table('team_members').select('id, team_id').execute()
            all_members = all_members_response.data if all_members_response.data else []
            
            valid_statuses = ['pending', 'approved', 'rejected', 'waitlisted', 'cancelled', 'finalist']
            for status in valid_statuses:
                status_counts[status] = 0
            
            for member in all_members:
                team_id = member.get('team_id')
                if team_id and team_id in teams_by_registration_id:
                    team_status = teams_by_registration_id[team_id].get('status', 'pending')
                    if team_status in status_counts:
                        status_counts[team_status] += 1
            
            # Build base query for participants
            query = supabase.table('team_members').select('*', count='exact')
            
            # Apply search filter
            if search:
                query = query.or_(f'name.ilike.%{search}%,email.ilike.%{search}%,institution.ilike.%{search}%')
            
            # Get total count first
            count_response = query.execute()
            total_count = count_response.count if hasattr(count_response, 'count') and count_response.count else len(count_response.data) if count_response.data else 0
            
            # Apply pagination
            offset = (page - 1) * per_page
            members_response = query.order('name').range(offset, offset + per_page - 1).execute()
            participants = members_response.data if members_response.data else []
            
            for participant in participants:
                # Get team name and id (team_members.team_id references teams.registration_id)
                team_id = participant.get('team_id')
                if team_id and team_id in teams_by_registration_id:
                    participant['team_name'] = teams_by_registration_id[team_id]['team_name']
                    participant['team_db_id'] = teams_by_registration_id[team_id]['id']
                else:
                    participant['team_name'] = 'No Team'
                    participant['team_db_id'] = None
                
                # Get user credentials
                creds_response = supabase.table('ctfd_user_credentials').select('*').eq('member_id', participant['id']).execute()
                participant['credentials'] = creds_response.data[0] if creds_response.data else None
                
        except Exception as e:
            flash(f'Error fetching participants: {str(e)}', 'error')
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    return render_template('settings/participants.html', 
                          participants=participants,
                          page=page,
                          per_page=per_page,
                          total_count=total_count,
                          total_pages=total_pages,
                          search=search,
                          status_counts=status_counts)


@settings_bp.route('/settings/teams/<int:team_id>/status', methods=['PUT'])
@login_required
def update_team_status(team_id):
    """Update a team's status."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        status = data.get('status', '').strip()
        
        if not status:
            return jsonify({'error': 'Status is required'}), 400
        
        # Valid statuses
        valid_statuses = ['pending', 'approved', 'rejected', 'waitlisted', 'cancelled', 'finalist']
        if status not in valid_statuses:
            return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
        
        # Check if the team exists and get registration_id
        existing = supabase.table('teams').select('id, registration_id').eq('id', team_id).execute()
        if not existing.data:
            return jsonify({'error': 'Team not found'}), 404
        
        registration_id = existing.data[0].get('registration_id')
        
        # Prepare update data
        update_data = {'status': status}
        
        # Handle finalist status - update finalist-specific fields
        if status == 'finalist':
            update_data['is_finalist'] = True
            # Validate and get finalist fields
            is_valid, error_msg, validated_fields = validate_finalist_fields(data)
            if not is_valid:
                return jsonify({'error': error_msg}), 400
            update_data.update(validated_fields)
            
            # Clear CTFd credentials to generate fresh ones
            if registration_id:
                clear_ctfd_credentials_for_team(supabase, registration_id)
        else:
            # If changing from finalist to another status, clear finalist fields
            update_data['is_finalist'] = False
            update_data['finalist_round_id'] = None
            update_data['finalist_position'] = None
            update_data['finalist_score_previous_round'] = None
        
        # Update the team status and finalist fields
        supabase.table('teams').update(update_data).eq('id', team_id).execute()
        
        return jsonify({'success': True, 'message': f'Team status updated to {status}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/teams/bulk-status', methods=['PUT'])
@login_required
def bulk_update_team_status():
    """Update multiple teams' status at once."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        team_ids = data.get('team_ids', [])
        status = data.get('status', '').strip()
        
        if not team_ids:
            return jsonify({'error': 'No teams selected'}), 400
        
        if not status:
            return jsonify({'error': 'Status is required'}), 400
        
        # Valid statuses
        valid_statuses = ['pending', 'approved', 'rejected', 'waitlisted', 'cancelled', 'finalist']
        if status not in valid_statuses:
            return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
        
        # Update teams in bulk
        updated_count = 0
        failed_ids = []
        for team_id in team_ids:
            try:
                # Get team's registration_id first
                team_response = supabase.table('teams').select('registration_id').eq('id', team_id).execute()
                if not team_response.data:
                    failed_ids.append(team_id)
                    continue
                
                registration_id = team_response.data[0].get('registration_id')
                
                # Prepare update data based on status
                update_data = {'status': status}
                
                # Handle finalist status
                if status == 'finalist':
                    update_data['is_finalist'] = True
                    # Note: bulk update doesn't set position/round/score - those should be set individually
                    
                    # Clear CTFd credentials to generate fresh ones
                    if registration_id:
                        clear_ctfd_credentials_for_team(supabase, registration_id)
                else:
                    # If changing from finalist to another status, clear finalist fields
                    update_data['is_finalist'] = False
                    update_data['finalist_round_id'] = None
                    update_data['finalist_position'] = None
                    update_data['finalist_score_previous_round'] = None
                
                supabase.table('teams').update(update_data).eq('id', team_id).execute()
                updated_count += 1
            except Exception:
                failed_ids.append(team_id)
        
        response_data = {
            'success': True,
            'message': f'Updated {updated_count} teams to status: {status}',
            'updated_count': updated_count
        }
        
        if failed_ids:
            response_data['failed_ids'] = failed_ids
            response_data['message'] += f'. Failed to update {len(failed_ids)} team(s).'
        
        return jsonify(response_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/teams/statuses')
@login_required
def get_team_statuses():
    """Get list of valid team statuses and counts."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Valid statuses
        valid_statuses = ['pending', 'approved', 'rejected', 'waitlisted', 'cancelled', 'finalist']
        
        # Get count for each status
        status_counts = {}
        for status in valid_statuses:
            response = supabase.table('teams').select('id', count='exact').eq('status', status).execute()
            # Get count from response - check count attribute first, then data length
            if hasattr(response, 'count') and response.count is not None:
                status_counts[status] = response.count
            elif response.data:
                status_counts[status] = len(response.data)
            else:
                status_counts[status] = 0
        
        return jsonify({
            'success': True,
            'statuses': valid_statuses,
            'counts': status_counts
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/teams/<int:team_id>/json', methods=['GET'])
@login_required
def get_team(team_id):
    """Get a specific team's details for editing (JSON API)."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        response = supabase.table('teams').select('*').eq('id', team_id).execute()
        if not response.data:
            return jsonify({'error': 'Team not found'}), 404
        return jsonify({'success': True, 'data': response.data[0]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/teams/<int:team_id>', methods=['PUT'])
@login_required
def update_team(team_id):
    """Update a team's details."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        
        # Check if team exists and get registration_id
        existing = supabase.table('teams').select('id, registration_id').eq('id', team_id).execute()
        if not existing.data:
            return jsonify({'error': 'Team not found'}), 404
        
        registration_id = existing.data[0].get('registration_id')
        
        # Fields that can be updated
        allowed_fields = [
            'team_name', 'project_name', 'captain_name', 'captain_email',
            'contact_name', 'contact_email', 'contact_number', 'status',
            'finalist_position', 'finalist_round_id', 'finalist_score_previous_round'
        ]
        
        update_data = {}
        for field in allowed_fields:
            if field in data:
                value = data[field]
                # Strip strings and handle empty values
                if isinstance(value, str):
                    value = value.strip()
                update_data[field] = value if value else None
        
        if not update_data:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        # Validate required fields
        if 'team_name' in update_data and not update_data['team_name']:
            return jsonify({'error': 'Team name is required'}), 400
        
        # Handle finalist status logic
        if 'status' in update_data:
            if update_data['status'] == 'finalist':
                update_data['is_finalist'] = True
                # Validate finalist fields if provided
                is_valid, error_msg, validated_fields = validate_finalist_fields(update_data)
                if not is_valid:
                    return jsonify({'error': error_msg}), 400
                # Merge validated fields (this replaces the original values with validated ones)
                update_data.update(validated_fields)
                
                # Clear CTFd credentials to generate fresh ones
                if registration_id:
                    clear_ctfd_credentials_for_team(supabase, registration_id)
            else:
                # If changing from finalist to another status, clear finalist fields
                update_data['is_finalist'] = False
                update_data['finalist_round_id'] = None
                update_data['finalist_position'] = None
                update_data['finalist_score_previous_round'] = None
        
        supabase.table('teams').update(update_data).eq('id', team_id).execute()
        return jsonify({'success': True, 'message': 'Team updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/participants/<int:participant_id>', methods=['GET'])
@login_required
def get_participant(participant_id):
    """Get a specific participant's details for editing."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        response = supabase.table('team_members').select('*').eq('id', participant_id).execute()
        if not response.data:
            return jsonify({'error': 'Participant not found'}), 404
        return jsonify({'success': True, 'data': response.data[0]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/participants/<int:participant_id>', methods=['PUT'])
@login_required
def update_participant(participant_id):
    """Update a participant's details."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        
        # Check if participant exists
        existing = supabase.table('team_members').select('id').eq('id', participant_id).execute()
        if not existing.data:
            return jsonify({'error': 'Participant not found'}), 404
        
        # Fields that can be updated (phone is the database column name)
        allowed_fields = [
            'name', 'full_name', 'email', 'phone', 'institution',
            'class', 'gender', 't_shirt_size'
        ]
        
        update_data = {}
        for field in allowed_fields:
            if field in data:
                value = data[field]
                # Strip strings and handle empty values
                if isinstance(value, str):
                    value = value.strip()
                update_data[field] = value if value else None
        
        if not update_data:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        # Validate required fields
        if 'name' in update_data and not update_data['name']:
            return jsonify({'error': 'Name is required'}), 400
        
        supabase.table('team_members').update(update_data).eq('id', participant_id).execute()
        return jsonify({'success': True, 'message': 'Participant updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/email-audit-logs')
@login_required
def email_audit_logs():
    """View email audit logs page with pagination."""
    supabase = get_supabase_client()
    logs = []
    total_count = 0
    status_counts = {'sent': 0, 'failed': 0}
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    status_filter = request.args.get('status', '', type=str).strip()
    
    # Ensure valid values
    page = max(1, page)
    per_page = min(max(10, per_page), 100)  # Between 10 and 100
    
    if supabase:
        try:
            # Get status counts for all logs
            for status in ['sent', 'failed']:
                count_response = supabase.table('email_audit_logs').select('id', count='exact').eq('status', status).execute()
                if hasattr(count_response, 'count') and count_response.count is not None:
                    status_counts[status] = count_response.count
                elif count_response.data:
                    status_counts[status] = len(count_response.data)
            
            # Build base query
            query = supabase.table('email_audit_logs').select('*', count='exact')
            
            # Apply status filter
            if status_filter:
                query = query.eq('status', status_filter)
            
            # Get total count first
            count_response = query.execute()
            total_count = count_response.count if hasattr(count_response, 'count') and count_response.count else len(count_response.data) if count_response.data else 0
            
            # Apply pagination
            offset = (page - 1) * per_page
            logs_response = query.order('sent_at', desc=True).range(offset, offset + per_page - 1).execute()
            logs = logs_response.data if logs_response.data else []
        except Exception as e:
            flash(f'Error fetching email audit logs: {str(e)}', 'error')
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    return render_template('settings/email_audit_logs.html', 
                          logs=logs,
                          page=page,
                          per_page=per_page,
                          total_count=total_count,
                          total_pages=total_pages,
                          status_filter=status_filter,
                          status_counts=status_counts)


@settings_bp.route('/settings/email-audit-logs/api', methods=['GET'])
@login_required
def get_email_audit_logs():
    """API endpoint to fetch email audit logs with optional filters."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Get filter parameters
        status = request.args.get('status')
        template_id = request.args.get('template_id')
        team_id = request.args.get('team_id')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        # Build query
        query = supabase.table('email_audit_logs').select('*')
        
        if status:
            query = query.eq('status', status)
        if template_id:
            query = query.eq('template_id', template_id)
        if team_id:
            query = query.eq('team_id', team_id)
        
        # Order by most recent first and apply pagination
        offset = (page - 1) * per_page
        query = query.order('sent_at', desc=True).range(offset, offset + per_page - 1)
        
        response = query.execute()
        logs = response.data if response.data else []
        
        return jsonify({
            'success': True,
            'data': logs,
            'page': page,
            'per_page': per_page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/email-audit-logs/clear', methods=['POST'])
@login_required
def clear_email_audit_logs():
    """Clear all email audit logs."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Delete all records by matching any id > 0 (all valid records have positive IDs)
        # This is a common pattern in Supabase/PostgREST to delete all records
        supabase.table('email_audit_logs').delete().gt('id', 0).execute()
        return jsonify({'success': True, 'message': 'All email audit logs cleared'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/deduplication')
@login_required
def deduplication_checker():
    """Render the deduplication checker page."""
    return render_template('settings/deduplication.html')


@settings_bp.route('/settings/deduplication/check', methods=['GET'])
@login_required
def check_duplicates():
    """Check for duplicate registration data across teams and participants."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Fetch all teams
        teams_response = supabase.table('teams').select('*').execute()
        teams = teams_response.data if teams_response.data else []
        
        # Fetch all team members
        members_response = supabase.table('team_members').select('*').execute()
        members = members_response.data if members_response.data else []
        
        # Build lookup for teams by registration_id
        teams_by_reg_id = {team['registration_id']: team for team in teams if team.get('registration_id')}
        teams_by_id = {team['id']: team for team in teams}
        
        duplicates = {
            'team_names': [],
            'participant_emails': [],
            'phone_numbers': [],
            'captain_emails': [],
            'members_in_multiple_teams': []
        }
        
        # 1. Check for duplicate team names (case-insensitive)
        team_names = {}
        for team in teams:
            name_lower = team['team_name'].lower().strip() if team.get('team_name') else ''
            if name_lower:
                if name_lower not in team_names:
                    team_names[name_lower] = []
                team_names[name_lower].append(team)
        
        for name, team_list in team_names.items():
            if len(team_list) > 1:
                duplicates['team_names'].append({
                    'value': team_list[0]['team_name'],
                    'count': len(team_list),
                    'teams': [{
                        'id': t['id'],
                        'team_name': t['team_name'],
                        'captain_name': t.get('captain_name'),
                        'status': t.get('status')
                    } for t in team_list]
                })
        
        # 2. Check for duplicate participant emails (across all teams)
        participant_emails = {}
        for member in members:
            email = member.get('email', '').lower().strip() if member.get('email') else ''
            if email:
                if email not in participant_emails:
                    participant_emails[email] = []
                team = teams_by_reg_id.get(member.get('team_id'))
                participant_emails[email].append({
                    'member_id': member['id'],
                    'member_name': member.get('name'),
                    'team_id': team['id'] if team else None,
                    'team_name': team['team_name'] if team else 'Unknown Team',
                    'team_status': team['status'] if team else None
                })
        
        for email, member_list in participant_emails.items():
            if len(member_list) > 1:
                duplicates['participant_emails'].append({
                    'value': email,
                    'count': len(member_list),
                    'occurrences': member_list
                })
        
        # 3. Check for duplicate phone numbers (across participants)
        phone_numbers = {}
        for member in members:
            phone = member.get('phone', '').strip() if member.get('phone') else ''
            # Normalize phone number - remove common separators
            if phone:
                normalized_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
                if normalized_phone and len(normalized_phone) >= MIN_PHONE_LENGTH:
                    if normalized_phone not in phone_numbers:
                        phone_numbers[normalized_phone] = []
                    team = teams_by_reg_id.get(member.get('team_id'))
                    phone_numbers[normalized_phone].append({
                        'member_id': member['id'],
                        'member_name': member.get('name'),
                        'phone': phone,
                        'team_id': team['id'] if team else None,
                        'team_name': team['team_name'] if team else 'Unknown Team',
                        'team_status': team['status'] if team else None
                    })
        
        for phone, member_list in phone_numbers.items():
            if len(member_list) > 1:
                duplicates['phone_numbers'].append({
                    'value': member_list[0]['phone'],
                    'count': len(member_list),
                    'occurrences': member_list
                })
        
        # 4. Check for duplicate captain emails
        captain_emails = {}
        for team in teams:
            captain_email = team.get('captain_email', '').lower().strip() if team.get('captain_email') else ''
            if captain_email:
                if captain_email not in captain_emails:
                    captain_emails[captain_email] = []
                captain_emails[captain_email].append({
                    'id': team['id'],
                    'team_name': team['team_name'],
                    'captain_name': team.get('captain_name'),
                    'status': team.get('status')
                })
        
        for email, team_list in captain_emails.items():
            if len(team_list) > 1:
                duplicates['captain_emails'].append({
                    'value': email,
                    'count': len(team_list),
                    'teams': team_list
                })
        
        # 5. Check for members appearing in multiple teams (by email or name + institution)
        # Group by email first
        member_teams = {}
        for member in members:
            email = member.get('email', '').lower().strip() if member.get('email') else ''
            if email:
                if email not in member_teams:
                    member_teams[email] = set()
                team_id = member.get('team_id')
                if team_id:
                    member_teams[email].add(team_id)
        
        for email, team_ids in member_teams.items():
            if len(team_ids) > 1:
                # Get details about these teams
                member_info = next((m for m in members if m.get('email', '').lower().strip() == email), None)
                team_details = []
                for tid in team_ids:
                    team = teams_by_reg_id.get(tid)
                    if team:
                        team_details.append({
                            'id': team['id'],
                            'team_name': team['team_name'],
                            'status': team.get('status')
                        })
                
                duplicates['members_in_multiple_teams'].append({
                    'email': email,
                    'name': member_info.get('name') if member_info else 'Unknown',
                    'team_count': len(team_ids),
                    'teams': team_details
                })
        
        # Calculate summary statistics
        summary = {
            'total_teams': len(teams),
            'total_participants': len(members),
            'duplicate_team_names': len(duplicates['team_names']),
            'duplicate_emails': len(duplicates['participant_emails']),
            'duplicate_phones': len(duplicates['phone_numbers']),
            'duplicate_captain_emails': len(duplicates['captain_emails']),
            'members_in_multiple_teams': len(duplicates['members_in_multiple_teams'])
        }
        
        return jsonify({
            'success': True,
            'summary': summary,
            'duplicates': duplicates
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def generate_password(length=12):
    """Generate a random password with alphanumeric characters."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


@settings_bp.route('/settings/teams/<int:team_id>/generate-passwords', methods=['POST'])
@login_required
def generate_team_passwords(team_id):
    """Generate passwords for team and all its members in bulk (plain text, stored in DB)."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Fetch team
        team_response = supabase.table('teams').select('*').eq('id', team_id).execute()
        if not team_response.data:
            return jsonify({'error': 'Team not found'}), 404
        
        team = team_response.data[0]
        registration_id = team.get('registration_id')
        
        if not registration_id:
            return jsonify({'error': 'Team has no registration ID'}), 400
        
        # Generate team password
        team_password = generate_password()
        
        # Check if team credentials already exist
        existing_creds = supabase.table('ctfd_team_credentials').select('id').eq('team_id', registration_id).execute()
        
        if existing_creds.data:
            # Update existing credentials
            supabase.table('ctfd_team_credentials').update({
                'ctfd_team_password': team_password
            }).eq('team_id', registration_id).execute()
        else:
            # Create new credentials
            supabase.table('ctfd_team_credentials').insert({
                'team_id': registration_id,
                'ctfd_team_password': team_password
            }).execute()
        
        # Fetch team members
        members_response = supabase.table('team_members').select('*').eq('team_id', registration_id).execute()
        members = members_response.data if members_response.data else []
        
        member_passwords = []
        for member in members:
            member_password = generate_password()
            
            # Check if user credentials already exist
            existing_user_creds = supabase.table('ctfd_user_credentials').select('id').eq('member_id', member['id']).execute()
            
            if existing_user_creds.data:
                # Update existing credentials
                supabase.table('ctfd_user_credentials').update({
                    'ctfd_password': member_password
                }).eq('member_id', member['id']).execute()
            else:
                # Create new credentials
                supabase.table('ctfd_user_credentials').insert({
                    'member_id': member['id'],
                    'ctfd_password': member_password
                }).execute()
            
            member_passwords.append({
                'member_id': member['id'],
                'name': member.get('name'),
                'email': member.get('email'),
                'password': member_password
            })
        
        return jsonify({
            'success': True,
            'message': f'Generated passwords for team and {len(members)} members',
            'team_password': team_password,
            'member_passwords': member_passwords
        })
        
    except Exception as e:
        logger.error(f"Error generating passwords: {str(e)}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/teams/<int:team_id>/create-ctfd-accounts', methods=['POST'])
@login_required
def create_ctfd_accounts(team_id):
    """Create team and user accounts in CTFd for a specific team."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Get CTFd configuration from database settings
        ctfd_url, ctfd_api_key = get_ctfd_config()
        
        if not ctfd_url or not ctfd_api_key:
            return jsonify({'error': 'CTFd URL and API key not configured'}), 400
        
        # Initialize CTFd client
        client = CTFdAPIClient(ctfd_url, ctfd_api_key)
        
        # Fetch team
        team_response = supabase.table('teams').select('*').eq('id', team_id).execute()
        if not team_response.data:
            return jsonify({'error': 'Team not found'}), 404
        
        team = team_response.data[0]
        registration_id = team.get('registration_id')
        team_name = team.get('team_name')
        
        if not registration_id:
            return jsonify({'error': 'Team has no registration ID'}), 400
        
        # Fetch team credentials
        team_creds_response = supabase.table('ctfd_team_credentials').select('*').eq('team_id', registration_id).execute()
        if not team_creds_response.data:
            return jsonify({'error': 'Team credentials not found. Please generate passwords first.'}), 400
        
        team_creds = team_creds_response.data[0]
        team_password = team_creds.get('ctfd_team_password')
        
        if not team_password:
            return jsonify({'error': 'Team password not found. Please generate passwords first.'}), 400
        
        # Check if team already has CTFd ID (already created)
        if team_creds.get('ctfd_team_id'):
            return jsonify({
                'error': 'Team already exists in CTFd',
                'ctfd_team_id': team_creds['ctfd_team_id']
            }), 400
        
        # Fetch team members
        members_response = supabase.table('team_members').select('*').eq('team_id', registration_id).execute()
        members = members_response.data if members_response.data else []
        
        logs = []
        ctfd_team_id = None
        created_user_ids = []
        
        try:
            # Step 1: Create team in CTFd
            log_entry = {
                'team_id': team_id,
                'team_registration_id': registration_id,
                'operation_type': 'create_team',
                'status': 'pending',
                'request_data': {'team_name': team_name}
            }
            
            try:
                team_result = client.create_team({
                    'name': team_name,
                    'password': team_password
                })
                ctfd_team_id = team_result.get('id')
                
                log_entry['status'] = 'success'
                log_entry['response_data'] = team_result
                log_entry['ctfd_entity_id'] = ctfd_team_id
                
                # Update team credentials with CTFd team ID
                supabase.table('ctfd_team_credentials').update({
                    'ctfd_team_id': ctfd_team_id
                }).eq('team_id', registration_id).execute()
                
            except CTFdAPIException as e:
                log_entry['status'] = 'failed'
                log_entry['error_message'] = e.message
                log_entry['response_data'] = e.details
                logs.append(log_entry)
                supabase.table('ctfd_operation_logs').insert(log_entry).execute()
                return jsonify({
                    'success': False,
                    'error': f'Failed to create team: {e.message}',
                    'logs': logs
                }), 500
            
            logs.append(log_entry)
            supabase.table('ctfd_operation_logs').insert(log_entry).execute()
            
            # Step 2: Create users in CTFd
            for member in members:
                # Fetch user credentials
                user_creds_response = supabase.table('ctfd_user_credentials').select('*').eq('member_id', member['id']).execute()
                if not user_creds_response.data:
                    continue
                
                user_creds = user_creds_response.data[0]
                user_password = user_creds.get('ctfd_password')
                
                if not user_password or not member.get('email'):
                    continue
                
                # Skip if user already has CTFd ID
                if user_creds.get('ctfd_user_id'):
                    continue
                
                user_log_entry = {
                    'team_id': team_id,
                    'team_registration_id': registration_id,
                    'member_id': member['id'],
                    'operation_type': 'create_user',
                    'status': 'pending',
                    'request_data': {'email': member['email'], 'name': member.get('name', member['email'])}
                }
                
                try:
                    user_result = client.create_user({
                        'name': member.get('name', member['email']),
                        'email': member['email'],
                        'password': user_password,
                        'verified': True
                    })
                    ctfd_user_id = user_result.get('id')
                    created_user_ids.append(ctfd_user_id)
                    
                    user_log_entry['status'] = 'success'
                    user_log_entry['response_data'] = user_result
                    user_log_entry['ctfd_entity_id'] = ctfd_user_id
                    
                    # Update user credentials with CTFd user ID
                    supabase.table('ctfd_user_credentials').update({
                        'ctfd_user_id': ctfd_user_id
                    }).eq('member_id', member['id']).execute()
                    
                except CTFdAPIException as e:
                    user_log_entry['status'] = 'failed'
                    user_log_entry['error_message'] = e.message
                    user_log_entry['response_data'] = e.details
                
                logs.append(user_log_entry)
                supabase.table('ctfd_operation_logs').insert(user_log_entry).execute()
            
            # Step 3: Add users to team
            for user_id in created_user_ids:
                add_log_entry = {
                    'team_id': team_id,
                    'team_registration_id': registration_id,
                    'operation_type': 'add_user_to_team',
                    'status': 'pending',
                    'request_data': {'ctfd_team_id': ctfd_team_id, 'ctfd_user_id': user_id}
                }
                
                try:
                    client.add_user_to_team(ctfd_team_id, user_id)
                    add_log_entry['status'] = 'success'
                    add_log_entry['ctfd_entity_id'] = user_id
                except CTFdAPIException as e:
                    add_log_entry['status'] = 'failed'
                    add_log_entry['error_message'] = e.message
                    add_log_entry['response_data'] = e.details
                
                logs.append(add_log_entry)
                supabase.table('ctfd_operation_logs').insert(add_log_entry).execute()
            
            # Count successes and failures
            success_count = sum(1 for log in logs if log['status'] == 'success')
            failed_count = sum(1 for log in logs if log['status'] == 'failed')
            
            return jsonify({
                'success': True,
                'message': f'CTFd accounts created. {success_count} operations succeeded, {failed_count} failed.',
                'ctfd_team_id': ctfd_team_id,
                'logs': logs
            })
            
        except Exception as e:
            logger.error(f"Error creating CTFd accounts: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e),
                'logs': logs
            }), 500
        
    except Exception as e:
        logger.error(f"Error creating CTFd accounts: {str(e)}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/teams/<int:team_id>/ctfd-logs', methods=['GET'])
@login_required
def get_team_ctfd_logs(team_id):
    """Get CTFd operation logs for a specific team."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Fetch logs for this team
        logs_response = supabase.table('ctfd_operation_logs').select('*').eq('team_id', team_id).order('created_at', desc=True).execute()
        logs = logs_response.data if logs_response.data else []
        
        return jsonify({
            'success': True,
            'logs': logs
        })
        
    except Exception as e:
        logger.error(f"Error fetching CTFd logs: {str(e)}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/teams/bulk-generate-passwords', methods=['POST'])
@login_required
def bulk_generate_passwords():
    """Generate passwords for multiple teams and their members in bulk."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        team_ids = data.get('team_ids', [])
        
        if not team_ids:
            return jsonify({'error': 'No teams selected'}), 400
        
        total_teams = 0
        total_members = 0
        failed_teams = []
        
        for team_id in team_ids:
            try:
                # Fetch team
                team_response = supabase.table('teams').select('*').eq('id', team_id).execute()
                if not team_response.data:
                    failed_teams.append({'team_id': team_id, 'error': 'Team not found'})
                    continue
                
                team = team_response.data[0]
                registration_id = team.get('registration_id')
                
                if not registration_id:
                    failed_teams.append({'team_id': team_id, 'error': 'No registration ID'})
                    continue
                
                # Generate team password
                team_password = generate_password()
                
                # Check if team credentials already exist
                existing_creds = supabase.table('ctfd_team_credentials').select('id').eq('team_id', registration_id).execute()
                
                if existing_creds.data:
                    supabase.table('ctfd_team_credentials').update({
                        'ctfd_team_password': team_password
                    }).eq('team_id', registration_id).execute()
                else:
                    supabase.table('ctfd_team_credentials').insert({
                        'team_id': registration_id,
                        'ctfd_team_password': team_password
                    }).execute()
                
                total_teams += 1
                
                # Fetch and generate passwords for team members
                members_response = supabase.table('team_members').select('*').eq('team_id', registration_id).execute()
                members = members_response.data if members_response.data else []
                
                for member in members:
                    member_password = generate_password()
                    
                    existing_user_creds = supabase.table('ctfd_user_credentials').select('id').eq('member_id', member['id']).execute()
                    
                    if existing_user_creds.data:
                        supabase.table('ctfd_user_credentials').update({
                            'ctfd_password': member_password
                        }).eq('member_id', member['id']).execute()
                    else:
                        supabase.table('ctfd_user_credentials').insert({
                            'member_id': member['id'],
                            'ctfd_password': member_password
                        }).execute()
                    
                    total_members += 1
                    
            except Exception as e:
                failed_teams.append({'team_id': team_id, 'error': str(e)})
        
        message = f'Generated passwords for {total_teams} team(s) and {total_members} member(s).'
        if failed_teams:
            message += f' {len(failed_teams)} team(s) failed.'
        
        return jsonify({
            'success': True,
            'message': message,
            'total_teams': total_teams,
            'total_members': total_members,
            'failed_teams': failed_teams
        })
        
    except Exception as e:
        logger.error(f"Error in bulk password generation: {str(e)}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/ctfd-logs')
@login_required
def ctfd_logs():
    """View CTFd operation logs page with pagination and filtering."""
    supabase = get_supabase_client()
    logs = []
    total_count = 0
    status_counts = {'pending': 0, 'success': 0, 'failed': 0}
    operation_types = []
    
    # Pagination and filter parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    status_filter = request.args.get('status', '', type=str).strip()
    operation_filter = request.args.get('operation', '', type=str).strip()
    team_id = request.args.get('team_id', type=int)
    
    # Ensure valid values
    page = max(1, page)
    per_page = min(max(10, per_page), 100)  # Between 10 and 100
    
    if supabase:
        try:
            # Get status counts
            for status in ['pending', 'success', 'failed']:
                count_response = supabase.table('ctfd_operation_logs').select('id', count='exact').eq('status', status).execute()
                if hasattr(count_response, 'count') and count_response.count is not None:
                    status_counts[status] = count_response.count
                elif count_response.data:
                    status_counts[status] = len(count_response.data)
            
            # Get unique operation types for filter dropdown
            operations_response = supabase.table('ctfd_operation_logs').select('operation_type').execute()
            if operations_response.data:
                operation_types = sorted(list(set([log['operation_type'] for log in operations_response.data if log.get('operation_type')])))
            
            # Build base query
            query = supabase.table('ctfd_operation_logs').select('*', count='exact')
            
            # Apply filters
            if status_filter:
                query = query.eq('status', status_filter)
            if operation_filter:
                query = query.eq('operation_type', operation_filter)
            if team_id:
                query = query.eq('team_id', team_id)
            
            # Get total count first
            count_response = query.execute()
            total_count = count_response.count if hasattr(count_response, 'count') and count_response.count else len(count_response.data) if count_response.data else 0
            
            # Apply pagination
            offset = (page - 1) * per_page
            logs_response = query.order('created_at', desc=True).range(offset, offset + per_page - 1).execute()
            logs = logs_response.data if logs_response.data else []
            
            # Fetch team names for logs that have team_id
            team_ids = [log['team_id'] for log in logs if log.get('team_id')]
            teams_map = {}
            if team_ids:
                teams_response = supabase.table('teams').select('id, team_name').in_('id', team_ids).execute()
                if teams_response.data:
                    teams_map = {team['id']: team['team_name'] for team in teams_response.data}
            
            # Attach team names to logs
            for log in logs:
                if log.get('team_id'):
                    log['team_name'] = teams_map.get(log['team_id'], 'Unknown Team')
                    
        except Exception as e:
            flash(f'Error fetching CTFd operation logs: {str(e)}', 'error')
    
    # Calculate pagination info and total operations
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    total_operations = status_counts.get('pending', 0) + status_counts.get('success', 0) + status_counts.get('failed', 0)
    
    return render_template('settings/ctfd_logs.html', 
                          logs=logs,
                          page=page,
                          per_page=per_page,
                          total_count=total_count,
                          total_pages=total_pages,
                          status_filter=status_filter,
                          operation_filter=operation_filter,
                          team_id=team_id,
                          status_counts=status_counts,
                          operation_types=operation_types,
                          total_operations=total_operations)


@settings_bp.route('/settings/ctfd-logs/clear', methods=['POST'])
@login_required
def clear_ctfd_logs():
    """Clear all CTFd operation logs."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Delete all records by matching any id > 0 (all valid records have positive IDs)
        # This is a common pattern in Supabase/PostgREST to delete all records without truncating
        supabase.table('ctfd_operation_logs').delete().gt('id', 0).execute()
        return jsonify({'success': True, 'message': 'All CTFd operation logs cleared'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/teams/bulk-create-ctfd-accounts', methods=['POST'])
@login_required
def bulk_create_ctfd_accounts():
    """Create CTFd accounts for multiple teams and their members in bulk."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Get CTFd configuration from database settings
        ctfd_url, ctfd_api_key = get_ctfd_config()
        
        if not ctfd_url or not ctfd_api_key:
            return jsonify({'error': 'CTFd URL and API key not configured'}), 400
        
        # Initialize CTFd client
        client = CTFdAPIClient(ctfd_url, ctfd_api_key)
        
        data = request.json
        team_ids = data.get('team_ids', [])
        
        if not team_ids:
            return jsonify({'error': 'No teams selected'}), 400
        
        total_teams_created = 0
        total_users_created = 0
        total_users_added = 0
        failed_teams = []
        all_logs = []
        
        for team_id in team_ids:
            try:
                # Fetch team
                team_response = supabase.table('teams').select('*').eq('id', team_id).execute()
                if not team_response.data:
                    failed_teams.append({'team_id': team_id, 'error': 'Team not found'})
                    continue
                
                team = team_response.data[0]
                registration_id = team.get('registration_id')
                team_name = team.get('team_name')
                
                if not registration_id:
                    failed_teams.append({'team_id': team_id, 'error': 'No registration ID'})
                    continue
                
                # Fetch team credentials
                team_creds_response = supabase.table('ctfd_team_credentials').select('*').eq('team_id', registration_id).execute()
                if not team_creds_response.data:
                    failed_teams.append({'team_id': team_id, 'error': 'No credentials. Generate passwords first.'})
                    continue
                
                team_creds = team_creds_response.data[0]
                team_password = team_creds.get('ctfd_team_password')
                
                if not team_password:
                    failed_teams.append({'team_id': team_id, 'error': 'No team password. Generate passwords first.'})
                    continue
                
                # Check if team already has CTFd ID
                if team_creds.get('ctfd_team_id'):
                    # Team already exists, skip team creation but continue with users
                    ctfd_team_id = team_creds['ctfd_team_id']
                else:
                    # Create team in CTFd
                    log_entry = {
                        'team_id': team_id,
                        'team_registration_id': registration_id,
                        'operation_type': 'create_team',
                        'status': 'pending',
                        'request_data': {'team_name': team_name}
                    }
                    
                    try:
                        team_result = client.create_team({
                            'name': team_name,
                            'password': team_password
                        })
                        ctfd_team_id = team_result.get('id')
                        
                        log_entry['status'] = 'success'
                        log_entry['response_data'] = team_result
                        log_entry['ctfd_entity_id'] = ctfd_team_id
                        
                        supabase.table('ctfd_team_credentials').update({
                            'ctfd_team_id': ctfd_team_id
                        }).eq('team_id', registration_id).execute()
                        
                        total_teams_created += 1
                        
                    except CTFdAPIException as e:
                        log_entry['status'] = 'failed'
                        log_entry['error_message'] = e.message
                        log_entry['response_data'] = e.details
                        all_logs.append(log_entry)
                        supabase.table('ctfd_operation_logs').insert(log_entry).execute()
                        failed_teams.append({'team_id': team_id, 'error': f'Team creation failed: {e.message}'})
                        continue
                    
                    all_logs.append(log_entry)
                    supabase.table('ctfd_operation_logs').insert(log_entry).execute()
                
                # Fetch team members
                members_response = supabase.table('team_members').select('*').eq('team_id', registration_id).execute()
                members = members_response.data if members_response.data else []
                
                created_user_ids = []
                
                for member in members:
                    user_creds_response = supabase.table('ctfd_user_credentials').select('*').eq('member_id', member['id']).execute()
                    if not user_creds_response.data:
                        continue
                    
                    user_creds = user_creds_response.data[0]
                    user_password = user_creds.get('ctfd_password')
                    
                    if not user_password or not member.get('email'):
                        continue
                    
                    if user_creds.get('ctfd_user_id'):
                        # User already exists, add to team if needed
                        created_user_ids.append(user_creds['ctfd_user_id'])
                        continue
                    
                    user_log_entry = {
                        'team_id': team_id,
                        'team_registration_id': registration_id,
                        'member_id': member['id'],
                        'operation_type': 'create_user',
                        'status': 'pending',
                        'request_data': {'email': member['email'], 'name': member.get('name', member['email'])}
                    }
                    
                    try:
                        user_result = client.create_user({
                            'name': member.get('name', member['email']),
                            'email': member['email'],
                            'password': user_password,
                            'verified': True
                        })
                        ctfd_user_id = user_result.get('id')
                        created_user_ids.append(ctfd_user_id)
                        
                        user_log_entry['status'] = 'success'
                        user_log_entry['response_data'] = user_result
                        user_log_entry['ctfd_entity_id'] = ctfd_user_id
                        
                        supabase.table('ctfd_user_credentials').update({
                            'ctfd_user_id': ctfd_user_id
                        }).eq('member_id', member['id']).execute()
                        
                        total_users_created += 1
                        
                    except CTFdAPIException as e:
                        user_log_entry['status'] = 'failed'
                        user_log_entry['error_message'] = e.message
                        user_log_entry['response_data'] = e.details
                    
                    all_logs.append(user_log_entry)
                    supabase.table('ctfd_operation_logs').insert(user_log_entry).execute()
                
                # Add users to team
                for user_id in created_user_ids:
                    add_log_entry = {
                        'team_id': team_id,
                        'team_registration_id': registration_id,
                        'operation_type': 'add_user_to_team',
                        'status': 'pending',
                        'request_data': {'ctfd_team_id': ctfd_team_id, 'ctfd_user_id': user_id}
                    }
                    
                    try:
                        client.add_user_to_team(ctfd_team_id, user_id)
                        add_log_entry['status'] = 'success'
                        add_log_entry['ctfd_entity_id'] = user_id
                        total_users_added += 1
                    except CTFdAPIException as e:
                        add_log_entry['status'] = 'failed'
                        add_log_entry['error_message'] = e.message
                        add_log_entry['response_data'] = e.details
                    
                    all_logs.append(add_log_entry)
                    supabase.table('ctfd_operation_logs').insert(add_log_entry).execute()
                    
            except Exception as e:
                failed_teams.append({'team_id': team_id, 'error': str(e)})
        
        message = f'Created {total_teams_created} team(s), {total_users_created} user(s), added {total_users_added} user(s) to teams.'
        if failed_teams:
            message += f' {len(failed_teams)} team(s) had issues.'
        
        return jsonify({
            'success': True,
            'message': message,
            'total_teams_created': total_teams_created,
            'total_users_created': total_users_created,
            'total_users_added': total_users_added,
            'failed_teams': failed_teams
        })
        
    except Exception as e:
        logger.error(f"Error in bulk CTFd account creation: {str(e)}")
        return jsonify({'error': str(e)}), 500
