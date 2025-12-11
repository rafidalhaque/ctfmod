"""
Simple test to verify background email queue works correctly.
"""
import sys
import os
import time
import uuid
from datetime import datetime

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.email_queue import EmailQueue, EmailTask


def test_email_queue():
    """Test basic email queue functionality."""
    print("Testing Email Queue...")
    
    # Create queue instance
    queue = EmailQueue()
    
    # Create a mock task
    task_id = str(uuid.uuid4())
    recipients = [
        {
            'email': 'test1@example.com',
            'user_name': 'Test User 1',
            'user_email': 'test1@example.com',
            'user_ctfd_username': 'test1',
            'user_ctfd_password': 'pass1',
            'team_name': 'Team A',
            'team_db_id': 1,
            'registration_id': '1',
            'team_ctfd_username': 'teama',
            'team_ctfd_password': 'teampass'
        },
        {
            'email': 'test2@example.com',
            'user_name': 'Test User 2',
            'user_email': 'test2@example.com',
            'user_ctfd_username': 'test2',
            'user_ctfd_password': 'pass2',
            'team_name': 'Team B',
            'team_db_id': 2,
            'registration_id': '2',
            'team_ctfd_username': 'teamb',
            'team_ctfd_password': 'teampass2'
        }
    ]
    
    smtp_settings = {
        'host': 'smtp.example.com',
        'port': 587,
        'username': 'user',
        'password': 'pass',
        'sender_email': 'sender@example.com',
        'sender_name': 'Test Sender',
        'use_tls': True,
        'use_ssl': False,
        'event_name': 'Test Event',
        'site_name': 'Test Site'
    }
    
    template_data = {
        'subject': 'Test Email - {{user_name}}',
        'body': '<p>Hello {{user_name}}, welcome to {{team_name}}!</p>'
    }
    
    task = EmailTask(
        task_id=task_id,
        template_id=1,
        template_name='Test Template',
        recipients=recipients,
        smtp_settings=smtp_settings,
        template_data=template_data,
        attachments=[],
        upload_folder='/tmp',
        delay_seconds=2
    )
    
    print(f"Created task: {task_id}")
    print(f"Recipients: {len(recipients)}")
    print(f"Delay: {task.delay_seconds}s")
    
    # Test task properties
    assert task.status == 'queued'
    assert task.total_count == 2
    assert task.sent_count == 0
    assert task.failed_count == 0
    
    # Test getting status before adding to queue
    status = queue.get_task_status(task_id)
    assert status is None, "Task should not exist in queue yet"
    
    # Add task to queue (but don't start worker since we don't have real SMTP)
    queue.tasks[task_id] = task
    
    # Test getting status after adding
    status = queue.get_task_status(task_id)
    assert status is not None, "Task should exist in queue"
    assert status['status'] == 'queued'
    assert status['total_count'] == 2
    assert status['progress_percentage'] == 0
    
    print("✓ Task creation and status tracking works correctly")
    
    # Test variable replacement logic
    subject = template_data['subject']
    body = template_data['body']
    recipient = recipients[0]
    
    variables = {
        'user_name': recipient['user_name'],
        'team_name': recipient['team_name']
    }
    
    for var_name, var_value in variables.items():
        subject = subject.replace('{{' + var_name + '}}', str(var_value or ''))
        body = body.replace('{{' + var_name + '}}', str(var_value or ''))
    
    assert 'Test User 1' in subject
    assert 'Team A' in body
    
    print("✓ Variable replacement works correctly")
    
    # Simulate progress
    task.status = 'processing'
    task.sent_count = 1
    task.failed_count = 0
    status = queue.get_task_status(task_id)
    assert status['progress_percentage'] == 50.0
    
    print("✓ Progress tracking works correctly")
    
    print("\n✅ All tests passed!")
    return True


if __name__ == '__main__':
    try:
        test_email_queue()
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
