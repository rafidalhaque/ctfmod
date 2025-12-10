# CTF Challenge Manager

A web-based platform for managing CTF (Capture The Flag) challenges for events like Science Fest. Built with Python, Flask, DaisyUI, and Tailwind CSS.

## Features

- 🔐 **Authentication**: Secure login/registration using Supabase Auth with password change support
- 📊 **Dashboard**: Overview of challenge statistics with progress tracking for all rounds and difficulties
- ⏱️ **Round Countdown Timers**: Schedule rounds with date/time and timezone, with live countdown on dashboard
- 📝 **Challenge Management**: View, filter, and manage challenges by category, difficulty, and setter
- 🔗 **GitHub Integration**: Sync challenges from GitHub PRs, approve/decline/request changes
- 🔄 **Auto-Sync**: Automatically sync challenges from GitHub at configurable intervals
- 🚀 **CTFd Integration**: Push approved challenges to CTFd with configurable field selection and settings
- 🎯 **Target Setting**: Set and track challenge targets by category, difficulty, and round with full edit support
- 🏆 **Rounds Management**: Organize challenges into rounds (e.g., Preliminary, Final) with scheduling
- 📈 **Public Stats API**: Access detailed statistics via authenticated API
- ⚙️ **Dynamic Settings**: All configurations manageable from the UI
- 📧 **SMTP Email Configuration**: Configure SMTP settings for sending emails with test functionality
- ✉️ **Dynamic Email Designer**: Create and manage email templates with variable placeholders
- 👥 **Teams & Participants Management**: View teams, members, and their CTFd credentials (passwords in plain text)

## Tech Stack

- **Backend**: Python 3.11+, Flask
- **Frontend**: DaisyUI, Tailwind CSS (via CDN)
- **Database**: Supabase (PostgreSQL)
- **Authentication**: Supabase Auth
- **Integrations**: GitHub API, CTFd API, SMTP Email

## Installation

1. Clone the repository:
```bash
git clone https://github.com/rafidalhaque/ctfmod.git
cd ctfmod
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Set up Supabase:
   - Create a new Supabase project
   - Run the SQL migrations from `migrations/` folder in order:
     1. `001_initial_schema.sql` - Creates base tables (challenges, settings, targets)
     2. `002_add_rounds_table.sql` - Adds rounds table and round support for targets
     3. `003_add_round_schedule.sql` - Adds schedule fields to rounds (start_datetime, timezone)
     4. `004_add_email_templates.sql` - Adds email templates table for dynamic email designer
     5. `005_add_teams_and_credentials.sql` - Adds teams, team_members, and CTFd credentials tables
   - Update `.env` with your Supabase URL and key

6. Run the application:
```bash
python run.py
```

The application will be available at `http://localhost:5000`

## Database Migrations

### Migration 001: Initial Schema
Creates the base tables for the application:
- `challenges` - Stores CTF challenges with metadata
- `settings` - Key-value store for application settings
- `targets` - Challenge targets by category and difficulty

### Migration 002: Rounds Support
Adds support for organizing challenges into rounds:
- `rounds` - Table for defining CTF rounds (e.g., Preliminary, Final)
- Adds `round_id` foreign key to `targets` and `challenges` tables
- Updates unique constraint on targets to include round_id

### Migration 004: Email Templates
Adds support for dynamic email templates:
- `email_templates` - Stores email templates with subject, body, and variable placeholders

### Migration 005: Teams and Credentials
Adds support for teams and participant management:
- `teams` - Stores team information (name, captain, contact, status, etc.)
- `team_members` - Stores team member details (name, email, institution, etc.)
- `ctfd_team_credentials` - Stores CTFd team-level credentials (username and password in plain text)
- `ctfd_user_credentials` - Stores CTFd user-level credentials (username and password in plain text)

Run migrations in your Supabase SQL Editor in numerical order.

## Database Schema

