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
    import re
    
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        template_id = data.get('template_id')
        test_email = data.get('test_email', '').strip()
        
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
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f'{sender_name} <{sender_email}>'
        msg['To'] = test_email
        
        # Plain text version - strip HTML tags
        text_content = body.replace('<br>', '\n').replace('<p>', '\n').replace('</p>', '\n')
        text_content = re.sub('<[^<]+?>', '', text_content)
        
        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(body, 'html'))
        
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


@settings_bp.route('/settings/email-templates/bulk-send', methods=['POST'])
@login_required
def bulk_send_email():
    """Send bulk emails to all participants using a template."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        template_id = data.get('template_id')
        include_team_captains = data.get('include_team_captains', False)
        
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
        
        # Fetch teams for team name lookup
        teams_response = supabase.table('teams').select('*').execute()
        teams = {team['id']: team for team in (teams_response.data or [])}
        
        # Fetch team credentials
        team_creds_response = supabase.table('ctfd_team_credentials').select('*').execute()
        team_credentials = {cred['team_id']: cred for cred in (team_creds_response.data or [])}
        
        # Fetch user credentials
        user_creds_response = supabase.table('ctfd_user_credentials').select('*').execute()
        user_credentials = {cred['member_id']: cred for cred in (user_creds_response.data or [])}
        
        # Prepare recipients
        recipients = []
        for member in members:
            if member.get('email'):
                team = teams.get(member.get('team_id'), {})
                team_cred = team_credentials.get(member.get('team_id'), {})
                user_cred = user_credentials.get(member.get('id'), {})
                
                recipients.append({
                    'email': member['email'],
                    'user_name': member.get('name', ''),
                    'user_email': member.get('email', ''),
                    'user_ctfd_username': user_cred.get('ctfd_username', ''),
                    'user_ctfd_password': user_cred.get('ctfd_password', ''),
                    'team_name': team.get('team_name', ''),
                    'team_ctfd_username': team_cred.get('ctfd_team_username', ''),
                    'team_ctfd_password': team_cred.get('ctfd_team_password', '')
                })
        
        # Add team captains if requested
        if include_team_captains:
            for team_id, team in teams.items():
                if team.get('captain_email'):
                    team_cred = team_credentials.get(team_id, {})
                    # Check if captain email is not already in recipients
                    if not any(r['email'] == team['captain_email'] for r in recipients):
                        recipients.append({
                            'email': team['captain_email'],
                            'user_name': team.get('captain_name', ''),
                            'user_email': team.get('captain_email', ''),
                            'user_ctfd_username': '',
                            'user_ctfd_password': '',
                            'team_name': team.get('team_name', ''),
                            'team_ctfd_username': team_cred.get('ctfd_team_username', ''),
                            'team_ctfd_password': team_cred.get('ctfd_team_password', '')
                        })
        
        if not recipients:
            return jsonify({'error': 'No recipients found with valid email addresses'}), 400
        
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
            
            # Import re at start of loop for HTML stripping
            import re
            
            for recipient in recipients:
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
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = subject
                    msg['From'] = f'{sender_name} <{sender_email}>'
                    msg['To'] = recipient['email']
                    
                    # Plain text version - strip HTML tags
                    text_content = body.replace('<br>', '\n').replace('<p>', '\n').replace('</p>', '\n')
                    text_content = re.sub('<[^<]+?>', '', text_content)
                    
                    msg.attach(MIMEText(text_content, 'plain'))
                    msg.attach(MIMEText(body, 'html'))
                    
                    server.sendmail(sender_email, recipient['email'], msg.as_string())
                    sent_count += 1
                except Exception:
                    failed_count += 1
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
        
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
    """List all teams with their credentials."""
    supabase = get_supabase_client()
    teams = []
    
    if supabase:
        try:
            # Fetch all teams
            teams_response = supabase.table('teams').select('*').order('team_name').execute()
            teams = teams_response.data if teams_response.data else []
            
            # Fetch team credentials and attach to teams
            for team in teams:
                # Get team credentials
                creds_response = supabase.table('ctfd_team_credentials').select('*').eq('team_id', team['id']).execute()
                team['credentials'] = creds_response.data[0] if creds_response.data else None
                
                # Get member count
                members_response = supabase.table('team_members').select('id', count='exact').eq('team_id', team['id']).execute()
                team['member_count'] = members_response.count if hasattr(members_response, 'count') else len(members_response.data) if members_response.data else 0
                
        except Exception as e:
            flash(f'Error fetching teams: {str(e)}', 'error')
    
    return render_template('settings/teams.html', teams=teams)


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
            
            # Fetch team credentials
            creds_response = supabase.table('ctfd_team_credentials').select('*').eq('team_id', team_id).execute()
            team_credentials = creds_response.data[0] if creds_response.data else None
            
            # Fetch team members with their credentials
            members_response = supabase.table('team_members').select('*').eq('team_id', team_id).execute()
            members = members_response.data if members_response.data else []
            
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
    """List all participants with their credentials."""
    supabase = get_supabase_client()
    participants = []
    
    if supabase:
        try:
            # Fetch all team members
            members_response = supabase.table('team_members').select('*').order('name').execute()
            participants = members_response.data if members_response.data else []
            
            # Get team names and credentials for each participant
            for participant in participants:
                # Get team name
                if participant.get('team_id'):
                    team_response = supabase.table('teams').select('team_name').eq('id', participant['team_id']).execute()
                    participant['team_name'] = team_response.data[0]['team_name'] if team_response.data else 'Unknown'
                else:
                    participant['team_name'] = 'No Team'
                
                # Get user credentials
                creds_response = supabase.table('ctfd_user_credentials').select('*').eq('member_id', participant['id']).execute()
                participant['credentials'] = creds_response.data[0] if creds_response.data else None
                
        except Exception as e:
            flash(f'Error fetching participants: {str(e)}', 'error')
    
    return render_template('settings/participants.html', participants=participants)
