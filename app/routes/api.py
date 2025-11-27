from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required
from app.supabase_client import get_supabase_client
import requests
import yaml

api_bp = Blueprint('api', __name__)


def fetch_challenge_yml(github_token, repo_owner, repo_name, branch):
    """Fetch and parse challenge.yml from a branch.
    
    Returns a dict with challenge data or None if not found.
    Searches for challenge.yml in all directories of the branch.
    """
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    try:
        # Get the tree of the branch to find challenge.yml files
        tree_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/git/trees/{branch}?recursive=1'
        tree_response = requests.get(tree_url, headers=headers, timeout=30)
        
        if tree_response.status_code != 200:
            return None
        
        tree_data = tree_response.json()
        challenge_files = [
            item['path'] for item in tree_data.get('tree', [])
            if item['path'].endswith('challenge.yml') or item['path'].endswith('challenge.yaml')
        ]
        
        if not challenge_files:
            return None
        
        # Fetch the first challenge.yml found
        challenge_path = challenge_files[0]
        raw_headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3.raw'
        }
        
        content_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{challenge_path}?ref={branch}'
        content_response = requests.get(content_url, headers=raw_headers, timeout=30)
        
        if content_response.status_code != 200:
            return None
        
        yml_content = yaml.safe_load(content_response.text)
        
        # Handle nested 'challenge' key if present
        if 'challenge' in yml_content:
            yml_content = yml_content['challenge']
        
        # Extract challenge directory info for category if not specified
        path_parts = challenge_path.split('/')
        dir_category = path_parts[0] if len(path_parts) > 1 else None
        
        return {
            'yml': yml_content,
            'dir_category': dir_category,
            'path': challenge_path
        }
        
    except Exception:
        return None


def normalize_category(category, settings_categories=None):
    """Normalize category name for case-insensitive matching.
    
    If settings_categories is provided, try to match the category
    case-insensitively and return the proper-cased version from settings.
    """
    if not category:
        return 'Unknown'
    
    if settings_categories:
        # Try to find a case-insensitive match
        for settings_cat in settings_categories:
            if settings_cat.lower() == category.lower():
                return settings_cat
    
    # Return the category with first letter capitalized
    return category.capitalize() if category else 'Unknown'


def get_settings_categories(supabase):
    """Get categories from settings."""
    try:
        response = supabase.table('settings').select('value').eq('key', 'categories').execute()
        if response.data and response.data[0].get('value'):
            return [cat.strip() for cat in response.data[0]['value'].split(',')]
    except Exception:
        pass
    return None


