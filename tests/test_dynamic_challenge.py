"""
Test to verify that dynamic challenges are pushed correctly with dynamic scoring fields.
"""
import json


def add_dynamic_fields_to_challenge(ctfd_challenge, settings_config, challenge_yml):
    """Helper function to add dynamic scoring fields based on challenge type."""
    if settings_config.get('type') == 'dynamic' and challenge_yml:
        if 'initial' in challenge_yml:
            ctfd_challenge['initial'] = challenge_yml['initial']
        if 'minimum' in challenge_yml:
            ctfd_challenge['minimum'] = challenge_yml['minimum']
        if 'decay' in challenge_yml:
            ctfd_challenge['decay'] = challenge_yml['decay']
        if 'function' in challenge_yml:
            ctfd_challenge['function'] = challenge_yml['function']


def test_dynamic_challenge_with_fields():
    """Test that dynamic challenges include required dynamic scoring fields."""
    
    print("=" * 70)
    print("TEST: Dynamic Challenge Push")
    print("=" * 70)
    print()
    
    # Simulate challenge data from database
    challenge = {
        'id': 123,
        'name': 'Dynamic Web Challenge',
        'category': 'Web',
        'description': 'A dynamic scoring challenge',
        'points': 100,
        'flag': 'flag{dynamic_test}'
    }
    
    # Simulate challenge.yml with dynamic scoring fields
    challenge_yml = {
        'connection_info': 'http://dynamic.ctf.local',
        'attribution': 'Security Team',
        'initial': 500,      # Initial value for dynamic scoring
        'minimum': 100,      # Minimum value
        'decay': 50,         # Decay amount
        'function': 'logarithmic'  # Scoring function
    }
    
    # Configuration with type set to 'dynamic'
    fields_config = {
        'name': True,
        'category': True,
        'description': True,
        'value': True,
        'flag': True,
        'connection_info': True,
        'attribution': True,
        'requirements': False
    }
    
    settings_config = {
        'type': 'dynamic',  # Set to dynamic
        'state': 'hidden',
        'max_attempts': 0
    }
    
    # Build CTFd challenge data (simulating the backend logic)
    ctfd_challenge = {
        'name': challenge['name'],
        'category': challenge['category'],
        'value': challenge['points'],
        'type': settings_config['type'],
        'state': settings_config['state']
    }
    
    # Add description if configured
    if fields_config.get('description', True):
        ctfd_challenge['description'] = challenge['description']
    
    # Add max_attempts from settings
    max_attempts = settings_config.get('max_attempts', 0)
    if max_attempts > 0:
        ctfd_challenge['max_attempts'] = max_attempts
    
    # Add connection_info if configured and available
    if fields_config.get('connection_info', True) and 'connection_info' in challenge_yml:
        ctfd_challenge['connection_info'] = challenge_yml['connection_info']
    
    # Add attribution if configured and available
    if fields_config.get('attribution', True) and 'attribution' in challenge_yml:
        ctfd_challenge['attribution'] = challenge_yml['attribution']
    
    # Add dynamic scoring fields if type is 'dynamic' (THE FIX)
    add_dynamic_fields_to_challenge(ctfd_challenge, settings_config, challenge_yml)
    
    # Flag handling
    flag_content = None
    if fields_config.get('flag', True):
        flag_content = challenge['flag']
    
    print("Built challenge data for CTFd:")
    print(json.dumps(ctfd_challenge, indent=2))
    print()
    print(f"Flag to be created: {flag_content}")
    print()
    
    # Verify the challenge data includes dynamic scoring fields
    print("Verification:")
    verifications = [
        ('Challenge has type=dynamic', ctfd_challenge.get('type') == 'dynamic'),
        ('Challenge has initial value', 'initial' in ctfd_challenge),
        ('Challenge has minimum value', 'minimum' in ctfd_challenge),
        ('Challenge has decay value', 'decay' in ctfd_challenge),
        ('Challenge has function', 'function' in ctfd_challenge),
        ('Initial value is correct', ctfd_challenge.get('initial') == 500),
        ('Minimum value is correct', ctfd_challenge.get('minimum') == 100),
        ('Decay value is correct', ctfd_challenge.get('decay') == 50),
        ('Function is correct', ctfd_challenge.get('function') == 'logarithmic'),
        ('Flag content is present', flag_content is not None),
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
        print("✓ DYNAMIC CHALLENGE TEST PASSED")
    else:
        print("✗ DYNAMIC CHALLENGE TEST FAILED")
    print("=" * 70)
    
    return all_passed


def test_standard_challenge_no_dynamic_fields():
    """Test that standard challenges don't include dynamic scoring fields."""
    
    print()
    print("=" * 70)
    print("TEST: Standard Challenge Should Not Have Dynamic Fields")
    print("=" * 70)
    print()
    
    # Simulate challenge data
    challenge = {
        'name': 'Standard Challenge',
        'category': 'Crypto',
        'description': 'A standard scoring challenge',
        'points': 200,
        'flag': 'flag{standard_test}'
    }
    
    # challenge.yml has dynamic fields but type is standard
    challenge_yml = {
        'initial': 500,
        'minimum': 100,
        'decay': 50,
        'function': 'logarithmic'
    }
    
    # Configuration with type set to 'standard'
    settings_config = {
        'type': 'standard',  # Standard type
        'state': 'visible',
        'max_attempts': 0
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
    
    # Add dynamic scoring fields ONLY if type is 'dynamic'
    add_dynamic_fields_to_challenge(ctfd_challenge, settings_config, challenge_yml)
    
    print("Built challenge data for CTFd:")
    print(json.dumps(ctfd_challenge, indent=2))
    print()
    
    # Verify that standard challenges don't have dynamic fields
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
        print("✓ STANDARD CHALLENGE TEST PASSED")
    else:
        print("✗ STANDARD CHALLENGE TEST FAILED")
    print("=" * 70)
    
    return all_passed


def test_dynamic_challenge_missing_fields():
    """Test that dynamic challenges work even with some missing dynamic fields."""
    
    print()
    print("=" * 70)
    print("TEST: Dynamic Challenge with Partial Fields")
    print("=" * 70)
    print()
    
    # challenge.yml has only some dynamic fields
    challenge_yml = {
        'initial': 500,
        'minimum': 100,
        # Missing decay and function
    }
    
    settings_config = {
        'type': 'dynamic',
        'state': 'hidden',
        'max_attempts': 0
    }
    
    # Build CTFd challenge data
    ctfd_challenge = {
        'name': 'Test',
        'category': 'Test',
        'value': 100,
        'type': settings_config['type'],
        'state': settings_config['state']
    }
    
    # Add dynamic scoring fields if type is 'dynamic'
    add_dynamic_fields_to_challenge(ctfd_challenge, settings_config, challenge_yml)
    
    print("Built challenge data for CTFd:")
    print(json.dumps(ctfd_challenge, indent=2))
    print()
    
    # Verify
    print("Verification:")
    verifications = [
        ('Challenge has type=dynamic', ctfd_challenge.get('type') == 'dynamic'),
        ('Challenge has initial', 'initial' in ctfd_challenge),
        ('Challenge has minimum', 'minimum' in ctfd_challenge),
        ('Challenge does NOT have decay (missing)', 'decay' not in ctfd_challenge),
        ('Challenge does NOT have function (missing)', 'function' not in ctfd_challenge),
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
        print("✓ PARTIAL DYNAMIC FIELDS TEST PASSED")
    else:
        print("✗ PARTIAL DYNAMIC FIELDS TEST FAILED")
    print("=" * 70)
    
    return all_passed


if __name__ == '__main__':
    test1 = test_dynamic_challenge_with_fields()
    test2 = test_standard_challenge_no_dynamic_fields()
    test3 = test_dynamic_challenge_missing_fields()
    
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
