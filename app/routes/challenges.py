from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.supabase_client import get_supabase_client
from app.ctfd_client import CTFdAPIClient, CTFdAPIException
from app.utils import get_ctfd_config
import requests
import yaml
import os
import logging

challenges_bp = Blueprint('challenges', __name__)

# Configure logger
logger = logging.getLogger(__name__)

# Fields that can be edited in the portal
EDITABLE_CHALLENGE_FIELDS = ['name', 'category', 'difficulty', 'description', 'points', 'flag', 'hint', 'solution']


def _fetch_artifacts_recursive(repo_owner, repo_name, path, branch, github_token, base_path=None):
    """
    Recursively fetch all files and folders in the challenge directory.
    Returns a list of artifact dictionaries with name, type, path, and children.
    """
    # Validate required parameters
    if not repo_owner or not repo_name or not github_token or not path:
        return []
    
    if base_path is None:
        base_path = path
    
    artifacts = []
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    contents_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{path}?ref={branch}'
    
    try:
        response = requests.get(contents_url, headers=headers, timeout=10)
        if response.status_code == 200:
            items = response.json()
            if isinstance(items, list):
                for item in items:
                    item_name = item.get('name', '')
                    item_type = item.get('type', '')
                    item_path = item.get('path', '')
                    
                    # Calculate relative path from challenge directory
                    relative_path = item_path[len(base_path):].lstrip('/')
                    
                    artifact = {
                        'name': item_name,
                        'type': item_type,
                        'path': item_path,
                        'relative_path': relative_path,
                        'size': item.get('size', 0),
                        'download_url': item.get('download_url'),
                        'html_url': item.get('html_url'),
                        'children': []
                    }
                    
                    # Recursively fetch contents of directories
                    if item_type == 'dir':
                        artifact['children'] = _fetch_artifacts_recursive(
                            repo_owner, repo_name, item_path, branch, github_token, base_path
                        )
                    
                    artifacts.append(artifact)
    except requests.exceptions.RequestException:
        # Network or API errors - return empty list silently
        pass
    
    return artifacts


@challenges_bp.route('/challenges')
@login_required
def list_challenges():
    """List all challenges with filtering options."""
    supabase = get_supabase_client()
    
    # Get filter parameters
    category_filter = request.args.get('category', '')
    difficulty_filter = request.args.get('difficulty', '')
    status_filter = request.args.get('status', '')
    setter_filter = request.args.get('setter', '')
    
    challenges = []
    categories = set()
    difficulties = set()
    setters = set()
    
    if supabase:
        try:
            query = supabase.table('challenges').select('*')
            
            if category_filter:
                query = query.eq('category', category_filter)
            if difficulty_filter:
                query = query.eq('difficulty', difficulty_filter)
            if status_filter:
                query = query.eq('status', status_filter)
            if setter_filter:
                query = query.eq('setter', setter_filter)
            
            response = query.execute()
            challenges = response.data if response.data else []
            
            # Get all unique values for filters
            all_challenges_response = supabase.table('challenges').select('category, difficulty, setter').execute()
            if all_challenges_response.data:
                for c in all_challenges_response.data:
                    if c.get('category'):
                        categories.add(c['category'])
                    if c.get('difficulty'):
                        difficulties.add(c['difficulty'])
                    if c.get('setter'):
                        setters.add(c['setter'])
                        
        except Exception as e:
            flash(f'Error fetching challenges: {str(e)}', 'error')
    
    return render_template('challenges/list.html',
                         challenges=challenges,
                         categories=sorted(categories),
                         difficulties=sorted(difficulties),
                         setters=sorted(setters),
                         current_filters={
                             'category': category_filter,
                             'difficulty': difficulty_filter,
                             'status': status_filter,
                             'setter': setter_filter
                         })


