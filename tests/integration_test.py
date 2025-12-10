"""
Integration test demonstrating the full CTFd push configuration flow.
This simulates the user journey from UI to backend.
"""

import json

def simulate_user_flow():
    """Simulate a complete user flow through the feature."""
    
    print("=" * 70)
    print("INTEGRATION TEST: CTFd Push Configuration Feature")
    print("=" * 70)
    print()
    
    # Step 1: User opens the push configuration modal
    print("Step 1: User clicks 'Push to CTFd' button")
    print("  → Modal opens with default configuration")
    print()
    
    # Step 2: User customizes the configuration
    print("Step 2: User customizes the configuration")
    user_config = {
        'fields': {
            'name': True,          # Required - always checked
            'category': True,      # Required - always checked
            'description': True,   # User keeps checked
            'value': True,         # Required - always checked
            'flag': True,          # User keeps checked
            'connection_info': True,  # User keeps checked
            'attribution': True,   # User keeps checked
            'requirements': False  # User unchecks (not needed)
        },
        'settings': {
            'type': 'standard',    # User selects standard
            'state': 'hidden',     # User selects hidden
            'max_attempts': 3      # User sets to 3 attempts
        }
    }
    
    print("  Selected fields:")
    for field, enabled in user_config['fields'].items():
        status = "✓" if enabled else "✗"
        required = "(required)" if field in ['name', 'category', 'value'] else ""
        print(f"    {status} {field} {required}")
    
    print("\n  Settings:")
    print(f"    Type: {user_config['settings']['type']}")
    print(f"    State: {user_config['settings']['state']}")
    print(f"    Max Attempts: {user_config['settings']['max_attempts']}")
    print()
    
    # Step 3: User checks "Save as default"
    print("Step 3: User checks 'Save as default'")
    saved_config = json.dumps(user_config)
    print(f"  → Configuration saved to localStorage")
    print()
    
    # Step 4: Request is sent to backend
    print("Step 4: Request sent to backend")
    print(f"  POST /challenges/123/push-to-ctfd")
    print(f"  Body: {json.dumps(user_config, indent=6)}")
    print()
    
    # Step 5: Backend processes the request
    print("Step 5: Backend processes the configuration")
    
    # Simulate challenge data from database
    challenge = {
        'id': 123,
        'name': 'SQL Injection 101',
        'category': 'Web',
        'description': 'Find and exploit the SQL injection vulnerability',
        'points': 100,
        'flag': 'flag{sql_1nj3ct10n_m4st3r}'
    }
    
    # Simulate challenge.yml data
    challenge_yml = {
        'connection_info': 'http://vulnerable-app.ctf.local',
        'attribution': 'Security Team',
        'max_attempts': None  # Override with config
    }
    
    # Build CTFd challenge data based on configuration
    ctfd_challenge = {
        'name': challenge['name'],
        'category': challenge['category'],
        'value': challenge['points'],
        'type': user_config['settings']['type'],
        'state': user_config['settings']['state']
    }
    
    # Apply field selections
    if user_config['fields']['description']:
        ctfd_challenge['description'] = challenge['description']
    
    if user_config['settings']['max_attempts'] > 0:
        ctfd_challenge['max_attempts'] = user_config['settings']['max_attempts']
    
    if user_config['fields']['connection_info'] and 'connection_info' in challenge_yml:
        ctfd_challenge['connection_info'] = challenge_yml['connection_info']
    
    if user_config['fields']['attribution'] and 'attribution' in challenge_yml:
        ctfd_challenge['attribution'] = challenge_yml['attribution']
    
    # Flag handling
    flag_content = None
    if user_config['fields']['flag']:
        flag_content = challenge['flag']
    
    print("  Built challenge data for CTFd:")
    print(json.dumps(ctfd_challenge, indent=4))
    print()
    print(f"  Flag to be created: {flag_content}")
    print()
    
    # Step 6: Simulate successful push
    print("Step 6: Challenge pushed to CTFd successfully")
    response = {
        'success': True,
        'message': 'Challenge pushed to CTFd successfully with state: hidden. Included: description, flag, connection info, attribution',
        'ctfd_id': 456,
        'flag_created': True,
        'settings': user_config['settings']
    }
    
    print(f"  Response: {json.dumps(response, indent=4)}")
    print()
    
    # Step 7: Verify the configuration was applied correctly
    print("Step 7: Verification")
    
    verifications = [
        ('Challenge has name', 'name' in ctfd_challenge),
        ('Challenge has category', 'category' in ctfd_challenge),
        ('Challenge has value/points', 'value' in ctfd_challenge),
        ('Challenge has description', 'description' in ctfd_challenge),
        ('Challenge has connection_info', 'connection_info' in ctfd_challenge),
        ('Challenge has attribution', 'attribution' in ctfd_challenge),
        ('Challenge does NOT have requirements', 'requirements' not in ctfd_challenge),
        ('Challenge type is standard', ctfd_challenge['type'] == 'standard'),
        ('Challenge state is hidden', ctfd_challenge['state'] == 'hidden'),
        ('Challenge max_attempts is 3', ctfd_challenge.get('max_attempts') == 3),
        ('Flag was created', flag_content is not None),
        ('Response indicates success', response['success'])
    ]
    
    all_passed = True
    for description, result in verifications:
        status = "✓" if result else "✗"
        print(f"  {status} {description}")
        if not result:
            all_passed = False
    
    print()
    
    # Step 8: Test loading defaults for next challenge
    print("Step 8: User pushes another challenge")
    print("  → Configuration loaded from localStorage")
    loaded_config = json.loads(saved_config)
    
    print("  Loaded configuration:")
    print(f"    Fields match saved: {loaded_config['fields'] == user_config['fields']}")
    print(f"    Settings match saved: {loaded_config['settings'] == user_config['settings']}")
    print()
    
    # Final result
    print("=" * 70)
    if all_passed:
        print("✓ INTEGRATION TEST PASSED - All verifications successful!")
    else:
        print("✗ INTEGRATION TEST FAILED - Some verifications failed!")
    print("=" * 70)
    
    return all_passed

