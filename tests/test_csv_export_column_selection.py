"""
Test to verify CSV export column selection functionality.
"""
import sys
import os
import csv
import io

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_csv_export_selected_columns():
    """Test the CSV export logic with column selection."""
    print("Testing CSV export with column selection...")
    
    # Mock data
    teams = [
        {
            'registration_id': 101,
            'team_name': 'Team Alpha',
            'captain_name': 'Alice Smith',
            'finalist_position': 1,
            'members': [
                {'name': 'Alice Smith', 'class': '10', 'institution': 'School A', 'email': 'alice@example.com', 'phone': '1234567890', 't_shirt_size': 'M'},
                {'name': 'Bob Jones', 'class': '11', 'institution': 'School A', 'email': 'bob@example.com', 'phone': '1234567891', 't_shirt_size': 'L'},
            ]
        },
        {
            'registration_id': 102,
            'team_name': 'Team Beta',
            'captain_name': 'Charlie Brown',
            'finalist_position': None,
            'members': [
                {'name': 'Charlie Brown', 'class': '12', 'institution': 'School B', 'email': 'charlie@example.com', 'phone': '1234567892', 't_shirt_size': 'XL'},
            ]
        }
    ]
    
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
        't_shirt_size': 'T-Shirt Size'
    }
    
    # Test 1: Export only basic team columns
    print("\n--- Test 1: Export only basic team columns ---")
    selected_columns = ['position', 'team_id', 'team_name', 'captain_name']
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header with selected columns only
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
        
        def build_row_data(member_data=None):
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
                't_shirt_size': member_data.get('t_shirt_size', '') if member_data else ''
            }
            return [row_data[col] for col in selected_columns if col in row_data]
        
        if not members:
            writer.writerow(build_row_data())
        else:
            for member in members:
                writer.writerow(build_row_data(member))
    
    # Verify output
    output.seek(0)
    reader = csv.reader(output)
    rows = list(reader)
    
    assert rows[0] == ['Position', 'Team ID', 'Team Name', 'Captain Name'], "Header should contain only selected columns"
    print("✓ Header contains only selected columns:", rows[0])
    
    # Check data rows
    assert len(rows[0]) == 4, "Each row should have exactly 4 columns"
    assert rows[1][0] == '1', "Position should be present"
    assert rows[1][1] == '101', "Team ID should be present"
    assert rows[1][2] == 'Team Alpha', "Team Name should be present"
    assert rows[1][3] == 'Alice Smith', "Captain Name should be present"
    print("✓ Data rows contain only selected columns")
    
    # Test 2: Export only member-specific columns
    print("\n--- Test 2: Export only member-specific columns ---")
    selected_columns = ['team_name', 'member_name', 'member_email']
    
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
        
        def build_row_data(member_data=None):
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
                't_shirt_size': member_data.get('t_shirt_size', '') if member_data else ''
            }
            return [row_data[col] for col in selected_columns if col in row_data]
        
        if not members:
            writer.writerow(build_row_data())
        else:
            for member in members:
                writer.writerow(build_row_data(member))
    
    output.seek(0)
    reader = csv.reader(output)
    rows = list(reader)
    
    assert rows[0] == ['Team Name', 'Member Name', 'Member Email'], "Header should contain only selected columns"
    print("✓ Header contains only selected columns:", rows[0])
    
    assert len(rows[0]) == 3, "Each row should have exactly 3 columns"
    assert rows[1][0] == 'Team Alpha', "Team Name should be present"
    assert rows[1][1] == 'Alice Smith', "Member Name should be present"
    assert rows[1][2] == 'alice@example.com', "Member Email should be present"
    print("✓ Data rows contain only selected columns")
    
    # Test 3: Export single column
    print("\n--- Test 3: Export single column ---")
    selected_columns = ['team_name']
    
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
        
        def build_row_data(member_data=None):
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
                't_shirt_size': member_data.get('t_shirt_size', '') if member_data else ''
            }
            return [row_data[col] for col in selected_columns if col in row_data]
        
        if not members:
            writer.writerow(build_row_data())
        else:
            for member in members:
                writer.writerow(build_row_data(member))
    
    output.seek(0)
    reader = csv.reader(output)
    rows = list(reader)
    
    assert rows[0] == ['Team Name'], "Header should contain only selected column"
    print("✓ Header contains only selected column:", rows[0])
    
    assert len(rows[0]) == 1, "Each row should have exactly 1 column"
    assert rows[1][0] == 'Team Alpha', "Team Name should be present"
    print("✓ Data rows contain only selected column")
    
    print("\n✅ All column selection tests passed!")
    return True


if __name__ == '__main__':
    try:
        test_csv_export_selected_columns()
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