### Challenges Table
```sql
CREATE TABLE challenges (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    difficulty VARCHAR(50) DEFAULT 'Medium',
    description TEXT,
    points INTEGER DEFAULT 100,
    flag TEXT,
    setter VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    pr_number INTEGER,
    branch VARCHAR(255),
    ctfd_id INTEGER,
    pushed_to_ctfd BOOLEAN DEFAULT FALSE,
    round_id INTEGER REFERENCES rounds(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Rounds Table
```sql
CREATE TABLE rounds (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Targets Table
```sql
CREATE TABLE targets (
    id SERIAL PRIMARY KEY,
    category VARCHAR(100) NOT NULL,
    difficulty VARCHAR(50) NOT NULL,
    target_count INTEGER DEFAULT 0,
    round_id INTEGER REFERENCES rounds(id),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Settings Table
```sql
CREATE TABLE settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Email Templates Table
```sql
CREATE TABLE email_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Teams Table
```sql
CREATE TABLE teams (
    id BIGSERIAL PRIMARY KEY,
    registration_id BIGINT UNIQUE,
    team_name VARCHAR(255) NOT NULL,
    project_name TEXT,
    captain_name VARCHAR(255),
    captain_email VARCHAR(255),
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    contact_number VARCHAR(50),
    status VARCHAR(50) DEFAULT 'pending',
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Team Members Table
```sql
CREATE TABLE team_members (
    id BIGSERIAL PRIMARY KEY,
    team_id BIGINT REFERENCES teams(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    institution VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    role VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### CTFd Team Credentials Table
```sql
CREATE TABLE ctfd_team_credentials (
    id BIGSERIAL PRIMARY KEY,
    team_id BIGINT REFERENCES teams(id) ON DELETE CASCADE,
    ctfd_team_username VARCHAR(255) UNIQUE NOT NULL,
    ctfd_team_password TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### CTFd User Credentials Table
```sql
CREATE TABLE ctfd_user_credentials (
    id BIGSERIAL PRIMARY KEY,
    member_id BIGINT REFERENCES team_members(id) ON DELETE CASCADE,
    ctfd_username VARCHAR(255) UNIQUE NOT NULL,
    ctfd_password TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask secret key for session management |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase anon/public key |
| `GITHUB_TOKEN` | GitHub personal access token with repo access |
| `GITHUB_REPO_OWNER` | GitHub repository owner (username/org) |
| `GITHUB_REPO_NAME` | GitHub repository name |
| `CTFD_URL` | CTFd instance URL |
| `CTFD_API_KEY` | CTFd API key |

## Usage

1. **Login/Register**: Create an account or login with existing credentials
2. **Change Password**: Update your password from the user menu dropdown
3. **Sync from GitHub**: Click "Sync from GitHub" to import challenges from open PRs
4. **Review Challenges**: View challenge details, README, and challenge.yml
5. **Approve/Decline**: Merge or close PRs directly from the platform
6. **Push to CTFd**: Deploy accepted challenges to your CTFd instance with configurable settings:
   - Select which fields to include (description, flag, connection info, attribution, etc.)
   - Configure challenge settings (type: standard/dynamic, state: visible/hidden, max attempts)
   - Save your preferences as defaults for future challenges
7. **Manage Rounds**: Create and organize CTF rounds with schedules in Settings
8. **Round Schedules**: Set date, time, and timezone for each round to show countdown timers on dashboard
9. **Auto-Sync**: Configure automatic GitHub sync interval in GitHub settings
10. **Set Targets**: Configure challenge targets by category, difficulty, and round
11. **Edit Targets**: Modify existing targets directly from the Settings page
12. **View Statistics**: Dashboard shows detailed stats (accepted, pending, declined) for all targets
13. **Stats API**: Generate an API key in Settings to access statistics via public API
14. **SMTP Configuration**: Configure email server settings (host, port, username, password, TLS/SSL) in Settings
15. **Test Email**: Send a test email to verify SMTP configuration
16. **Email Templates**: Create multiple dynamic email templates with variable placeholders
17. **Template Preview**: Preview email templates with sample data before saving
18. **Bulk Email Sending**: Send emails to all participants using any template with automatic variable substitution
19. **View Teams**: Access team list with CTFd credentials (passwords shown in plain text)
20. **View Participants**: Access participant list with individual CTFd credentials (passwords shown in plain text)

### CTFd Push Configuration

When pushing a challenge to CTFd, you can configure:

**Fields to Include:**
- ✓ Name (required)
- ✓ Category (required)
- ✓ Points/Value (required)
- ☑ Description
- ☑ Flag
- ☑ Connection Info (from challenge.yml)
- ☑ Attribution/Author (from challenge.yml)
- ☐ Requirements (from challenge.yml)

**Challenge Settings:**
- **Type**: Standard or Dynamic scoring
  - **Dynamic**: Automatically includes dynamic scoring fields from challenge.yml (initial, minimum, decay, function)
- **State**: Hidden (default) or Visible - Hidden challenges won't appear to players until made visible
- **Max Attempts**: 0 for unlimited, or set a specific number

**Save as Default**: Check this option to remember your preferences for future challenges. Settings are stored in your browser's localStorage.

**Note**: For dynamic challenges, ensure your challenge.yml includes the required dynamic scoring fields (`initial`, `minimum`, `decay`, `function`) for proper configuration.

### Email Template Variables

Available placeholders for email templates:
- **Team/Participant**: `{{team_name}}`, `{{team_ctfd_username}}`, `{{team_ctfd_password}}`, `{{user_name}}`, `{{user_email}}`, `{{user_ctfd_username}}`, `{{user_ctfd_password}}`
- **Event**: `{{event_name}}`, `{{site_name}}`, `{{date}}`, `{{time}}`
- **Challenge**: `{{challenge_name}}`, `{{category}}`, `{{difficulty}}`, `{{setter}}`, `{{round_name}}`

## Stats API

The Stats API provides detailed statistics about challenges, rounds, and targets via a public endpoint.

### Authentication

All requests to the Stats API require an API key. Generate one in **Settings > Stats API**.

Include the API key in the request header:
```
X-API-Key: ctfm_your_api_key_here
```

### Endpoint

**GET** `/api/v1/stats`

### Response

```json
{
  "success": true,
  "data": {
    "total_challenges": 25,
    "accepted_challenges": 15,
    "pending_challenges": 8,
    "declined_challenges": 2,
    "by_category": {
      "Web": {"total": 10, "accepted": 6, "pending": 3, "declined": 1}
    },
    "by_difficulty": {
      "Easy": {"total": 8, "accepted": 5, "pending": 2, "declined": 1}
    },
    "by_round": {
      "Preliminary": {"total": 12, "accepted": 8, "pending": 3, "declined": 1}
    },
    "by_setter": {
      "user123": {"total": 5, "accepted": 3, "pending": 1, "declined": 1}
    },
    "targets": [
      {
        "category": "Web",
        "difficulty": "Easy",
        "round": "Preliminary",
        "target_count": 5,
        "accepted_count": 3,
        "progress_percentage": 60.0
      }
    ],
    "rounds": [
      {
        "id": 1,
        "name": "Preliminary",
        "description": "First round",
        "start_datetime": "2024-12-01T10:00:00",
        "timezone": "Asia/Dhaka"
      }
    ]
  }
}
```

### Error Responses

| Status Code | Description |
|-------------|-------------|
| 401 | Invalid or missing API key |
| 500 | Server error |

## License

MIT License
