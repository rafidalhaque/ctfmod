"""
Integration test for bulk email background task API.
"""
import sys
import os
import json

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set test environment variables
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_KEY'] = 'test-key'

from app import create_app

def test_bulk_email_endpoint():
    """Test bulk email endpoint with background task."""
    print("Testing Bulk Email API Endpoint...")
    
    app = create_app()
    app.config['TESTING'] = True
    
    with app.test_client() as client:
        # Test endpoint exists
        print("✓ Flask app created successfully")
        
        # Note: Full integration test would require:
        # 1. Valid authentication/login
        # 2. Database setup with test data
        # 3. SMTP server mock/stub
        
        # For now, just verify the route is registered
        routes = [str(rule) for rule in app.url_map.iter_rules()]
        
        # Check bulk send endpoint exists
        bulk_send_route = '/settings/email-templates/bulk-send'
        assert any(bulk_send_route in route for route in routes), f"Bulk send route not found"
        print(f"✓ Bulk send endpoint registered: {bulk_send_route}")
        
        # Check task status endpoint exists
        task_status_route = '/settings/email-tasks/<task_id>/status'
        assert any('email-tasks' in route for route in routes), "Task status route not found"
        print(f"✓ Task status endpoint registered: {task_status_route}")
        
    print("\n✅ All endpoint tests passed!")
    return True


if __name__ == '__main__':
    try:
        test_bulk_email_endpoint()
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