@challenges_bp.route('/challenges/<int:challenge_id>')
@login_required
def view_challenge(challenge_id):
    """View a specific challenge's details."""
    supabase = get_supabase_client()
    challenge = None
    readme_content = None
    challenge_yml = None
    rounds = []
    artifacts = []
    
    if supabase:
        try:
            response = supabase.table('challenges').select('*').eq('id', challenge_id).single().execute()
            challenge = response.data
            
            # Fetch rounds for the round selector
            try:
                rounds_response = supabase.table('rounds').select('*').execute()
                rounds = rounds_response.data if rounds_response.data else []
            except Exception:
                rounds = []
            
            if challenge:
                # Try to fetch README.md and challenge.yml from GitHub
                github_token = current_app.config.get('GITHUB_TOKEN')
                repo_owner = current_app.config.get('GITHUB_REPO_OWNER')
                repo_name = current_app.config.get('GITHUB_REPO_NAME')
                
                if github_token and repo_owner and repo_name:
                    category = challenge.get('category', '')
                    name = challenge.get('name', '')
                    branch = challenge.get('branch', 'main')
                    
                    headers = {
                        'Authorization': f'token {github_token}',
                        'Accept': 'application/vnd.github.v3.raw'
                    }
                    
                    # Fetch README.md
                    readme_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{category}/{name}/README.md?ref={branch}'
                    try:
                        readme_response = requests.get(readme_url, headers=headers, timeout=10)
                        if readme_response.status_code == 200:
                            readme_content = readme_response.text
                    except Exception:
                        pass
                    
                    # Fetch challenge.yml
                    yml_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{category}/{name}/challenge.yml?ref={branch}'
                    try:
                        yml_response = requests.get(yml_url, headers=headers, timeout=10)
                        if yml_response.status_code == 200:
                            challenge_yml = yaml.safe_load(yml_response.text)
                    except Exception:
                        pass
                    
                    # Fetch artifacts (files and folders in challenge directory)
                    artifacts = _fetch_artifacts_recursive(
                        repo_owner, repo_name, f'{category}/{name}', branch, github_token
                    )
                        
        except Exception as e:
            flash(f'Error fetching challenge: {str(e)}', 'error')
    
    if not challenge:
        flash('Challenge not found.', 'error')
        return redirect(url_for('challenges.list_challenges'))
    
    # Get GitHub repo info for PR linking
    github_repo_owner = current_app.config.get('GITHUB_REPO_OWNER', '')
    github_repo_name = current_app.config.get('GITHUB_REPO_NAME', '')
    
    return render_template('challenges/view.html',
                         challenge=challenge,
                         readme_content=readme_content,
                         challenge_yml=challenge_yml,
                         rounds=rounds,
                         artifacts=artifacts,
                         github_repo_owner=github_repo_owner,
                         github_repo_name=github_repo_name)


