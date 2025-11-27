from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.challenges import challenges_bp
from app.routes.settings import settings_bp
from app.routes.api import api_bp

__all__ = ['auth_bp', 'dashboard_bp', 'challenges_bp', 'settings_bp', 'api_bp']
