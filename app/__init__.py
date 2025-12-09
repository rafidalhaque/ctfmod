import os
import logging
from flask import Flask
from flask_login import LoginManager
from dotenv import load_dotenv

load_dotenv()

login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set appropriate log levels
    logging.getLogger('app.ctfd_client').setLevel(logging.INFO)
    logging.getLogger('app.routes.challenges').setLevel(logging.INFO)
    
    # File upload configuration
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads', 'email_attachments')
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Supabase configuration
    app.config['SUPABASE_URL'] = os.getenv('SUPABASE_URL', '')
    app.config['SUPABASE_KEY'] = os.getenv('SUPABASE_KEY', '')
    
    # GitHub configuration
    app.config['GITHUB_TOKEN'] = os.getenv('GITHUB_TOKEN', '')
    app.config['GITHUB_REPO_OWNER'] = os.getenv('GITHUB_REPO_OWNER', '')
    app.config['GITHUB_REPO_NAME'] = os.getenv('GITHUB_REPO_NAME', '')
    
    # CTFd configuration
    app.config['CTFD_URL'] = os.getenv('CTFD_URL', '')
    app.config['CTFD_API_KEY'] = os.getenv('CTFD_API_KEY', '')
    
    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.challenges import challenges_bp
    from app.routes.settings import settings_bp
    from app.routes.api import api_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(challenges_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    return app