@challenges_bp.route('/challenges/<int:challenge_id>/push-to-ctfd', methods=['POST'])
@login_required
def push_to_ctfd(challenge_id):
    """Push a challenge to CTFd with configurable fields and settings."""
    supabase = get_supabase_client()
    
    if not supabase:
        logger.error("Database not configured")
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Get push configuration from request body
        config = request.get_json() or {}
        fields_config = config.get('fields', {})
        settings_config = config.get('settings', {})
        dynamic_scoring_config = config.get('dynamic_scoring', {})
        
        # Set defaults for configuration if not provided
        if not fields_config:
            fields_config = {
                'name': True,
                'category': True,
                'description': True,
                'value': True,
                'flag': True,
                'connection_info': True,
                'attribution': True,
                'requirements': False
            }
        
        if not settings_config:
            settings_config = {
                'type': 'standard',
                'state': 'hidden',
                'max_attempts': 0
            }
        
        # Get challenge info
        logger.info(f"Fetching challenge {challenge_id} from database")
        response = supabase.table('challenges').select('*').eq('id', challenge_id).single().execute()
        challenge = response.data
        
        if not challenge:
            logger.warning(f"Challenge {challenge_id} not found")
            return jsonify({'error': 'Challenge not found'}), 404
        
        # Get CTFd configuration from database settings
        ctfd_url, ctfd_api_key = get_ctfd_config()
        
        # Initialize CTFd client (validates configuration)
        try:
            ctfd_client = CTFdAPIClient(ctfd_url, ctfd_api_key)
        except CTFdAPIException as e:
            logger.error(f"CTFd configuration error: {e.message}")
            return jsonify(e.to_dict()), 500
        
        # Fetch challenge.yml from GitHub for additional metadata
        challenge_yml = None
        github_token = current_app.config.get('GITHUB_TOKEN')
        repo_owner = current_app.config.get('GITHUB_REPO_OWNER')
        repo_name = current_app.config.get('GITHUB_REPO_NAME')
        
        if github_token and repo_owner and repo_name:
            category = challenge.get('category', '')
            name = challenge.get('name', '')
            branch = challenge.get('branch', 'main')
            
            # Sanitize path components to prevent path traversal
            # GitHub API doesn't allow '..' in paths, but we validate to be safe
            if category and name and '..' not in category and '..' not in name:
                headers = {
                    'Authorization': f'token {github_token}',
                    'Accept': 'application/vnd.github.v3.raw'
                }
                
                yml_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{category}/{name}/challenge.yml?ref={branch}'
                try:
                    logger.info(f"Fetching challenge.yml from GitHub for challenge {challenge_id}")
                    yml_response = requests.get(yml_url, headers=headers, timeout=10)
                    if yml_response.status_code == 200:
                        challenge_yml = yaml.safe_load(yml_response.text)
                        logger.debug(f"Successfully loaded challenge.yml for challenge {challenge_id}")
                except Exception as e:
                    logger.warning(f"Could not fetch challenge.yml: {str(e)}")
            else:
                logger.warning(f"Invalid category or name for challenge {challenge_id}, skipping challenge.yml fetch")
        
        # Prepare challenge data for CTFd based on configuration
        ctfd_challenge = {
            'name': challenge.get('name'),  # Always required
            'category': challenge.get('category'),  # Always required
            'value': challenge.get('points', 100),  # Always required
            'type': settings_config.get('type', 'standard'),
            'state': settings_config.get('state', 'hidden')
        }
        
        # Add description if configured
        if fields_config.get('description', True):
            ctfd_challenge['description'] = challenge.get('description', '')
        
        # Add max_attempts from settings
        max_attempts = settings_config.get('max_attempts', 0)
        if max_attempts > 0:
            ctfd_challenge['max_attempts'] = max_attempts
        
        # Add connection_info if configured and available from challenge.yml
        if fields_config.get('connection_info', True) and challenge_yml and 'connection_info' in challenge_yml:
            ctfd_challenge['connection_info'] = challenge_yml['connection_info']
        
        # Add attribution if configured and available
        if fields_config.get('attribution', True):
            if challenge_yml and ('attribution' in challenge_yml or 'author' in challenge_yml):
                ctfd_challenge['attribution'] = challenge_yml.get('attribution') or challenge_yml.get('author')
        
        # Add requirements if configured and available
        if fields_config.get('requirements', False) and challenge_yml and 'requirements' in challenge_yml:
            ctfd_challenge['requirements'] = challenge_yml['requirements']
        
        # Add extra metadata if specified in challenge.yml
        if challenge_yml and 'extra' in challenge_yml:
            ctfd_challenge['extra'] = challenge_yml['extra']
        
        # Add dynamic scoring fields if type is 'dynamic'
        # Prefer values from challenge.yml, fall back to values from request config
        if settings_config.get('type') == 'dynamic':
            # Initial value
            if challenge_yml and 'initial' in challenge_yml:
                ctfd_challenge['initial'] = challenge_yml['initial']
            elif dynamic_scoring_config.get('initial') is not None:
                ctfd_challenge['initial'] = dynamic_scoring_config['initial']
            
            # Minimum value
            if challenge_yml and 'minimum' in challenge_yml:
                ctfd_challenge['minimum'] = challenge_yml['minimum']
            elif dynamic_scoring_config.get('minimum') is not None:
                ctfd_challenge['minimum'] = dynamic_scoring_config['minimum']
            
            # Decay value
            if challenge_yml and 'decay' in challenge_yml:
                ctfd_challenge['decay'] = challenge_yml['decay']
            elif dynamic_scoring_config.get('decay') is not None:
                ctfd_challenge['decay'] = dynamic_scoring_config['decay']
            
            # Function type
            if challenge_yml and 'function' in challenge_yml:
                ctfd_challenge['function'] = challenge_yml['function']
            elif dynamic_scoring_config.get('function'):
                ctfd_challenge['function'] = dynamic_scoring_config['function']
        
        # Determine if flag should be pushed
        flag_content = None
        if fields_config.get('flag', True):
            flag_content = challenge.get('flag')
        
        # Push challenge and flag using the client with transaction-like behavior
        try:
            result = ctfd_client.push_challenge_with_flag(
                challenge_data=ctfd_challenge,
                flag_content=flag_content,
                flag_type='static'
            )
            
            ctfd_id = result['challenge']['id']
            
            # Update challenge with CTFd ID
            logger.info(f"Updating challenge {challenge_id} with CTFd ID {ctfd_id}")
            supabase.table('challenges').update({
                'ctfd_id': ctfd_id,
                'pushed_to_ctfd': True
            }).eq('id', challenge_id).execute()
            
            logger.info(f"Challenge {challenge_id} successfully pushed to CTFd with ID {ctfd_id}")
            
            # Build detailed message - only include fields that were actually pushed with content
            pushed_fields = []
            if fields_config.get('description', True) and ctfd_challenge.get('description'):
                pushed_fields.append('description')
            if fields_config.get('flag', True) and flag_content:
                pushed_fields.append('flag')
            if fields_config.get('connection_info', True) and ctfd_challenge.get('connection_info'):
                pushed_fields.append('connection info')
            if fields_config.get('attribution', True) and ctfd_challenge.get('attribution'):
                pushed_fields.append('attribution')
            if fields_config.get('requirements', False) and ctfd_challenge.get('requirements'):
                pushed_fields.append('requirements')
            
            message = f'Challenge pushed to CTFd successfully with state: {settings_config.get("state", "hidden")}'
            if pushed_fields:
                message += f'. Included: {", ".join(pushed_fields)}'
            
            return jsonify({
                'success': True,
                'message': message,
                'ctfd_id': ctfd_id,
                'flag_created': result['flag'] is not None,
                'settings': settings_config
            })
            
        except CTFdAPIException as e:
            logger.error(f"CTFd API error while pushing challenge {challenge_id}: {e.message}")
            return jsonify(e.to_dict()), 400
            
    except Exception as e:
        logger.exception(f"Unexpected error while pushing challenge {challenge_id} to CTFd")
        return jsonify({
            'error': 'An unexpected error occurred',
            'details': str(e)
        }), 500