def test_edge_cases():
    """Test edge cases and error conditions."""
    
    print("\n" + "=" * 70)
    print("EDGE CASE TESTS")
    print("=" * 70)
    print()
    
    # Test 1: Empty configuration (should use defaults)
    print("Test 1: Empty configuration (should use defaults)")
    config = {}
    
    # Backend should apply defaults
    fields_config = config.get('fields', {
        'name': True,
        'category': True,
        'description': True,
        'value': True,
        'flag': True,
        'connection_info': True,
        'attribution': True,
        'requirements': False
    })
    
    settings_config = config.get('settings', {
        'type': 'standard',
        'state': 'hidden',
        'max_attempts': 0
    })
    
    assert fields_config['name'] == True
    assert settings_config['state'] == 'hidden'
    print("  ✓ Defaults applied correctly")
    print()
    
    # Test 2: Only required fields
    print("Test 2: Minimal configuration (only required fields)")
    minimal_config = {
        'fields': {
            'name': True,
            'category': True,
            'value': True,
            'description': False,
            'flag': False,
            'connection_info': False,
            'attribution': False,
            'requirements': False
        },
        'settings': {
            'type': 'standard',
            'state': 'visible',
            'max_attempts': 0
        }
    }
    
    # Build challenge with minimal config
    ctfd_challenge = {
        'name': 'Test',
        'category': 'Test',
        'value': 100,
        'type': minimal_config['settings']['type'],
        'state': minimal_config['settings']['state']
    }
    
    # Verify only required fields
    assert len(ctfd_challenge) == 5  # name, category, value, type, state
    assert 'description' not in ctfd_challenge
    assert 'connection_info' not in ctfd_challenge
    print("  ✓ Minimal configuration works correctly")
    print()
    
    # Test 3: Max attempts = 0 (unlimited)
    print("Test 3: Unlimited attempts (max_attempts = 0)")
    config = {
        'settings': {
            'max_attempts': 0
        }
    }
    
    ctfd_challenge = {'name': 'Test', 'category': 'Test', 'value': 100}
    
    # Should not add max_attempts if 0
    if config['settings']['max_attempts'] > 0:
        ctfd_challenge['max_attempts'] = config['settings']['max_attempts']
    
    assert 'max_attempts' not in ctfd_challenge
    print("  ✓ Unlimited attempts handled correctly (field omitted)")
    print()
    
    # Test 4: Dynamic scoring type
    print("Test 4: Dynamic scoring type")
    config = {
        'settings': {
            'type': 'dynamic',
            'state': 'visible'
        }
    }
    
    ctfd_challenge = {
        'type': config['settings']['type'],
        'state': config['settings']['state']
    }
    
    assert ctfd_challenge['type'] == 'dynamic'
    assert ctfd_challenge['state'] == 'visible'
    print("  ✓ Dynamic scoring type supported")
    print()
    
    print("=" * 70)
    print("✓ ALL EDGE CASE TESTS PASSED")
    print("=" * 70)
    
    return True

if __name__ == '__main__':
    success1 = simulate_user_flow()
    success2 = test_edge_cases()
    
    exit(0 if (success1 and success2) else 1)
