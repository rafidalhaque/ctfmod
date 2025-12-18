from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required
from app.supabase_client import get_supabase_client
import requests
import yaml
from yaml import YAMLError
import hmac
import base64
from datetime import datetime, timezone

api_bp = Blueprint('api', __name__)

# Maximum YAML content size (100KB) to prevent DoS
MAX_YAML_SIZE = 100 * 1024

# Fields that can be edited in the portal (shared with challenges module)
EDITABLE_CHALLENGE_FIELDS = ['name', 'category', 'difficulty', 'description', 'points', 'flag', 'hint', 'solution']


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
    """Create a new challenge directly in the portal."""
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
            'hint': data.get('hint', ''),
            'solution': data.get('solution', ''),
            'setter': data.get('setter', ''),
            'status': data.get('status', 'pending'),
            'round_id': data.get('round_id')
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


@api_bp.route('/export-to-github', methods=['POST'])
@login_required
def export_to_github():
    """Export all challenges to GitHub main branch in category/name folder structure.
    
    Creates/updates challenge files on GitHub main branch with:
    - README.md: Challenge description
    - challenge.yml: Challenge metadata
    - Each challenge in its own folder: category/name/
    """
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
        
        # Fetch all challenges from database
        response = supabase.table('challenges').select('*').execute()
        challenges = response.data if response.data else []
        
        if not challenges:
            return jsonify({'error': 'No challenges to export'}), 400
        
        exported_count = 0
        failed_count = 0
        errors = []
        
        for challenge in challenges:
            try:
                category = challenge.get('category', 'Unknown')
                name = challenge.get('name', 'Untitled')
                
                # Sanitize folder names (remove special characters)
                category = category.replace(' ', '_').replace('/', '_')
                name = name.replace(' ', '_').replace('/', '_')
                
                # Build paths
                base_path = f"{category}/{name}"
                readme_path = f"{base_path}/README.md"
                yml_path = f"{base_path}/challenge.yml"
                
                # Build README.md content
                readme_content = f"# {challenge.get('name', 'Untitled')}\n\n"
                if challenge.get('description'):
                    readme_content += f"{challenge.get('description')}\n\n"
                if challenge.get('hint'):
                    readme_content += f"## Hint\n{challenge.get('hint')}\n\n"
                if challenge.get('solution'):
                    readme_content += f"## Solution\n{challenge.get('solution')}\n\n"
                
                # Build challenge.yml content
                yml_content = {
                    'name': challenge.get('name', 'Untitled'),
                    'category': challenge.get('category', 'Unknown'),
                    'difficulty': challenge.get('difficulty', 'Medium'),
                    'points': challenge.get('points', 100),
                    'flag': challenge.get('flag', ''),
                    'description': challenge.get('description', ''),
                }
                
                if challenge.get('hint'):
                    yml_content['hint'] = challenge.get('hint')
                if challenge.get('solution'):
                    yml_content['solution'] = challenge.get('solution')
                if challenge.get('setter'):
                    yml_content['author'] = challenge.get('setter')
                
                yml_text = yaml.dump(yml_content, default_flow_style=False, sort_keys=False)
                
                # Check if files exist on GitHub
                import base64
                
                # Create/Update README.md
                readme_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{readme_path}'
                readme_get_response = requests.get(readme_url, headers=headers, timeout=10)
                
                readme_data = {
                    'message': f'Update challenge: {name}',
                    'content': base64.b64encode(readme_content.encode()).decode(),
                    'branch': 'main'
                }
                
                if readme_get_response.status_code == 200:
                    # File exists, update it
                    readme_data['sha'] = readme_get_response.json()['sha']
                
                readme_put_response = requests.put(readme_url, headers=headers, json=readme_data, timeout=30)
                
                # Create/Update challenge.yml
                yml_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{yml_path}'
                yml_get_response = requests.get(yml_url, headers=headers, timeout=10)
                
                yml_data = {
                    'message': f'Update challenge: {name}',
                    'content': base64.b64encode(yml_text.encode()).decode(),
                    'branch': 'main'
                }
                
                if yml_get_response.status_code == 200:
                    # File exists, update it
                    yml_data['sha'] = yml_get_response.json()['sha']
                
                yml_put_response = requests.put(yml_url, headers=headers, json=yml_data, timeout=30)
                
                if readme_put_response.status_code in [200, 201] and yml_put_response.status_code in [200, 201]:
                    exported_count += 1
                else:
                    failed_count += 1
                    errors.append(f"Failed to export {name}: README status {readme_put_response.status_code}, YML status {yml_put_response.status_code}")
                    
            except Exception as e:
                failed_count += 1
                errors.append(f"Error exporting {challenge.get('name', 'Unknown')}: {str(e)}")
        
        message = f'Exported {exported_count} challenges to GitHub main branch'
        if failed_count > 0:
            message += f', {failed_count} failed'
        
        return jsonify({
            'success': True,
            'message': message,
            'exported_count': exported_count,
            'failed_count': failed_count,
            'errors': errors if errors else None
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


def validate_api_key(api_key):
    """Validate API key against stored key in settings."""
    if not api_key:
        return False
    
    supabase = get_supabase_client()
    if not supabase:
        return False
    
    try:
        response = supabase.table('settings').select('value').eq('key', 'stats_api_key').execute()
        if response.data and response.data[0].get('value'):
            stored_key = response.data[0]['value']
            # Use constant-time comparison to prevent timing attacks
            return hmac.compare_digest(api_key, stored_key)
    except Exception:
        pass
    
    return False


@api_bp.route('/v1/stats', methods=['GET'])
def get_public_stats():
    """Public API endpoint to get detailed statistics.
    
    Requires API key authentication via X-API-Key header.
    
    Returns detailed stats including:
    - Total, accepted, pending, and declined challenges
    - Stats by category
    - Stats by difficulty
    - Stats by round
    - Target progress
    - Round schedules
    """
    # Validate API key
    api_key = request.headers.get('X-API-Key')
    
    if not validate_api_key(api_key):
        return jsonify({'error': 'Invalid or missing API key'}), 401
    
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        # Fetch all challenges
        challenges_response = supabase.table('challenges').select('*').execute()
        challenges = challenges_response.data if challenges_response.data else []
        
        # Fetch rounds
        rounds_response = supabase.table('rounds').select('*').execute()
        rounds = rounds_response.data if rounds_response.data else []
        
        # Fetch targets
        targets_response = supabase.table('targets').select('*').execute()
        targets = targets_response.data if targets_response.data else []
        
        # Build stats
        stats = {
            'total_challenges': len(challenges),
            'accepted_challenges': 0,
            'pending_challenges': 0,
            'declined_challenges': 0,
            'by_category': {},
            'by_difficulty': {},
            'by_round': {},
            'by_setter': {},
            'targets': [],
            'rounds': []
        }
        
        # Create rounds lookup
        rounds_lookup = {r['id']: r for r in rounds}
        
        for challenge in challenges:
            status = challenge.get('status', 'pending')
            category = challenge.get('category', 'Unknown')
            difficulty = challenge.get('difficulty', 'Unknown')
            round_id = challenge.get('round_id')
            setter = challenge.get('setter', 'Unknown')
            
            # Count by status
            if status == 'accepted':
                stats['accepted_challenges'] += 1
            elif status == 'pending':
                stats['pending_challenges'] += 1
            elif status == 'declined':
                stats['declined_challenges'] += 1
            
            # Count by category
            if category not in stats['by_category']:
                stats['by_category'][category] = {'total': 0, 'accepted': 0, 'pending': 0, 'declined': 0}
            stats['by_category'][category]['total'] += 1
            stats['by_category'][category][status] = stats['by_category'][category].get(status, 0) + 1
            
            # Count by difficulty
            if difficulty not in stats['by_difficulty']:
                stats['by_difficulty'][difficulty] = {'total': 0, 'accepted': 0, 'pending': 0, 'declined': 0}
            stats['by_difficulty'][difficulty]['total'] += 1
            stats['by_difficulty'][difficulty][status] = stats['by_difficulty'][difficulty].get(status, 0) + 1
            
            # Count by round
            round_name = rounds_lookup.get(round_id, {}).get('name', 'Unassigned') if round_id else 'Unassigned'
            if round_name not in stats['by_round']:
                stats['by_round'][round_name] = {'total': 0, 'accepted': 0, 'pending': 0, 'declined': 0}
            stats['by_round'][round_name]['total'] += 1
            stats['by_round'][round_name][status] = stats['by_round'][round_name].get(status, 0) + 1
            
            # Count by setter
            if setter not in stats['by_setter']:
                stats['by_setter'][setter] = {'total': 0, 'accepted': 0, 'pending': 0, 'declined': 0}
            stats['by_setter'][setter]['total'] += 1
            stats['by_setter'][setter][status] = stats['by_setter'][setter].get(status, 0) + 1
        
        # Build targets info with progress
        for target in targets:
            round_name = rounds_lookup.get(target.get('round_id'), {}).get('name', 'All Rounds') if target.get('round_id') else 'All Rounds'
            
            # Count accepted challenges for this target
            accepted_count = sum(
                1 for c in challenges
                if c.get('category') == target.get('category')
                and c.get('difficulty') == target.get('difficulty')
                and (
                    (target.get('round_id') is None) or 
                    (c.get('round_id') == target.get('round_id'))
                )
                and c.get('status') == 'accepted'
            )
            
            # Count pending challenges for this target
            pending_count = sum(
                1 for c in challenges
                if c.get('category') == target.get('category')
                and c.get('difficulty') == target.get('difficulty')
                and (
                    (target.get('round_id') is None) or 
                    (c.get('round_id') == target.get('round_id'))
                )
                and c.get('status') == 'pending'
            )
            
            # Progress counts both accepted and pending challenges
            progress_count = accepted_count + pending_count
            target_count = target.get('target_count', 0)
            
            stats['targets'].append({
                'category': target.get('category'),
                'difficulty': target.get('difficulty'),
                'round': round_name,
                'target_count': target_count,
                'accepted_count': accepted_count,
                'pending_count': pending_count,
                'progress_count': progress_count,
                'progress_percentage': round((progress_count / target_count) * 100, 2) if target_count > 0 else 0
            })
        
        # Build rounds info with schedule
        for round_item in rounds:
            stats['rounds'].append({
                'id': round_item.get('id'),
                'name': round_item.get('name'),
                'description': round_item.get('description'),
                'start_datetime': round_item.get('start_datetime'),
                'timezone': round_item.get('timezone', 'UTC')
            })
        
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500



