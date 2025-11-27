from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required
from app.supabase_client import get_supabase_client
import requests

api_bp = Blueprint('api', __name__)


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
    """Sync challenges from GitHub PRs."""
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
        
        # Fetch open PRs
        prs_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/pulls?state=open'
        prs_response = requests.get(prs_url, headers=headers, timeout=30)
        
        if prs_response.status_code != 200:
            return jsonify({'error': 'Failed to fetch PRs from GitHub'}), 500
        
        prs = prs_response.json()
        synced_count = 0
        
        for pr in prs:
            pr_number = pr['number']
            branch = pr['head']['ref']
            
            # Check if challenge already exists
            existing = supabase.table('challenges').select('id').eq('pr_number', pr_number).execute()
            
            if not existing.data:
                # Try to parse challenge info from PR
                challenge_data = {
                    'name': pr['title'],
                    'category': 'Unknown',
                    'difficulty': 'Medium',
                    'description': pr.get('body', ''),
                    'status': 'pending',
                    'pr_number': pr_number,
                    'branch': branch,
                    'setter': pr['user']['login']
                }
                
                supabase.table('challenges').insert(challenge_data).execute()
                synced_count += 1
        
        return jsonify({
            'success': True,
            'message': f'Synced {synced_count} new challenges from GitHub'
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
