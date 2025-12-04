from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, send_from_directory
from flask_login import login_required, current_user
from app.supabase_client import get_supabase_client
import secrets
import os
import uuid
import logging
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
    """Send bulk emails to participants using a template, optionally filtered by team status."""
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
        include_team_captains = data.get('include_team_captains', False)
        attachment_ids = data.get('attachments', [])  # List of attachment IDs
        status_filter = data.get('status_filter', [])  # List of statuses to filter by (empty = all)
        
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
        
        # Connect to SMTP server
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
                    
                    # Create message with mixed type to support both alternative content and attachments
                    msg = MIMEMultipart('mixed')
                    msg['Subject'] = subject
                    msg['From'] = f'{sender_name} <{sender_email}>'
                    msg['To'] = recipient['email']
                    
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
                    
                    # Find and process inline images in the template body
                    # Look for patterns like src="/uploads/email_attachments/..." or src="{{cid:filename}}"
                    img_pattern = r'src=["\'](?:/uploads/email_attachments/|\{\{cid:)([^"\']+)["\']'
                    matches = re.findall(img_pattern, body)
                    
                    for i, match in enumerate(matches):
                        filename = match.rstrip('}}')
                        file_path = os.path.join(upload_folder, secure_filename(filename))
                        
                        if os.path.exists(file_path) and allowed_image(filename):
                            cid = f'image{i}'
                            # Replace the src with cid reference
                            body = re.sub(
                                r'src=["\'](?:/uploads/email_attachments/|\{\{cid:)' + re.escape(match) + r'["\']',
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
                    
                    # Log successful send
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
                    
                    # Log failed send
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
        
        # Insert audit logs into database
        if audit_logs:
            try:
                supabase.table('email_audit_logs').insert(audit_logs).execute()
            except Exception as log_error:
                # Log the error but don't fail the request
                logger.warning("Failed to save email audit logs: %s", log_error)
        
        return jsonify({
            'success': True,
            'sent': sent_count,
            'failed': failed_count,
            'total': len(recipients),
            'message': f'Sent {sent_count} emails, {failed_count} failed'
        })
        
    except smtplib.SMTPAuthenticationError:
        return jsonify({'error': 'SMTP authentication failed. Check username and password.'}), 400
    except smtplib.SMTPConnectError:
        return jsonify({'error': 'Failed to connect to SMTP server. Check host and port.'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to send bulk emails: {str(e)}'}), 500


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
            valid_statuses = ['pending', 'approved', 'rejected', 'waitlisted', 'cancelled']
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
            
            # Apply search filter (search by team_name, captain_name, captain_email)
            # Note: registration_id is BIGINT, so we can't use ilike on it directly
            if search:
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
            
            valid_statuses = ['pending', 'approved', 'rejected', 'waitlisted', 'cancelled']
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
        valid_statuses = ['pending', 'approved', 'rejected', 'waitlisted', 'cancelled']
        if status not in valid_statuses:
            return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
        
        # Check if the team exists
        existing = supabase.table('teams').select('id').eq('id', team_id).execute()
        if not existing.data:
            return jsonify({'error': 'Team not found'}), 404
        
        # Update the team status
        supabase.table('teams').update({'status': status}).eq('id', team_id).execute()
        
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
        valid_statuses = ['pending', 'approved', 'rejected', 'waitlisted', 'cancelled']
        if status not in valid_statuses:
            return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
        
        # Update teams in bulk
        updated_count = 0
        failed_ids = []
        for team_id in team_ids:
            try:
                supabase.table('teams').update({'status': status}).eq('id', team_id).execute()
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
        valid_statuses = ['pending', 'approved', 'rejected', 'waitlisted', 'cancelled']
        
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


@settings_bp.route('/settings/teams/<int:team_id>', methods=['GET'])
@login_required
def get_team(team_id):
    """Get a specific team's details for editing."""
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
        
        # Check if team exists
        existing = supabase.table('teams').select('id').eq('id', team_id).execute()
        if not existing.data:
            return jsonify({'error': 'Team not found'}), 404
        
        # Fields that can be updated
        allowed_fields = [
            'team_name', 'project_name', 'captain_name', 'captain_email',
            'contact_name', 'contact_email', 'contact_number', 'status'
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
            'class', 'gender'
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
    """View email audit logs page."""
    supabase = get_supabase_client()
    logs = []
    
    if supabase:
        try:
            # Fetch email audit logs ordered by most recent first
            response = supabase.table('email_audit_logs').select('*').order('sent_at', desc=True).limit(500).execute()
            logs = response.data if response.data else []
        except Exception as e:
            flash(f'Error fetching email audit logs: {str(e)}', 'error')
    
    return render_template('settings/email_audit_logs.html', logs=logs)


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
