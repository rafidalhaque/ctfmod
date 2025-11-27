from flask_login import UserMixin


class User(UserMixin):
    """User model for Flask-Login integration with Supabase."""
    
    def __init__(self, user_data: dict):
        self.id = user_data.get('id')
        self.email = user_data.get('email')
        self.role = user_data.get('role', 'user')
        self.created_at = user_data.get('created_at')
        self.user_metadata = user_data.get('user_metadata', {})
    
    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'
    
    def get_id(self) -> str:
        return str(self.id)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'email': self.email,
            'role': self.role,
            'created_at': self.created_at,
            'user_metadata': self.user_metadata
        }
