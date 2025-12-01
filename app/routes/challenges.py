from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.supabase_client import get_supabase_client
import requests
import yaml
import os

challenges_bp = Blueprint('challenges', __name__)


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
    
    return render_template('challenges/view.html',
                         challenge=challenge,
                         readme_content=readme_content,
                         challenge_yml=challenge_yml,
                         rounds=rounds,
                         artifacts=artifacts)


@challenges_bp.route('/challenges/<int:challenge_id>/approve', methods=['POST'])
@login_required
def approve_challenge(challenge_id):
    """Approve a challenge by merging its PR."""
    supabase = get_supabase_client()
    
    if supabase:
        try:
            # Get challenge info
            response = supabase.table('challenges').select('*').eq('id', challenge_id).single().execute()
            challenge = response.data
            
            if not challenge:
                return jsonify({'error': 'Challenge not found'}), 404
            
            pr_number = challenge.get('pr_number')
            if not pr_number:
                return jsonify({'error': 'No PR associated with this challenge'}), 400
            
            # Merge PR on GitHub
            github_token = current_app.config.get('GITHUB_TOKEN')
            repo_owner = current_app.config.get('GITHUB_REPO_OWNER')
            repo_name = current_app.config.get('GITHUB_REPO_NAME')
            
            if github_token and repo_owner and repo_name:
                headers = {
                    'Authorization': f'token {github_token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                merge_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/merge'
                merge_response = requests.put(merge_url, headers=headers, json={
                    'commit_title': f'Merge challenge: {challenge.get("name")}',
                    'merge_method': 'merge'
                }, timeout=30)
                
                if merge_response.status_code in [200, 201]:
                    # Update challenge status in database
                    supabase.table('challenges').update({'status': 'accepted'}).eq('id', challenge_id).execute()
                    return jsonify({'success': True, 'message': 'Challenge approved and PR merged'})
                else:
                    return jsonify({'error': f'Failed to merge PR: {merge_response.json().get("message", "Unknown error")}'}), 400
            else:
                return jsonify({'error': 'GitHub configuration missing'}), 500
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Database not configured'}), 500


@challenges_bp.route('/challenges/<int:challenge_id>/decline', methods=['POST'])
@login_required
def decline_challenge(challenge_id):
    """Decline a challenge by closing its PR and deleting it from the portal.
    
    Closed PRs are treated as deleted - they should not appear in the portal.
    """
    supabase = get_supabase_client()
    
    if supabase:
        try:
            # Get challenge info
            response = supabase.table('challenges').select('*').eq('id', challenge_id).single().execute()
            challenge = response.data
            
            if not challenge:
                return jsonify({'error': 'Challenge not found'}), 404
            
            pr_number = challenge.get('pr_number')
            if not pr_number:
                return jsonify({'error': 'No PR associated with this challenge'}), 400
            
            # Close PR on GitHub
            github_token = current_app.config.get('GITHUB_TOKEN')
            repo_owner = current_app.config.get('GITHUB_REPO_OWNER')
            repo_name = current_app.config.get('GITHUB_REPO_NAME')
            
            if github_token and repo_owner and repo_name:
                headers = {
                    'Authorization': f'token {github_token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                close_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/pulls/{pr_number}'
                close_response = requests.patch(close_url, headers=headers, json={
                    'state': 'closed'
                }, timeout=30)
                
                if close_response.status_code == 200:
                    # Delete challenge from database since closed PRs should not appear in portal
                    supabase.table('challenges').delete().eq('id', challenge_id).execute()
                    return jsonify({'success': True, 'message': 'Challenge declined, PR closed, and removed from portal'})
                else:
                    return jsonify({'error': f'Failed to close PR: {close_response.json().get("message", "Unknown error")}'}), 400
            else:
                return jsonify({'error': 'GitHub configuration missing'}), 500
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Database not configured'}), 500


@challenges_bp.route('/challenges/<int:challenge_id>/request-changes', methods=['POST'])
@login_required
def request_changes(challenge_id):
    """Request changes on a challenge PR."""
    supabase = get_supabase_client()
    comment = request.json.get('comment', '')
    
    if not comment:
        return jsonify({'error': 'Comment is required'}), 400
    
    if supabase:
        try:
            # Get challenge info
            response = supabase.table('challenges').select('*').eq('id', challenge_id).single().execute()
            challenge = response.data
            
            if not challenge:
                return jsonify({'error': 'Challenge not found'}), 404
            
            pr_number = challenge.get('pr_number')
            if not pr_number:
                return jsonify({'error': 'No PR associated with this challenge'}), 400
            
            # Add review comment on GitHub
            github_token = current_app.config.get('GITHUB_TOKEN')
            repo_owner = current_app.config.get('GITHUB_REPO_OWNER')
            repo_name = current_app.config.get('GITHUB_REPO_NAME')
            
            if github_token and repo_owner and repo_name:
                headers = {
                    'Authorization': f'token {github_token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                review_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/reviews'
                review_response = requests.post(review_url, headers=headers, json={
                    'body': comment,
                    'event': 'REQUEST_CHANGES'
                }, timeout=30)
                
                if review_response.status_code in [200, 201]:
                    return jsonify({'success': True, 'message': 'Changes requested on PR'})
                else:
                    return jsonify({'error': f'Failed to request changes: {review_response.json().get("message", "Unknown error")}'}), 400
            else:
                return jsonify({'error': 'GitHub configuration missing'}), 500
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Database not configured'}), 500


@challenges_bp.route('/challenges/<int:challenge_id>/push-to-ctfd', methods=['POST'])
@login_required
def push_to_ctfd(challenge_id):
    """Push a challenge to CTFd."""
    supabase = get_supabase_client()
    
    if supabase:
        try:
            # Get challenge info
            response = supabase.table('challenges').select('*').eq('id', challenge_id).single().execute()
            challenge = response.data
            
            if not challenge:
                return jsonify({'error': 'Challenge not found'}), 404
            
            ctfd_url = current_app.config.get('CTFD_URL')
            ctfd_api_key = current_app.config.get('CTFD_API_KEY')
            
            if not ctfd_url or not ctfd_api_key:
                return jsonify({'error': 'CTFd configuration missing'}), 500
            
            headers = {
                'Authorization': f'Token {ctfd_api_key}',
                'Content-Type': 'application/json'
            }
            
            # Prepare challenge data for CTFd
            ctfd_challenge = {
                'name': challenge.get('name'),
                'category': challenge.get('category'),
                'description': challenge.get('description', ''),
                'value': challenge.get('points', 100),
                'type': 'standard',
                'state': 'hidden'
            }
            
            # Create challenge on CTFd
            create_url = f'{ctfd_url.rstrip("/")}/api/v1/challenges'
            create_response = requests.post(create_url, headers=headers, json=ctfd_challenge, timeout=30)
            
            if create_response.status_code in [200, 201]:
                ctfd_response = create_response.json()
                ctfd_id = ctfd_response.get('data', {}).get('id')
                
                # Update challenge with CTFd ID
                supabase.table('challenges').update({
                    'ctfd_id': ctfd_id,
                    'pushed_to_ctfd': True
                }).eq('id', challenge_id).execute()
                
                # Add flag if available
                flag = challenge.get('flag')
                if flag and ctfd_id:
                    flag_url = f'{ctfd_url.rstrip("/")}/api/v1/flags'
                    flag_data = {
                        'challenge_id': ctfd_id,
                        'content': flag,
                        'type': 'static'
                    }
                    requests.post(flag_url, headers=headers, json=flag_data, timeout=30)
                
                return jsonify({'success': True, 'message': 'Challenge pushed to CTFd', 'ctfd_id': ctfd_id})
            else:
                return jsonify({'error': f'Failed to create challenge on CTFd: {create_response.text}'}), 400
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Database not configured'}), 500


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
