from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.supabase_client import get_supabase_client
from app.models import User
from app import login_manager

auth_bp = Blueprint('auth', __name__)


@login_manager.user_loader
def load_user(user_id):
    """Load user from session for Flask-Login."""
    user_data = session.get('user_data')
    if user_data and user_data.get('id') == user_id:
        return User(user_data)
    return None


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login via Supabase Auth."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('auth/login.html')
        
        try:
            supabase = get_supabase_client()
            if not supabase:
                flash('Database connection not configured.', 'error')
                return render_template('auth/login.html')
            
            response = supabase.auth.sign_in_with_password({
                'email': email,
                'password': password
            })
            
            if response.user:
                user_data = {
                    'id': response.user.id,
                    'email': response.user.email,
                    'role': response.user.user_metadata.get('role', 'user'),
                    'created_at': str(response.user.created_at),
                    'user_metadata': response.user.user_metadata
                }
                session['user_data'] = user_data
                session['access_token'] = response.session.access_token
                
                user = User(user_data)
                login_user(user)
                
                flash('Successfully logged in!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('dashboard.index'))
            else:
                flash('Invalid email or password.', 'error')
        except Exception as e:
            flash(f'Login failed: {str(e)}', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration via Supabase Auth."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not email or not password:
            flash('Please fill in all fields.', 'error')
            return render_template('auth/register.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/register.html')
        
        try:
            supabase = get_supabase_client()
            if not supabase:
                flash('Database connection not configured.', 'error')
                return render_template('auth/register.html')
            
            response = supabase.auth.sign_up({
                'email': email,
                'password': password
            })
            
            if response.user:
                flash('Registration successful! Please check your email to verify your account.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('Registration failed. Please try again.', 'error')
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'error')
    
    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout."""
    try:
        supabase = get_supabase_client()
        if supabase:
            supabase.auth.sign_out()
    except Exception:
        pass
    
    session.clear()
    logout_user()
    flash('Successfully logged out.', 'success')
    return redirect(url_for('auth.login'))
