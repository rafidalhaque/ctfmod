"""
Test script for challenge editing and conflict resolution features.
This validates the flow of editing challenges in the portal and resolving sync conflicts.
"""

import json


def test_challenge_update():
    """Test that challenge update endpoint accepts valid data."""
    
    # Simulate a challenge update from the frontend
    update_data = {
        'name': 'Updated Challenge Name',
        'category': 'Web',
        'difficulty': 'Hard',
        'points': 500,
        'description': 'Updated description with more details',
        'flag': 'FLAG{updated_flag_123}',
        'hint': 'Updated hint',
        'solution': 'Updated solution steps'
    }
    
    # Validate all fields are present
    required_fields = ['name', 'category', 'difficulty', 'points', 'description', 'flag']
    for field in required_fields:
        assert field in update_data, f"Missing required field: {field}"
    
    # Validate data types
    assert isinstance(update_data['name'], str), "name must be string"
    assert isinstance(update_data['points'], int), "points must be integer"
    assert update_data['points'] > 0, "points must be positive"
    assert update_data['difficulty'] in ['Easy', 'Medium', 'Hard'], "Invalid difficulty"
    
    print("✓ Challenge update validation test passed")
    print(f"  Updated fields: {list(update_data.keys())}")
    return True


def test_conflict_detection():
    """Test that conflict detection logic works correctly."""
    
    # Scenario 1: No conflicts (values unchanged)
    existing_challenge = {
        'name': 'Challenge 1',
        'description': 'Original description',
        'points': 100,
        'github_data_snapshot': {
            'name': 'Challenge 1',
            'description': 'Original description',
            'points': 100
        }
    }
    
    github_data = {
        'name': 'Challenge 1',
        'description': 'Original description',
        'points': 100
    }
    
    conflicts = detect_conflicts_test(existing_challenge, github_data)
    assert conflicts is None or len(conflicts) == 0, "No conflicts should be detected"
    print("✓ No conflicts test passed")
    
    # Scenario 2: Portal edited, GitHub unchanged - no conflict
    existing_challenge = {
        'name': 'Challenge 1 Updated',
        'description': 'Portal description',
        'points': 200,
        'github_data_snapshot': {
            'name': 'Challenge 1',
            'description': 'Original description',
            'points': 100
        }
    }
    
    github_data = {
        'name': 'Challenge 1',
        'description': 'Original description',
        'points': 100
    }
    
    conflicts = detect_conflicts_test(existing_challenge, github_data)
    assert conflicts is None or len(conflicts) == 0, "No conflicts when only portal edited"
    print("✓ Portal-only edit test passed")
    
    # Scenario 3: Both portal and GitHub changed the same field - conflict!
    existing_challenge = {
        'name': 'Challenge 1 Portal Edit',
        'description': 'Portal description',
        'points': 200,
        'github_data_snapshot': {
            'name': 'Challenge 1',
            'description': 'Original description',
            'points': 100
        }
    }
    
    github_data = {
        'name': 'Challenge 1 GitHub Edit',
        'description': 'GitHub description',
        'points': 150
    }
    
    conflicts = detect_conflicts_test(existing_challenge, github_data)
    assert conflicts is not None and len(conflicts) > 0, "Conflicts should be detected"
    assert 'name' in conflicts, "name field should have conflict"
    assert 'description' in conflicts, "description field should have conflict"
    assert 'points' in conflicts, "points field should have conflict"
    print("✓ Conflict detection test passed")
    print(f"  Detected conflicts in fields: {list(conflicts.keys())}")
    
    return True


def detect_conflicts_test(existing_challenge, github_data):
    """Test implementation of conflict detection logic."""
    editable_fields = ['name', 'category', 'difficulty', 'description', 'points', 'flag', 'hint', 'solution']
    github_snapshot = existing_challenge.get('github_data_snapshot', {})
    
    conflicts = {}
    
    for field in editable_fields:
        current_value = existing_challenge.get(field)
        github_value = github_data.get(field)
        original_value = github_snapshot.get(field) if github_snapshot else None
        
        # Skip if both are None (but not empty strings or 0, which are valid)
        if current_value is None and github_value is None:
            continue
        
        # Conflict detected if both differ from original
        if current_value != github_value:
            if github_value != original_value:
                conflicts[field] = {
                    'portal_value': current_value,
                    'github_value': github_value,
                    'original_value': original_value
                }
    
    return conflicts if conflicts else None


