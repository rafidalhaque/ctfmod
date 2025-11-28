from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.supabase_client import get_supabase_client

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    """Render the main dashboard with challenge statistics."""
    supabase = get_supabase_client()
    
    # Initialize default stats
    stats = {
        'total_challenges': 0,
        'accepted_challenges': 0,
        'pending_challenges': 0,
        'declined_challenges': 0,
        'by_category': {},
        'by_difficulty': {},
        'by_target': {},  # Stats organized by target (category + difficulty + round)
        'targets': {}
    }
    
    challenges = []
    targets = []
    rounds = []
    settings = {}
    
    if supabase:
        try:
            # Fetch challenges
            challenges_response = supabase.table('challenges').select('*').execute()
            challenges = challenges_response.data if challenges_response.data else []
            
            # Fetch rounds
            try:
                rounds_response = supabase.table('rounds').select('*').execute()
                rounds = rounds_response.data if rounds_response.data else []
            except Exception:
                rounds = []
            
            # Fetch settings (for auto_sync_interval)
            try:
                settings_response = supabase.table('settings').select('*').execute()
                if settings_response.data:
                    for setting in settings_response.data:
                        settings[setting['key']] = setting['value']
            except Exception:
                settings = {}
            
            # Calculate statistics
            stats['total_challenges'] = len(challenges)
            for challenge in challenges:
                status = challenge.get('status', 'pending')
                category = challenge.get('category', 'Unknown')
                difficulty = challenge.get('difficulty', 'Unknown')
                round_id = challenge.get('round_id')
                
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
                if status == 'accepted':
                    stats['by_category'][category]['accepted'] += 1
                elif status == 'pending':
                    stats['by_category'][category]['pending'] += 1
                elif status == 'declined':
                    stats['by_category'][category]['declined'] += 1
                
                # Count by difficulty
                if difficulty not in stats['by_difficulty']:
                    stats['by_difficulty'][difficulty] = {'total': 0, 'accepted': 0, 'pending': 0, 'declined': 0}
                stats['by_difficulty'][difficulty]['total'] += 1
                if status == 'accepted':
                    stats['by_difficulty'][difficulty]['accepted'] += 1
                elif status == 'pending':
                    stats['by_difficulty'][difficulty]['pending'] += 1
                elif status == 'declined':
                    stats['by_difficulty'][difficulty]['declined'] += 1
                
                # Count by target key (category + difficulty + round)
                round_key = str(round_id) if round_id else 'all'
                target_key = f"{category}_{difficulty}_{round_key}"
                if target_key not in stats['by_target']:
                    stats['by_target'][target_key] = {'total': 0, 'accepted': 0, 'pending': 0, 'declined': 0}
                stats['by_target'][target_key]['total'] += 1
                if status == 'accepted':
                    stats['by_target'][target_key]['accepted'] += 1
                elif status == 'pending':
                    stats['by_target'][target_key]['pending'] += 1
                elif status == 'declined':
                    stats['by_target'][target_key]['declined'] += 1
            
            # Fetch targets
            targets_response = supabase.table('targets').select('*').execute()
            targets = targets_response.data if targets_response.data else []
            
            for target in targets:
                key = f"{target.get('category', 'Unknown')}_{target.get('difficulty', 'Unknown')}"
                stats['targets'][key] = target.get('target_count', 0)
                
        except Exception as e:
            print(f"Error fetching dashboard data: {e}")
    
    return render_template('dashboard/index.html', 
                         stats=stats, 
                         challenges=challenges,
                         targets=targets,
                         rounds=rounds,
                         settings=settings)


@dashboard_bp.route('/api/stats')
@login_required
def get_stats():
    """API endpoint to get dashboard statistics."""
    supabase = get_supabase_client()
    
    stats = {
        'total_challenges': 0,
        'accepted_challenges': 0,
        'pending_challenges': 0,
        'declined_challenges': 0,
        'by_category': {},
        'by_difficulty': {}
    }
    
    if supabase:
        try:
            challenges_response = supabase.table('challenges').select('*').execute()
            challenges = challenges_response.data if challenges_response.data else []
            
            stats['total_challenges'] = len(challenges)
            for challenge in challenges:
                status = challenge.get('status', 'pending')
                category = challenge.get('category', 'Unknown')
                difficulty = challenge.get('difficulty', 'Unknown')
                
                if status == 'accepted':
                    stats['accepted_challenges'] += 1
                elif status == 'pending':
                    stats['pending_challenges'] += 1
                elif status == 'declined':
                    stats['declined_challenges'] += 1
                
                if category not in stats['by_category']:
                    stats['by_category'][category] = {'total': 0, 'accepted': 0, 'pending': 0, 'declined': 0}
                stats['by_category'][category]['total'] += 1
                stats['by_category'][category][status] = stats['by_category'][category].get(status, 0) + 1
                
                if difficulty not in stats['by_difficulty']:
                    stats['by_difficulty'][difficulty] = {'total': 0, 'accepted': 0, 'pending': 0, 'declined': 0}
                stats['by_difficulty'][difficulty]['total'] += 1
                stats['by_difficulty'][difficulty][status] = stats['by_difficulty'][difficulty].get(status, 0) + 1
                
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify(stats)
