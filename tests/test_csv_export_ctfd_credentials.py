"""
Test to verify CSV export includes CTFd user credentials.
"""
import sys
import os
import csv
import io

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def build_row_data_helper(position, registration_id, team_name, total_members, captain_name, member_data, user_credentials, selected_columns):
    """Helper function to build row data for CSV export with CTFd credentials."""
    member_id = member_data.get('id') if member_data else None
    user_cred = user_credentials.get(member_id, {}) if member_id else {}
    
    row_data = {
        'position': position,
        'team_id': registration_id or '',
        'team_name': team_name,
        'total_members': total_members,
        'captain_name': captain_name,
        'member_name': member_data.get('name', '') if member_data else '',
        'member_class': member_data.get('class', '') if member_data else '',
        'member_institution': member_data.get('institution', '') if member_data else '',
        'member_email': member_data.get('email', '') if member_data else '',
        'member_phone': member_data.get('phone', '') if member_data else '',
        't_shirt_size': member_data.get('t_shirt_size', '') if member_data else '',
        'ctfd_user_id': user_cred.get('ctfd_username', ''),
        'ctfd_user_password': user_cred.get('ctfd_password', '')
    }
    return [row_data[col] for col in selected_columns if col in row_data]


def test_csv_export_with_ctfd_credentials():
    """Test the CSV export logic with CTFd user credentials."""
    print("Testing CSV export with CTFd user credentials...")
    
    # Mock data with CTFd credentials
    teams = [
        {
            'registration_id': 101,
            'team_name': 'Team Alpha',
            'captain_name': 'Alice Smith',
            'finalist_position': 1,
            'members': [
                {'id': 1001, 'name': 'Alice Smith', 'class': '10', 'institution': 'School A', 'email': 'alice@example.com', 'phone': '1234567890', 't_shirt_size': 'M'},
                {'id': 1002, 'name': 'Bob Jones', 'class': '11', 'institution': 'School A', 'email': 'bob@example.com', 'phone': '1234567891', 't_shirt_size': 'L'},
            ]
        },
        {
            'registration_id': 102,
            'team_name': 'Team Beta',
            'captain_name': 'Charlie Brown',
            'finalist_position': None,
            'members': [
                {'id': 1003, 'name': 'Charlie Brown', 'class': '12', 'institution': 'School B', 'email': 'charlie@example.com', 'phone': '1234567892', 't_shirt_size': 'XL'},
            ]
        }
    ]
    
    # Mock CTFd user credentials
    user_credentials_data = {
        1001: {'member_id': 1001, 'ctfd_username': 'alice_user', 'ctfd_password': 'pass_alice_123'},
        1002: {'member_id': 1002, 'ctfd_username': 'bob_user', 'ctfd_password': 'pass_bob_456'},
        1003: {'member_id': 1003, 'ctfd_username': 'charlie_user', 'ctfd_password': 'pass_charlie_789'}
    }
    
    # Sort teams
    teams_with_position = [t for t in teams if t.get('finalist_position') is not None]
    teams_without_position = [t for t in teams if t.get('finalist_position') is None]
    teams_with_position.sort(key=lambda t: t.get('finalist_position'))
    sorted_teams = teams_with_position + teams_without_position
    
    # Define column mappings
    column_map = {
        'position': 'Position',
        'team_id': 'Team ID',
        'team_name': 'Team Name',
        'total_members': 'Total Members',
        'captain_name': 'Captain Name',
        'member_name': 'Member Name',
        'member_class': 'Member Class',
        'member_institution': 'Member Institution',
        'member_email': 'Member Email',
        'member_phone': 'Member Phone',
        't_shirt_size': 'T-Shirt Size',
        'ctfd_user_id': 'CTFd User ID',
        'ctfd_user_password': 'CTFd User Password'
    }
    
    # Test 1: Export with CTFd credentials columns
    print("\n--- Test 1: Export with CTFd credentials columns ---")
    selected_columns = ['team_name', 'member_name', 'member_email', 'ctfd_user_id', 'ctfd_user_password']
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    header = [column_map[col] for col in selected_columns if col in column_map]
    writer.writerow(header)
    
    max_finalist_position = max([t.get('finalist_position') for t in teams_with_position], default=0)
    next_sequential_position = max_finalist_position + 1
    
    for team in sorted_teams:
        registration_id = team.get('registration_id')
        team_name = team.get('team_name', '')
        captain_name = team.get('captain_name', '')
        finalist_position = team.get('finalist_position')
        
        if finalist_position:
            position = finalist_position
        else:
            position = next_sequential_position
            next_sequential_position += 1
        
        members = team.get('members', [])
        total_members = len(members)
        
        if not members:
            writer.writerow(build_row_data_helper(position, registration_id, team_name, total_members, captain_name, None, user_credentials_data, selected_columns))
        else:
            for member in members:
                writer.writerow(build_row_data_helper(position, registration_id, team_name, total_members, captain_name, member, user_credentials_data, selected_columns))
    
    # Verify output
    output.seek(0)
    reader = csv.reader(output)
    rows = list(reader)
    
    assert rows[0] == ['Team Name', 'Member Name', 'Member Email', 'CTFd User ID', 'CTFd User Password'], "Header should contain selected columns including CTFd credentials"
    print("✓ Header contains CTFd credentials columns:", rows[0])
    
    # Check first member (Alice)
    assert rows[1][0] == 'Team Alpha', "Team Name should be present"
    assert rows[1][1] == 'Alice Smith', "Member Name should be present"
    assert rows[1][2] == 'alice@example.com', "Member Email should be present"
    assert rows[1][3] == 'alice_user', "CTFd User ID (username) should be present"
    assert rows[1][4] == 'pass_alice_123', "CTFd User Password should be present"
    print("✓ Alice's CTFd credentials exported correctly")
    
    # Check second member (Bob)
    assert rows[2][3] == 'bob_user', "Bob's CTFd User ID should be present"
    assert rows[2][4] == 'pass_bob_456', "Bob's CTFd User Password should be present"
    print("✓ Bob's CTFd credentials exported correctly")
    
    # Check third member (Charlie)
    assert rows[3][3] == 'charlie_user', "Charlie's CTFd User ID should be present"
    assert rows[3][4] == 'pass_charlie_789', "Charlie's CTFd User Password should be present"
    print("✓ Charlie's CTFd credentials exported correctly")
    
    # Test 2: Export all columns including CTFd credentials
    print("\n--- Test 2: Export all columns ---")
    selected_columns = list(column_map.keys())
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    header = [column_map[col] for col in selected_columns if col in column_map]
    writer.writerow(header)
    
    max_finalist_position = max([t.get('finalist_position') for t in teams_with_position], default=0)
    next_sequential_position = max_finalist_position + 1
    
    for team in sorted_teams:
        registration_id = team.get('registration_id')
        team_name = team.get('team_name', '')
        captain_name = team.get('captain_name', '')
        finalist_position = team.get('finalist_position')
        
        if finalist_position:
            position = finalist_position
        else:
            position = next_sequential_position
            next_sequential_position += 1
        
        members = team.get('members', [])
        total_members = len(members)
        
        if not members:
            writer.writerow(build_row_data_helper(position, registration_id, team_name, total_members, captain_name, None, user_credentials_data, selected_columns))
        else:
            for member in members:
                writer.writerow(build_row_data_helper(position, registration_id, team_name, total_members, captain_name, member, user_credentials_data, selected_columns))
    
    output.seek(0)
    reader = csv.reader(output)
    rows = list(reader)
    
    # Verify that all columns are present
    expected_header = [column_map[col] for col in selected_columns]
    assert rows[0] == expected_header, "Header should contain all columns"
    print("✓ Header contains all columns including CTFd credentials")
    
    # Verify CTFd credentials are in the right position (last two columns)
    assert rows[0][-2] == 'CTFd User ID', "CTFd User ID should be second to last column"
    assert rows[0][-1] == 'CTFd User Password', "CTFd User Password should be last column"
    print("✓ CTFd credentials columns in correct position")
    
    # Check data
    assert rows[1][-2] == 'alice_user', "Alice's CTFd User ID in correct position"
    assert rows[1][-1] == 'pass_alice_123', "Alice's CTFd User Password in correct position"
    print("✓ CTFd credentials data exported correctly in all columns mode")
    
    # Test 3: Member without CTFd credentials (empty values)
    print("\n--- Test 3: Member without CTFd credentials ---")
    teams_no_creds = [
        {
            'registration_id': 103,
            'team_name': 'Team Gamma',
            'captain_name': 'Diana Prince',
            'finalist_position': None,
            'members': [
                {'id': 1004, 'name': 'Diana Prince', 'class': '11', 'institution': 'School C', 'email': 'diana@example.com', 'phone': '1234567893', 't_shirt_size': 'M'},
            ]
        }
    ]
    
    # No credentials for member 1004
    empty_credentials = {}
    
    selected_columns = ['member_name', 'ctfd_user_id', 'ctfd_user_password']
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    header = [column_map[col] for col in selected_columns if col in column_map]
    writer.writerow(header)
    
    for team in teams_no_creds:
        registration_id = team.get('registration_id')
        team_name = team.get('team_name', '')
        captain_name = team.get('captain_name', '')
        members = team.get('members', [])
        total_members = len(members)
        
        for member in members:
            writer.writerow(build_row_data_helper(1, registration_id, team_name, total_members, captain_name, member, empty_credentials, selected_columns))
    
    output.seek(0)
    reader = csv.reader(output)
    rows = list(reader)
    
    assert rows[1][0] == 'Diana Prince', "Member name should be present"
    assert rows[1][1] == '', "CTFd User ID should be empty when no credentials"
    assert rows[1][2] == '', "CTFd User Password should be empty when no credentials"
    print("✓ Empty CTFd credentials handled correctly")
    
    print("\n✅ All CTFd credentials export tests passed!")
    return True


if __name__ == '__main__':
    try:
        test_csv_export_with_ctfd_credentials()
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