@api_bp.route('/challenges', methods=['GET'])
@login_required
def get_challenges():
    """Get all challenges with optional filters."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        category = request.args.get('category')
        difficulty = request.args.get('difficulty')
        status = request.args.get('status')
        setter = request.args.get('setter')
        
        query = supabase.table('challenges').select('*')
        
        if category:
            query = query.eq('category', category)
        if difficulty:
            query = query.eq('difficulty', difficulty)
        if status:
            query = query.eq('status', status)
        if setter:
            query = query.eq('setter', setter)
        
        response = query.execute()
        return jsonify({'data': response.data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/challenges', methods=['POST'])
@login_required
def create_challenge():
    """Create a new challenge."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        required_fields = ['name', 'category']
        
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        challenge_data = {
            'name': data.get('name'),
            'category': data.get('category'),
            'difficulty': data.get('difficulty', 'Medium'),
            'description': data.get('description', ''),
            'points': data.get('points', 100),
            'flag': data.get('flag', ''),
            'setter': data.get('setter', ''),
            'status': 'pending',
            'pr_number': data.get('pr_number'),
            'branch': data.get('branch', '')
        }
        
        response = supabase.table('challenges').insert(challenge_data).execute()
        return jsonify({'data': response.data[0] if response.data else None}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/challenges/<int:challenge_id>', methods=['PUT'])
@login_required
def update_challenge(challenge_id):
    """Update a challenge."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.json
        
        response = supabase.table('challenges').update(data).eq('id', challenge_id).execute()
        return jsonify({'data': response.data[0] if response.data else None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/challenges/<int:challenge_id>', methods=['DELETE'])
@login_required
def delete_challenge(challenge_id):
    """Delete a challenge."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        supabase.table('challenges').delete().eq('id', challenge_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/sync-github', methods=['POST'])
@login_required
def sync_github():
    """Sync challenges from GitHub PRs and update data from challenge.yml."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    github_token = current_app.config.get('GITHUB_TOKEN')
    repo_owner = current_app.config.get('GITHUB_REPO_OWNER')
    repo_name = current_app.config.get('GITHUB_REPO_NAME')
    
    if not github_token or not repo_owner or not repo_name:
        return jsonify({'error': 'GitHub configuration missing'}), 500
    
    try:
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Get categories from settings for case-insensitive matching
        settings_categories = get_settings_categories(supabase)
        
        # Fetch open PRs
        prs_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/pulls?state=open'
        prs_response = requests.get(prs_url, headers=headers, timeout=30)
        
        if prs_response.status_code != 200:
            return jsonify({'error': 'Failed to fetch PRs from GitHub'}), 500
        
        prs = prs_response.json()
        synced_count = 0
        updated_count = 0
        
        for pr in prs:
            pr_number = pr['number']
            branch = pr['head']['ref']
            
            # Fetch challenge.yml from the branch
            challenge_yml_data = fetch_challenge_yml(github_token, repo_owner, repo_name, branch)
            
            # Build challenge data from challenge.yml or PR info
            if challenge_yml_data and challenge_yml_data.get('yml'):
                yml = challenge_yml_data['yml']
                dir_category = challenge_yml_data.get('dir_category')
                
                # Get category from yml or directory name, normalize it
                raw_category = yml.get('Category') or yml.get('category') or dir_category
                category = normalize_category(raw_category, settings_categories)
                
                # Get difficulty with proper case handling
                raw_difficulty = yml.get('Difficulty') or yml.get('difficulty') or 'Medium'
                difficulty = raw_difficulty.capitalize() if isinstance(raw_difficulty, str) else 'Medium'
                
                challenge_data = {
                    'name': yml.get('Name') or yml.get('name') or pr['title'],
                    'category': category,
                    'difficulty': difficulty,
                    'points': yml.get('Point') or yml.get('point') or yml.get('Points') or yml.get('points') or 100,
                    'flag': yml.get('Flag') or yml.get('flag') or '',
                    'description': yml.get('Description') or yml.get('description') or pr.get('body', ''),
                    'hint': yml.get('Hint') or yml.get('hint') or '',
                    'solution': yml.get('Solution') or yml.get('solution') or '',
                    'status': 'pending',
                    'pr_number': pr_number,
                    'branch': branch,
                    'setter': pr['user']['login']
                }
            else:
                # Fallback to PR info if no challenge.yml found
                challenge_data = {
                    'name': pr['title'],
                    'category': 'Unknown',
                    'difficulty': 'Medium',
                    'points': 100,
                    'description': pr.get('body', ''),
                    'status': 'pending',
                    'pr_number': pr_number,
                    'branch': branch,
                    'setter': pr['user']['login']
                }
            
            # Check if challenge already exists
            existing = supabase.table('challenges').select('id').eq('pr_number', pr_number).execute()
            
            if existing.data:
                # Update existing challenge with new data from challenge.yml
                challenge_id = existing.data[0]['id']
                # Remove status and setter from update to preserve existing values
                update_data = {k: v for k, v in challenge_data.items() if k not in ['status', 'setter', 'pr_number', 'branch']}
                supabase.table('challenges').update(update_data).eq('id', challenge_id).execute()
                updated_count += 1
            else:
                # Insert new challenge
                supabase.table('challenges').insert(challenge_data).execute()
                synced_count += 1
        
        return jsonify({
            'success': True,
            'message': f'Synced {synced_count} new challenges, updated {updated_count} existing from GitHub'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/settings', methods=['GET'])
@login_required
def get_settings():
    """Get all settings."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        response = supabase.table('settings').select('*').execute()
        settings = {}
        if response.data:
            for setting in response.data:
                settings[setting['key']] = setting['value']
        return jsonify({'data': settings})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/targets', methods=['GET'])
@login_required
def get_targets():
    """Get all targets."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        response = supabase.table('targets').select('*').execute()
        return jsonify({'data': response.data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/categories', methods=['GET'])
@login_required
def get_categories():
    """Get categories from settings."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        categories = get_settings_categories(supabase) or []
        return jsonify({'data': categories})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/difficulties', methods=['GET'])
@login_required
def get_difficulties():
    """Get difficulties from settings."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        response = supabase.table('settings').select('value').eq('key', 'difficulties').execute()
        difficulties = []
        if response.data and response.data[0].get('value'):
            difficulties = [d.strip() for d in response.data[0]['value'].split(',')]
        return jsonify({'data': difficulties})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/rounds', methods=['GET'])
@login_required
def get_rounds():
    """Get all rounds."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        response = supabase.table('rounds').select('*').execute()
        return jsonify({'data': response.data if response.data else []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/rounds', methods=['POST'])
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
        
        round_data = {
            'name': name,
            'description': data.get('description', '')
        }
        
        response = supabase.table('rounds').insert(round_data).execute()
        return jsonify({'data': response.data[0] if response.data else None}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/rounds/<int:round_id>', methods=['DELETE'])
@login_required
def delete_round(round_id):
    """Delete a round."""
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        supabase.table('rounds').delete().eq('id', round_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
