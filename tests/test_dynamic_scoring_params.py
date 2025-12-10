"""
Test to verify that dynamic scoring parameters can be provided via request
when they are missing from challenge.yml.
"""
import json


def add_dynamic_fields_to_challenge(ctfd_challenge, settings_config, challenge_yml, dynamic_scoring_config):
    """Helper function to add dynamic scoring fields based on challenge type.
    
    This simulates the backend logic for handling dynamic scoring parameters.
    Prefers values from challenge.yml, but falls back to values from the request config.
    """
    if settings_config.get('type') == 'dynamic':
        # Initial value
        if challenge_yml and 'initial' in challenge_yml:
            ctfd_challenge['initial'] = challenge_yml['initial']
        elif dynamic_scoring_config.get('initial') is not None:
            ctfd_challenge['initial'] = dynamic_scoring_config['initial']
        
        # Minimum value
        if challenge_yml and 'minimum' in challenge_yml:
            ctfd_challenge['minimum'] = challenge_yml['minimum']
        elif dynamic_scoring_config.get('minimum') is not None:
            ctfd_challenge['minimum'] = dynamic_scoring_config['minimum']
        
        # Decay value
        if challenge_yml and 'decay' in challenge_yml:
            ctfd_challenge['decay'] = challenge_yml['decay']
        elif dynamic_scoring_config.get('decay') is not None:
            ctfd_challenge['decay'] = dynamic_scoring_config['decay']
        
        # Function type
        if challenge_yml and 'function' in challenge_yml:
            ctfd_challenge['function'] = challenge_yml['function']
        elif dynamic_scoring_config.get('function'):
            ctfd_challenge['function'] = dynamic_scoring_config['function']


def test_dynamic_challenge_with_request_params():
    """Test that dynamic challenges use parameters from request when challenge.yml lacks them."""
    
    print("=" * 70)
    print("TEST: Dynamic Challenge with Parameters from Request")
    print("=" * 70)
    print()
    
    # Simulate challenge data from database
    challenge = {
        'id': 456,
        'name': 'Dynamic Reversing Challenge',
        'category': 'Reversing',
        'description': 'A dynamic scoring challenge without params in yml',
        'points': 150,
        'flag': 'flag{dynamic_from_request}'
    }
    
    # challenge.yml exists but does NOT have dynamic scoring fields
    challenge_yml = {
        'connection_info': 'nc challenge.ctf.local 9999',
        'attribution': 'Security Team'
    }
    
    # Configuration with type set to 'dynamic'
    settings_config = {
        'type': 'dynamic',
        'state': 'hidden',
        'max_attempts': 0
    }
    
    # Dynamic scoring parameters provided via request (from the portal UI)
    dynamic_scoring_config = {
        'initial': 500,
        'minimum': 100,
        'decay': 50,
        'function': 'logarithmic'
    }
    
    # Build CTFd challenge data
    ctfd_challenge = {
        'name': challenge['name'],
        'category': challenge['category'],
        'value': challenge['points'],
        'type': settings_config['type'],
        'state': settings_config['state'],
        'description': challenge['description']
    }
    
    # Add dynamic scoring fields (THE NEW BEHAVIOR)
    add_dynamic_fields_to_challenge(ctfd_challenge, settings_config, challenge_yml, dynamic_scoring_config)
    
    print("Built challenge data for CTFd:")
    print(json.dumps(ctfd_challenge, indent=2))
    print()
    
    # Verify that parameters from request config were used
    print("Verification:")
    verifications = [
        ('Challenge has type=dynamic', ctfd_challenge.get('type') == 'dynamic'),
        ('Challenge has initial value', 'initial' in ctfd_challenge),
        ('Challenge has minimum value', 'minimum' in ctfd_challenge),
        ('Challenge has decay value', 'decay' in ctfd_challenge),
        ('Challenge has function', 'function' in ctfd_challenge),
        ('Initial value is correct (from request)', ctfd_challenge.get('initial') == 500),
        ('Minimum value is correct (from request)', ctfd_challenge.get('minimum') == 100),
        ('Decay value is correct (from request)', ctfd_challenge.get('decay') == 50),
        ('Function is correct (from request)', ctfd_challenge.get('function') == 'logarithmic'),
    ]
    
    all_passed = True
    for description, result in verifications:
        status = "✓" if result else "✗"
        print(f"  {status} {description}")
        if not result:
            all_passed = False
    
    print()
    print("=" * 70)
    if all_passed:
        print("✓ REQUEST PARAMS TEST PASSED")
    else:
        print("✗ REQUEST PARAMS TEST FAILED")
    print("=" * 70)
    
    return all_passed


