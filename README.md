# CTF Challenge Manager

A web-based platform for managing CTF (Capture The Flag) challenges for events like Science Fest. Built with Python, Flask, DaisyUI, and Tailwind CSS.

## Features

- 🔐 **Authentication**: Secure login/registration using Supabase Auth with password change support
- 📊 **Dashboard**: Overview of challenge statistics with progress tracking for all rounds and difficulties
- 📝 **Challenge Management**: View, filter, and manage challenges by category, difficulty, and setter
- 🔗 **GitHub Integration**: Sync challenges from GitHub PRs, approve/decline/request changes
- 🚀 **CTFd Integration**: Push approved challenges to CTFd with one click
- 🎯 **Target Setting**: Set and track challenge targets by category, difficulty, and round with full edit support
- 🏆 **Rounds Management**: Organize challenges into rounds (e.g., Preliminary, Final)
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
7. **Manage Rounds**: Create and organize CTF rounds in Settings
8. **Set Targets**: Configure challenge targets by category, difficulty, and round
9. **Edit Targets**: Modify existing targets directly from the Settings page
10. **View Statistics**: Dashboard shows detailed stats (accepted, pending, declined) for all targets

## License

MIT License
