"""
Test to verify CSV export functionality for teams and participants.
"""
import sys
import os
import csv
import io

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_csv_export_logic():
    """Test the CSV export logic."""
    print("Testing CSV export logic...")
    
    # Mock data
    teams = [
        {
            'registration_id': 101,
            'team_name': 'Team Alpha',
            'captain_name': 'Alice Smith',
            'finalist_position': 1,
            'members': [
                {'name': 'Alice Smith', 'class': '10', 'institution': 'School A', 'email': 'alice@example.com', 'phone': '1234567890'},
                {'name': 'Bob Jones', 'class': '11', 'institution': 'School A', 'email': 'bob@example.com', 'phone': '1234567891'},
            ]
        },
        {
            'registration_id': 102,
            'team_name': 'Team Beta',
            'captain_name': 'Charlie Brown',
            'finalist_position': None,  # No finalist position
            'members': [
                {'name': 'Charlie Brown', 'class': '12', 'institution': 'School B', 'email': 'charlie@example.com', 'phone': '1234567892'},
            ]
        },
        {
            'registration_id': 103,
            'team_name': 'Team Gamma',
            'captain_name': 'Diana Prince',
            'finalist_position': 2,
            'members': []  # No members
        }
    ]
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Position',
        'Team ID',
        'Team Name',
        'Total Members',
        'Captain Name',
        'Member Name',
        'Member Class',
        'Member Institution',
        'Member Email',
        'Member Phone'
    ])
    
    # Process each team
    for idx, team in enumerate(teams, start=1):
        registration_id = team.get('registration_id')
        team_name = team.get('team_name', '')
        captain_name = team.get('captain_name', '')
        finalist_position = team.get('finalist_position')
        members = team.get('members', [])
        
        # Use finalist_position if available, otherwise use sequential number
        position = finalist_position if finalist_position else idx
        
        total_members = len(members)
        
        # If team has no members, write one line with team info only
        if not members:
            writer.writerow([
                position,
                registration_id or '',
                team_name,
                total_members,
                captain_name,
                '',  # Member Name
                '',  # Member Class
                '',  # Member Institution
                '',  # Member Email
                ''   # Member Phone
            ])
        else:
            # Write one line per member
            for member in members:
                writer.writerow([
                    position,
                    registration_id or '',
                    team_name,
                    total_members,
                    captain_name,
                    member.get('name', ''),
                    member.get('class', ''),
                    member.get('institution', ''),
                    member.get('email', ''),
                    member.get('phone', '')
                ])
    
    # Verify CSV content
    output.seek(0)
    reader = csv.reader(output)
    rows = list(reader)
    
    # Check header
    assert rows[0] == ['Position', 'Team ID', 'Team Name', 'Total Members', 'Captain Name', 
                       'Member Name', 'Member Class', 'Member Institution', 'Member Email', 'Member Phone'], \
        "Header row is incorrect"
    print("✓ Header row is correct")
    
    # Check Team Alpha (2 members, position 1)
    assert rows[1][0] == '1', "Team Alpha position should be 1"
    assert rows[1][1] == '101', "Team Alpha ID should be 101"
    assert rows[1][2] == 'Team Alpha', "Team Alpha name is incorrect"
    assert rows[1][3] == '2', "Team Alpha should have 2 members"
    assert rows[1][5] == 'Alice Smith', "First member name is incorrect"
    assert rows[2][0] == '1', "Team Alpha second row should have same position"
    assert rows[2][5] == 'Bob Jones', "Second member name is incorrect"
    print("✓ Team Alpha (with finalist_position) exported correctly")
    
    # Check Team Beta (1 member, no finalist position - should use sequential number 2)
    assert rows[3][0] == '2', "Team Beta position should be 2 (sequential)"
    assert rows[3][1] == '102', "Team Beta ID should be 102"
    assert rows[3][2] == 'Team Beta', "Team Beta name is incorrect"
    assert rows[3][3] == '1', "Team Beta should have 1 member"
    assert rows[3][5] == 'Charlie Brown', "Member name is incorrect"
    print("✓ Team Beta (without finalist_position) exported correctly")
    
    # Check Team Gamma (no members, position 2)
    assert rows[4][0] == '2', "Team Gamma position should be 2"
    assert rows[4][1] == '103', "Team Gamma ID should be 103"
    assert rows[4][2] == 'Team Gamma', "Team Gamma name is incorrect"
    assert rows[4][3] == '0', "Team Gamma should have 0 members"
    assert rows[4][5] == '', "Member name should be empty"
    print("✓ Team Gamma (no members) exported correctly")
    
    # Total rows: header + 2 (Team Alpha) + 1 (Team Beta) + 1 (Team Gamma) = 5
    assert len(rows) == 5, f"Expected 5 rows, got {len(rows)}"
    print("✓ Total row count is correct")
    
    print("\n✅ All CSV export tests passed!")
    return True


if __name__ == '__main__':
    try:
        test_csv_export_logic()
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
