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


def safe_int(value, default=None):
    """Attempt to convert value to int, returning default if conversion fails.
    
    Useful for safely parsing numeric values from YAML that may contain
    non-integer placeholders like 'tbd'.
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


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
        
        # Check content size to prevent DoS
        content_text = content_response.text
        if len(content_text) > MAX_YAML_SIZE:
            return None
        
        yml_content = yaml.safe_load(content_text)
        
        # Validate that yml_content is a dict
        if not isinstance(yml_content, dict):
            return None
        
        # Handle nested 'challenge' key if present
        if 'challenge' in yml_content and isinstance(yml_content['challenge'], dict):
            yml_content = yml_content['challenge']
        
        # Extract challenge directory info for category if not specified
        path_parts = challenge_path.split('/')
        dir_category = path_parts[0] if len(path_parts) > 1 else None
        
        return {
            'yml': yml_content,
            'dir_category': dir_category,
            'path': challenge_path
        }
        
    except YAMLError:
        # YAML parsing error - file has invalid YAML syntax
        return None
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


def detect_conflicts(existing_challenge, github_data):
    """Detect conflicts between portal-edited challenge and GitHub data.
    
    Args:
        existing_challenge: Current challenge data from database
        github_data: New challenge data from GitHub YAML
        
    Returns:
        dict with conflicting fields or None if no conflicts
    """
    # Get the original GitHub snapshot (before portal edits)
    github_snapshot = existing_challenge.get('github_data_snapshot', {})
    
    conflicts = {}
    
    for field in EDITABLE_CHALLENGE_FIELDS:
        current_value = existing_challenge.get(field)
        github_value = github_data.get(field)
        original_value = github_snapshot.get(field) if github_snapshot else None
        
        # Skip if both are None (but not empty strings or 0, which are valid)
        if current_value is None and github_value is None:
            continue
        
        # Conflict detected if:
        # 1. Current value differs from GitHub value
        # 2. GitHub value has changed from the original snapshot
        if current_value != github_value:
            # Check if GitHub data actually changed
            if github_value != original_value:
                conflicts[field] = {
                    'portal_value': current_value,
                    'github_value': github_value,
                    'original_value': original_value
                }
    
    return conflicts if conflicts else None


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


@api_bp.route('/sync-github', methods=['POST'])
@login_required
def sync_github():
    """Sync challenges from GitHub PRs and update data from challenge.yml.
    
    This function syncs challenges from open PRs and removes challenges
    whose PRs have been closed (but not merged). Only open, draft, and 
    merged PRs should be visible in the portal.
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
        
        # Get categories from settings for case-insensitive matching
        settings_categories = get_settings_categories(supabase)
        
        # Fetch open PRs
        prs_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/pulls?state=open'
        prs_response = requests.get(prs_url, headers=headers, timeout=30)
        
        if prs_response.status_code != 200:
            return jsonify({'error': 'Failed to fetch PRs from GitHub'}), 500
        
        prs = prs_response.json()
        open_pr_numbers = {pr['number'] for pr in prs}
        synced_count = 0
        updated_count = 0
        deleted_count = 0
        skipped_rejected = 0
        
        for pr in prs:
            pr_number = pr['number']
            branch = pr['head']['ref']
            
            # Skip PRs with 'rejected' label - these are declined challenges
            pr_labels = [label.get('name', '').lower() for label in pr.get('labels', [])]
            if 'rejected' in pr_labels:
                skipped_rejected += 1
                continue
            
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
                
                # Get points value from yml, using safe_int to handle non-integer values
                # Non-integer values (e.g., "tbd") result in -1 to indicate invalid/pending points
                # If no points key is found, default to 100
                points_value = yml.get('Point') or yml.get('point') or yml.get('Points') or yml.get('points')
                points = safe_int(points_value, default=-1) if points_value is not None else 100
                
                challenge_data = {
                    'name': yml.get('Name') or yml.get('name') or pr['title'],
                    'category': category,
                    'difficulty': difficulty,
                    'points': points,
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
            
            # Check if challenge already exists - select specific fields needed for conflict detection
            fields_to_select = 'id, manually_edited, github_data_snapshot, ' + ', '.join(EDITABLE_CHALLENGE_FIELDS)
            existing = supabase.table('challenges').select(fields_to_select).eq('pr_number', pr_number).execute()
            
            if existing.data:
                # Update existing challenge with new data from challenge.yml
                challenge_id = existing.data[0]['id']
                existing_challenge = existing.data[0]
                
                # Check if challenge was manually edited in portal
                if existing_challenge.get('manually_edited'):
                    # Detect conflicts between GitHub data and portal edits
                    conflicts = detect_conflicts(existing_challenge, challenge_data)
                    
                    if conflicts:
                        # Mark challenge as having conflicts
                        conflict_update = {
                            'has_conflicts': True,
                            'conflicting_fields': conflicts
                        }
                        supabase.table('challenges').update(conflict_update).eq('id', challenge_id).execute()
                        updated_count += 1
                    else:
                        # No conflicts, safe to update
                        update_data = {k: v for k, v in challenge_data.items() if k not in ['status', 'setter', 'pr_number', 'branch']}
                        supabase.table('challenges').update(update_data).eq('id', challenge_id).execute()
                        updated_count += 1
                else:
                    # No manual edits, safe to update from GitHub
                    update_data = {k: v for k, v in challenge_data.items() if k not in ['status', 'setter', 'pr_number', 'branch']}
                    supabase.table('challenges').update(update_data).eq('id', challenge_id).execute()
                    updated_count += 1
            else:
                # Insert new challenge
                supabase.table('challenges').insert(challenge_data).execute()
                synced_count += 1
        
        # Delete challenges whose PRs are now closed (not merged)
        # Get all challenges with pr_number that are not in open PRs and not accepted (merged)
        all_challenges = supabase.table('challenges').select('id, pr_number, status').execute()
        if all_challenges.data:
            for challenge in all_challenges.data:
                pr_num = challenge.get('pr_number')
                status = challenge.get('status')
                
                # Skip challenges without pr_number or that are already accepted (merged)
                if not pr_num or status == 'accepted':
                    continue
                
                # If the PR is not in open PRs, check if it's merged or closed
                if pr_num not in open_pr_numbers:
                    # Check PR status on GitHub
                    pr_check_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/pulls/{pr_num}'
                    pr_check_response = requests.get(pr_check_url, headers=headers, timeout=30)
                    
                    if pr_check_response.status_code == 200:
                        pr_data = pr_check_response.json()
                        pr_state = pr_data.get('state')
                        pr_merged = pr_data.get('merged', False)
                        
                        # Delete challenge if PR is closed and not merged
                        if pr_state == 'closed' and not pr_merged:
                            supabase.table('challenges').delete().eq('id', challenge['id']).execute()
                            deleted_count += 1
                    elif pr_check_response.status_code == 404:
                        # PR no longer exists (deleted), treat as closed and delete challenge
                        supabase.table('challenges').delete().eq('id', challenge['id']).execute()
                        deleted_count += 1
        
        # Save the last sync timestamp
        last_sync_time = datetime.now(timezone.utc).isoformat()
        supabase.table('settings').upsert({
            'key': 'last_sync_time',
            'value': last_sync_time
        }, on_conflict='key').execute()
        
        return jsonify({
            'success': True,
            'message': f'Synced {synced_count} new challenges, updated {updated_count} existing, deleted {deleted_count} closed PRs from GitHub',
            'last_sync_time': last_sync_time
        })
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


@api_bp.route('/challenges/<int:challenge_id>/resolve-conflicts', methods=['POST'])
@login_required
def resolve_conflicts(challenge_id):
    """Resolve sync conflicts for a challenge.
    
    Accepts a resolution strategy:
    - 'keep_portal': Keep all portal values
    - 'use_github': Use all GitHub values
    - 'merge': Use specific values for each field (requires field_resolutions)
    """
    supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({'error': 'Database not configured'}), 500
    
    try:
        data = request.get_json()
        resolution_type = data.get('resolution_type')
        field_resolutions = data.get('field_resolutions', {})
        
        if not resolution_type:
            return jsonify({'error': 'Resolution type is required'}), 400
        
        # Get challenge with conflicts
        existing = supabase.table('challenges').select('*').eq('id', challenge_id).execute()
        if not existing.data:
            return jsonify({'error': 'Challenge not found'}), 404
        
        challenge = existing.data[0]
        conflicting_fields = challenge.get('conflicting_fields', {})
        
        if not conflicting_fields:
            return jsonify({'error': 'No conflicts to resolve'}), 400
        
        # Build update data based on resolution strategy
        update_data = {}
        
        if resolution_type == 'keep_portal':
            # Keep all current portal values, just clear the conflict flags
            update_data = {
                'has_conflicts': False,
                'conflicting_fields': None,
                'github_data_snapshot': None,  # Reset snapshot
                'manually_edited': True  # Keep this flag
            }
        elif resolution_type == 'use_github':
            # Use all GitHub values
            for field, conflict_data in conflicting_fields.items():
                update_data[field] = conflict_data['github_value']
            update_data.update({
                'has_conflicts': False,
                'conflicting_fields': None,
                'github_data_snapshot': None,
                'manually_edited': False  # Reset since we're using GitHub values
            })
        elif resolution_type == 'merge':
            # Use field-specific resolutions
            if not field_resolutions:
                return jsonify({'error': 'Field resolutions required for merge strategy'}), 400
            
            for field, conflict_data in conflicting_fields.items():
                chosen_source = field_resolutions.get(field, 'portal')  # Default to portal
                if chosen_source == 'github':
                    update_data[field] = conflict_data['github_value']
                # If 'portal', we keep current value (no update needed)
            
            update_data.update({
                'has_conflicts': False,
                'conflicting_fields': None,
                'github_data_snapshot': None,
                'manually_edited': True  # Keep flag since we're keeping some portal values
            })
        else:
            return jsonify({'error': 'Invalid resolution type'}), 400
        
        # Apply the resolution
        supabase.table('challenges').update(update_data).eq('id', challenge_id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Conflicts resolved successfully'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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