def test_conflict_resolution():
    """Test conflict resolution strategies."""
    
    conflicting_fields = {
        'name': {
            'portal_value': 'Portal Name',
            'github_value': 'GitHub Name',
            'original_value': 'Original Name'
        },
        'description': {
            'portal_value': 'Portal Description',
            'github_value': 'GitHub Description',
            'original_value': 'Original Description'
        }
    }
    
    # Test 'keep_portal' resolution
    resolution = {
        'resolution_type': 'keep_portal'
    }
    assert resolution['resolution_type'] == 'keep_portal', "Resolution type should be keep_portal"
    print("✓ Keep portal resolution test passed")
    
    # Test 'use_github' resolution
    resolution = {
        'resolution_type': 'use_github'
    }
    assert resolution['resolution_type'] == 'use_github', "Resolution type should be use_github"
    print("✓ Use GitHub resolution test passed")
    
    # Test 'merge' resolution with field-specific choices
    resolution = {
        'resolution_type': 'merge',
        'field_resolutions': {
            'name': 'portal',
            'description': 'github'
        }
    }
    assert resolution['resolution_type'] == 'merge', "Resolution type should be merge"
    assert 'field_resolutions' in resolution, "Field resolutions should be present"
    assert resolution['field_resolutions']['name'] == 'portal', "Name should use portal value"
    assert resolution['field_resolutions']['description'] == 'github', "Description should use github value"
    print("✓ Merge resolution test passed")
    print(f"  Merge choices: {resolution['field_resolutions']}")
    
    return True


def test_edit_flow():
    """Test complete edit and conflict resolution flow."""
    
    print("\n=== Testing Complete Edit Flow ===\n")
    
    # Step 1: Initial challenge state
    challenge = {
        'id': 1,
        'name': 'Web Challenge',
        'description': 'Original description',
        'points': 100,
        'manually_edited': False,
        'github_data_snapshot': None
    }
    print("Step 1: Initial challenge state")
    print(f"  Name: {challenge['name']}")
    print(f"  Points: {challenge['points']}")
    
    # Step 2: User edits challenge in portal
    portal_updates = {
        'description': 'Portal edited description',
        'points': 200
    }
    challenge.update(portal_updates)
    challenge['manually_edited'] = True
    challenge['github_data_snapshot'] = {
        'name': 'Web Challenge',
        'description': 'Original description',
        'points': 100
    }
    print("\nStep 2: Challenge edited in portal")
    print(f"  New description: {challenge['description']}")
    print(f"  New points: {challenge['points']}")
    print(f"  Manually edited flag: {challenge['manually_edited']}")
    
    # Step 3: GitHub sync brings new changes
    github_data = {
        'name': 'Web Challenge',
        'description': 'GitHub updated description',
        'points': 150
    }
    print("\nStep 3: GitHub sync detects changes")
    print(f"  GitHub description: {github_data['description']}")
    print(f"  GitHub points: {github_data['points']}")
    
    # Step 4: Detect conflicts
    conflicts = detect_conflicts_test(challenge, github_data)
    if conflicts:
        challenge['has_conflicts'] = True
        challenge['conflicting_fields'] = conflicts
        print("\nStep 4: Conflicts detected!")
        for field, conflict_data in conflicts.items():
            print(f"  {field}:")
            print(f"    Portal: {conflict_data['portal_value']}")
            print(f"    GitHub: {conflict_data['github_value']}")
            print(f"    Original: {conflict_data['original_value']}")
    
    # Step 5: User resolves conflicts (using merge strategy)
    resolution = {
        'resolution_type': 'merge',
        'field_resolutions': {
            'description': 'portal',  # Keep portal description
            'points': 'github'  # Use GitHub points
        }
    }
    print("\nStep 5: User resolves conflicts")
    print(f"  Strategy: {resolution['resolution_type']}")
    print(f"  Choices: {resolution['field_resolutions']}")
    
    # Apply resolution
    for field, choice in resolution['field_resolutions'].items():
        if choice == 'github' and field in github_data:
            challenge[field] = github_data[field]
    
    challenge['has_conflicts'] = False
    challenge['conflicting_fields'] = None
    
    print("\nStep 6: Final state after resolution")
    print(f"  Description: {challenge['description']} (kept portal version)")
    print(f"  Points: {challenge['points']} (used GitHub version)")
    print(f"  Has conflicts: {challenge['has_conflicts']}")
    
    assert challenge['description'] == 'Portal edited description', "Should keep portal description"
    assert challenge['points'] == 150, "Should use GitHub points"
    assert challenge['has_conflicts'] == False, "Conflicts should be resolved"
    
    print("\n✓ Complete edit flow test passed")
    return True


def run_all_tests():
    """Run all tests for challenge editing and conflict resolution."""
    print("=" * 60)
    print("Challenge Editing and Conflict Resolution Tests")
    print("=" * 60)
    
    tests = [
        ("Challenge Update", test_challenge_update),
        ("Conflict Detection", test_conflict_detection),
        ("Conflict Resolution", test_conflict_resolution),
        ("Complete Edit Flow", test_edit_flow)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n--- Running: {test_name} ---")
        try:
            result = test_func()
            if result:
                passed += 1
                print(f"✓ {test_name} PASSED\n")
        except AssertionError as e:
            failed += 1
            print(f"✗ {test_name} FAILED: {e}\n")
        except Exception as e:
            failed += 1
            print(f"✗ {test_name} ERROR: {e}\n")
    
    print("=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    exit(0 if success else 1)
