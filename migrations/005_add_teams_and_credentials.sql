-- CTF Challenge Manager Database Migration 005
-- Adds teams, team_members, and CTFd credentials tables
-- Run this in your Supabase SQL Editor after 004_add_email_templates.sql

-- ============================
-- TEAMS TABLE
-- ============================
CREATE TABLE IF NOT EXISTS teams (
    id BIGSERIAL PRIMARY KEY,
    registration_id BIGINT UNIQUE,
    team_name VARCHAR(255) NOT NULL,
    project_name TEXT,
    proposal_file_path TEXT,
    proposal_file_url TEXT,
    captain_name VARCHAR(255),
    captain_email VARCHAR(255),
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    contact_number VARCHAR(50),
    status VARCHAR(50) DEFAULT 'pending',
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================
-- TEAM MEMBERS TABLE
-- ============================
CREATE TABLE IF NOT EXISTS team_members (
    id BIGSERIAL PRIMARY KEY,
    team_id BIGINT REFERENCES teams(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    class VARCHAR(255),
    institution VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    id_card_photo_path TEXT,
    id_card_photo_url TEXT,
    date_of_birth DATE,
    gender VARCHAR(20),
    division VARCHAR(100),
    district VARCHAR(100),
    thana VARCHAR(100),
    address TEXT,
    father_name VARCHAR(255),
    father_number VARCHAR(50),
    t_shirt_size VARCHAR(10),
    category VARCHAR(50),
    role VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================
-- CTFd CREDENTIALS — TEAM LEVEL
-- ============================
CREATE TABLE IF NOT EXISTS ctfd_team_credentials (
    id BIGSERIAL PRIMARY KEY,
    team_id BIGINT REFERENCES teams(id) ON DELETE CASCADE,
    ctfd_team_username VARCHAR(255) UNIQUE NOT NULL,
    ctfd_team_password TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================
-- CTFd CREDENTIALS — USER LEVEL
-- ============================
CREATE TABLE IF NOT EXISTS ctfd_user_credentials (
    id BIGSERIAL PRIMARY KEY,
    member_id BIGINT REFERENCES team_members(id) ON DELETE CASCADE,
    ctfd_username VARCHAR(255) UNIQUE NOT NULL,
    ctfd_password TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_teams_team_name ON teams(team_name);
CREATE INDEX IF NOT EXISTS idx_teams_status ON teams(status);
CREATE INDEX IF NOT EXISTS idx_team_members_team_id ON team_members(team_id);
CREATE INDEX IF NOT EXISTS idx_team_members_email ON team_members(email);
CREATE INDEX IF NOT EXISTS idx_ctfd_team_credentials_team_id ON ctfd_team_credentials(team_id);
CREATE INDEX IF NOT EXISTS idx_ctfd_user_credentials_member_id ON ctfd_user_credentials(member_id);

-- Enable Row Level Security
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE ctfd_team_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE ctfd_user_credentials ENABLE ROW LEVEL SECURITY;

-- Create policies for teams table
CREATE POLICY "Allow authenticated users to read teams"
    ON teams FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to insert teams"
    ON teams FOR INSERT
    TO authenticated
    WITH CHECK (true);

CREATE POLICY "Allow authenticated users to update teams"
    ON teams FOR UPDATE
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to delete teams"
    ON teams FOR DELETE
    TO authenticated
    USING (true);

-- Create policies for team_members table
CREATE POLICY "Allow authenticated users to read team_members"
    ON team_members FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to insert team_members"
    ON team_members FOR INSERT
    TO authenticated
    WITH CHECK (true);

CREATE POLICY "Allow authenticated users to update team_members"
    ON team_members FOR UPDATE
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to delete team_members"
    ON team_members FOR DELETE
    TO authenticated
    USING (true);

-- Create policies for ctfd_team_credentials table
CREATE POLICY "Allow authenticated users to read ctfd_team_credentials"
    ON ctfd_team_credentials FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to insert ctfd_team_credentials"
    ON ctfd_team_credentials FOR INSERT
    TO authenticated
    WITH CHECK (true);

CREATE POLICY "Allow authenticated users to update ctfd_team_credentials"
    ON ctfd_team_credentials FOR UPDATE
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to delete ctfd_team_credentials"
    ON ctfd_team_credentials FOR DELETE
    TO authenticated
    USING (true);

-- Create policies for ctfd_user_credentials table
CREATE POLICY "Allow authenticated users to read ctfd_user_credentials"
    ON ctfd_user_credentials FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to insert ctfd_user_credentials"
    ON ctfd_user_credentials FOR INSERT
    TO authenticated
    WITH CHECK (true);

CREATE POLICY "Allow authenticated users to update ctfd_user_credentials"
    ON ctfd_user_credentials FOR UPDATE
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to delete ctfd_user_credentials"
    ON ctfd_user_credentials FOR DELETE
    TO authenticated
    USING (true);

-- Trigger for updated_at on teams
CREATE TRIGGER update_teams_updated_at
    BEFORE UPDATE ON teams
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