@challenges_bp.route('/challenges/<int:challenge_id>/assign-round', methods=['POST'])
@login_required
def assign_round(challenge_id):
    """Assign a challenge to a round."""
    supabase = get_supabase_client()
    
    if supabase:
        try:
            data = request.json
            round_id = data.get('round_id')
            
            # Verify challenge exists
            existing = supabase.table('challenges').select('id').eq('id', challenge_id).execute()
            if not existing.data:
                return jsonify({'error': 'Challenge not found'}), 404
            
            # If round_id is provided, verify it exists
            if round_id:
                round_exists = supabase.table('rounds').select('id').eq('id', round_id).execute()
                if not round_exists.data:
                    return jsonify({'error': 'Round not found'}), 404
            
            # Update challenge with round_id (None if not provided)
            supabase.table('challenges').update({
                'round_id': round_id if round_id else None
            }).eq('id', challenge_id).execute()
            
            return jsonify({'success': True, 'message': 'Challenge assigned to round successfully'})
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Database not configured'}), 500


@challenges_bp.route('/challenges/<int:challenge_id>/update', methods=['POST'])
@login_required
def update_challenge(challenge_id):
    """Update challenge details from the portal."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Get the update data from request
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Verify challenge exists
        existing = supabase.table('challenges').select('*').eq('id', challenge_id).execute()
        if not existing.data:
            return jsonify({'error': 'Challenge not found'}), 404
        
        # Build update object with allowed fields
        update_data = {}
        
        for field in EDITABLE_CHALLENGE_FIELDS:
            if field in data:
                update_data[field] = data[field]
        
        if not update_data:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        # Update the challenge
        supabase.table('challenges').update(update_data).eq('id', challenge_id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Challenge updated successfully'
        })
        
    except Exception as e:
        logger.exception(f"Error updating challenge {challenge_id}")
        return jsonify({'error': str(e)}), 500