def test_dynamic_challenge_yml_overrides_request():
    """Test that challenge.yml values take precedence over request parameters."""
    
    print()
    print("=" * 70)
    print("TEST: Challenge.yml Values Override Request Parameters")
    print("=" * 70)
    print()
    
    # challenge.yml has SOME dynamic scoring fields
    challenge_yml = {
        'initial': 1000,  # Different from request
        'decay': 75       # Different from request
        # minimum and function missing
    }
    
    # Configuration with type set to 'dynamic'
    settings_config = {
        'type': 'dynamic',
        'state': 'visible',
        'max_attempts': 0
    }
    
    # Request parameters (defaults from portal)
    dynamic_scoring_config = {
        'initial': 500,
        'minimum': 100,
        'decay': 50,
        'function': 'logarithmic'
    }
    
    # Build CTFd challenge data
    ctfd_challenge = {
        'name': 'Mixed Source Challenge',
        'category': 'Web',
        'value': 200,
        'type': settings_config['type'],
        'state': settings_config['state']
    }
    
    # Add dynamic scoring fields
    add_dynamic_fields_to_challenge(ctfd_challenge, settings_config, challenge_yml, dynamic_scoring_config)
    
    print("Built challenge data for CTFd:")
    print(json.dumps(ctfd_challenge, indent=2))
    print()
    
    # Verify that yml values override request values
    print("Verification:")
    verifications = [
        ('Challenge has type=dynamic', ctfd_challenge.get('type') == 'dynamic'),
        ('Initial from yml (1000, not 500)', ctfd_challenge.get('initial') == 1000),
        ('Decay from yml (75, not 50)', ctfd_challenge.get('decay') == 75),
        ('Minimum from request (100)', ctfd_challenge.get('minimum') == 100),
        ('Function from request (logarithmic)', ctfd_challenge.get('function') == 'logarithmic'),
    ]
    
    all_passed = True
    for description, result in verifications:
        status = "✓" if result else "✗"
        print(f"  {status} {description}")
        if not result:
            all_passed = False
    
    print()
    print("=" * 70)
    if all_passed:
        print("✓ YML OVERRIDE TEST PASSED")
    else:
        print("✗ YML OVERRIDE TEST FAILED")
    print("=" * 70)
    
    return all_passed


def test_standard_challenge_ignores_request_params():
    """Test that standard challenges ignore dynamic scoring parameters."""
    
    print()
    print("=" * 70)
    print("TEST: Standard Challenge Ignores Dynamic Params")
    print("=" * 70)
    print()
    
    # Configuration with type set to 'standard' (not dynamic)
    settings_config = {
        'type': 'standard',
        'state': 'visible',
        'max_attempts': 0
    }
    
    # Request has dynamic scoring parameters (should be ignored)
    dynamic_scoring_config = {
        'initial': 500,
        'minimum': 100,
        'decay': 50,
        'function': 'logarithmic'
    }
    
    # Build CTFd challenge data
    ctfd_challenge = {
        'name': 'Standard Challenge',
        'category': 'Forensics',
        'value': 300,
        'type': settings_config['type'],
        'state': settings_config['state']
    }
    
    # Add dynamic scoring fields (should not add anything)
    add_dynamic_fields_to_challenge(ctfd_challenge, settings_config, None, dynamic_scoring_config)
    
    print("Built challenge data for CTFd:")
    print(json.dumps(ctfd_challenge, indent=2))
    print()
    
    # Verify that dynamic params were NOT added
    print("Verification:")
    verifications = [
        ('Challenge has type=standard', ctfd_challenge.get('type') == 'standard'),
        ('Challenge does NOT have initial', 'initial' not in ctfd_challenge),
        ('Challenge does NOT have minimum', 'minimum' not in ctfd_challenge),
        ('Challenge does NOT have decay', 'decay' not in ctfd_challenge),
        ('Challenge does NOT have function', 'function' not in ctfd_challenge),
    ]
    
    all_passed = True
    for description, result in verifications:
        status = "✓" if result else "✗"
        print(f"  {status} {description}")
        if not result:
            all_passed = False
    
    print()
    print("=" * 70)
    if all_passed:
        print("✓ STANDARD IGNORES PARAMS TEST PASSED")
    else:
        print("✗ STANDARD IGNORES PARAMS TEST FAILED")
    print("=" * 70)
    
    return all_passed


if __name__ == '__main__':
    test1 = test_dynamic_challenge_with_request_params()
    test2 = test_dynamic_challenge_yml_overrides_request()
    test3 = test_standard_challenge_ignores_request_params()
    
    print()
    print("=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    
    if test1 and test2 and test3:
        print("✓ ALL TESTS PASSED")
        exit(0)
    else:
        print("✗ SOME TESTS FAILED")
        exit(1)
