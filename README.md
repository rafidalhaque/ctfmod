# CTF Challenge Manager

A web-based platform for managing CTF (Capture The Flag) challenges for events like Science Fest. Built with Python, Flask, DaisyUI, and Tailwind CSS.

## Features

- 🔐 **Authentication**: Secure login/registration using Supabase Auth with password change support
- 📊 **Dashboard**: Overview of challenge statistics with progress tracking for all rounds and difficulties
- ⏱️ **Round Countdown Timers**: Schedule rounds with date/time and timezone, with live countdown on dashboard
- 📝 **Challenge Management**: View, filter, and manage challenges by category, difficulty, and setter
- 🔗 **GitHub Integration**: Sync challenges from GitHub PRs, approve/decline/request changes
- 🔄 **Auto-Sync**: Automatically sync challenges from GitHub at configurable intervals
- 🚀 **CTFd Integration**: Push approved challenges to CTFd with one click
- 🎯 **Target Setting**: Set and track challenge targets by category, difficulty, and round with full edit support
- 🏆 **Rounds Management**: Organize challenges into rounds (e.g., Preliminary, Final) with scheduling
- 📈 **Public Stats API**: Access detailed statistics via authenticated API
- ⚙️ **Dynamic Settings**: All configurations manageable from the UI

## Tech Stack

- **Backend**: Python 3.11+, Flask
- **Frontend**: DaisyUI, Tailwind CSS (via CDN)
- **Database**: Supabase (PostgreSQL)
- **Authentication**: Supabase Auth
- **Integrations**: GitHub API, CTFd API

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
6. **Push to CTFd**: Deploy accepted challenges to your CTFd instance
7. **Manage Rounds**: Create and organize CTF rounds with schedules in Settings
8. **Round Schedules**: Set date, time, and timezone for each round to show countdown timers on dashboard
9. **Auto-Sync**: Configure automatic GitHub sync interval in GitHub settings
10. **Set Targets**: Configure challenge targets by category, difficulty, and round
11. **Edit Targets**: Modify existing targets directly from the Settings page
12. **View Statistics**: Dashboard shows detailed stats (accepted, pending, declined) for all targets
13. **Stats API**: Generate an API key in Settings to access statistics via public API

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
