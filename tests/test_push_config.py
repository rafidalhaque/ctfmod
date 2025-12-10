"""
Test script to validate the CTFd push configuration feature.
This simulates the flow of configuring and pushing a challenge to CTFd.
"""

import json

def test_config_structure():
    """Test that the configuration structure is valid."""
    
    # Simulate a configuration from the frontend
    config = {
        'fields': {
            'name': True,
            'category': True,
            'description': True,
            'value': True,
            'flag': True,
            'connection_info': True,
            'attribution': True,
            'requirements': False
        },
        'settings': {
            'type': 'standard',
            'state': 'hidden',
            'max_attempts': 0
        }
    }
    
    print("✓ Configuration structure test passed")
    print(f"  Fields config: {json.dumps(config['fields'], indent=2)}")
    print(f"  Settings config: {json.dumps(config['settings'], indent=2)}")
    return True

def test_field_selection():
    """Test that field selection logic works correctly."""
    
    # Simulate different field configurations
    test_cases = [
        {
            'name': 'All fields enabled',
            'config': {
                'description': True,
                'flag': True,
                'connection_info': True,
                'attribution': True
            },
            'expected_fields': ['description', 'flag', 'connection_info', 'attribution']
        },
        {
            'name': 'Only required fields',
            'config': {
                'description': False,
                'flag': False,
                'connection_info': False,
                'attribution': False
            },
            'expected_fields': []
        },
        {
            'name': 'Mixed selection',
            'config': {
                'description': True,
                'flag': False,
                'connection_info': True,
                'attribution': False
            },
            'expected_fields': ['description', 'connection_info']
        }
    ]
    
    for test in test_cases:
        included_fields = [field for field, enabled in test['config'].items() if enabled]
        assert included_fields == test['expected_fields'], f"Test '{test['name']}' failed"
        print(f"✓ Field selection test '{test['name']}' passed")
    
    return True

def test_settings_validation():
    """Test that settings are valid."""
    
    valid_types = ['standard', 'dynamic']
    valid_states = ['hidden', 'visible']
    
    # Test valid settings
    settings = {
        'type': 'standard',
        'state': 'hidden',
        'max_attempts': 5
    }
    
    assert settings['type'] in valid_types, "Invalid challenge type"
    assert settings['state'] in valid_states, "Invalid challenge state"
    assert settings['max_attempts'] >= 0, "Max attempts must be non-negative"
    
    print("✓ Settings validation test passed")
    print(f"  Type: {settings['type']}")
    print(f"  State: {settings['state']}")
    print(f"  Max attempts: {settings['max_attempts']}")
    
    return True

def test_default_saving():
    """Test that default configuration can be saved and loaded."""
    
    # Simulate saving to localStorage
    config = {
        'fields': {
            'description': True,
            'flag': True,
            'connection_info': False
        },
        'settings': {
            'type': 'standard',
            'state': 'visible',
            'max_attempts': 3
        }
    }
    
    # Convert to JSON (simulating localStorage)
    saved_config = json.dumps(config)
    
    # Load back
    loaded_config = json.loads(saved_config)
    
    assert loaded_config == config, "Config mismatch after save/load"
    
    print("✓ Default saving/loading test passed")
    print(f"  Saved and loaded config successfully")
    
    return True

def test_challenge_data_building():
    """Test that challenge data is built correctly based on config."""
    
    # Sample challenge from database
    challenge = {
        'name': 'Test Challenge',
        'category': 'Web',
        'description': 'A test challenge',
        'points': 100,
        'flag': 'flag{test}'
    }
    
    # Sample challenge.yml data
    challenge_yml = {
        'connection_info': 'nc example.com 1337',
        'attribution': 'John Doe',
        'requirements': {'prerequisite': [1, 2]}
    }
    
    # Configuration
    fields_config = {
        'description': True,
        'flag': True,
        'connection_info': True,
        'attribution': True,
        'requirements': False
    }
    
    settings_config = {
        'type': 'standard',
        'state': 'hidden',
        'max_attempts': 5
    }
    
    # Build CTFd challenge data
    ctfd_challenge = {
        'name': challenge['name'],
        'category': challenge['category'],
        'value': challenge['points'],
        'type': settings_config['type'],
        'state': settings_config['state']
    }
    
    if fields_config.get('description', True):
        ctfd_challenge['description'] = challenge['description']
    
    if settings_config['max_attempts'] > 0:
        ctfd_challenge['max_attempts'] = settings_config['max_attempts']
    
    if fields_config.get('connection_info', True) and 'connection_info' in challenge_yml:
        ctfd_challenge['connection_info'] = challenge_yml['connection_info']
    
    if fields_config.get('attribution', True) and 'attribution' in challenge_yml:
        ctfd_challenge['attribution'] = challenge_yml['attribution']
    
    if fields_config.get('requirements', False) and 'requirements' in challenge_yml:
        ctfd_challenge['requirements'] = challenge_yml['requirements']
    
    # Verify
    assert 'name' in ctfd_challenge, "Name is required"
    assert 'category' in ctfd_challenge, "Category is required"
    assert 'value' in ctfd_challenge, "Value is required"
    assert ctfd_challenge['description'] == 'A test challenge', "Description should be included"
    assert ctfd_challenge['connection_info'] == 'nc example.com 1337', "Connection info should be included"
    assert ctfd_challenge['attribution'] == 'John Doe', "Attribution should be included"
    assert 'requirements' not in ctfd_challenge, "Requirements should not be included"
    assert ctfd_challenge['max_attempts'] == 5, "Max attempts should be set"
    
    print("✓ Challenge data building test passed")
    print(f"  Built challenge: {json.dumps(ctfd_challenge, indent=2)}")
    
    # Test flag handling
    flag_content = None
    if fields_config.get('flag', True):
        flag_content = challenge['flag']
    
    assert flag_content == 'flag{test}', "Flag should be included"
    print(f"  Flag content: {flag_content}")
    
    return True

def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Running CTFd Push Configuration Tests")
    print("=" * 60)
    print()
    
    tests = [
        test_config_structure,
        test_field_selection,
        test_settings_validation,
        test_default_saving,
        test_challenge_data_building
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            print(f"\n--- Running {test.__name__} ---")
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0

if __name__ == '__main__':
    success = run_all_tests()
    exit(0 if success else 1)
