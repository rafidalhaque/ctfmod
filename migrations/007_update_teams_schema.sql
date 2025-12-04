-- CTF Challenge Manager Database Migration 007
-- Updates teams and team_members schema to link via registration_id
-- Run this in your Supabase SQL Editor after previous migrations

-- ============================
-- IMPORTANT: This migration updates the foreign key relationship
-- team_members.team_id now references teams.registration_id instead of teams.id
-- ============================

-- Step 1: Drop existing foreign key constraint on team_members.team_id
ALTER TABLE team_members DROP CONSTRAINT IF EXISTS team_members_team_id_fkey;

-- Step 2: Drop existing foreign key constraint on ctfd_team_credentials.team_id
ALTER TABLE ctfd_team_credentials DROP CONSTRAINT IF EXISTS ctfd_team_credentials_team_id_fkey;

-- Step 3: Migrate existing data - update team_id values from teams.id to teams.registration_id
-- This updates team_members.team_id to use registration_id instead of id
UPDATE team_members tm
SET team_id = t.registration_id
FROM teams t
WHERE tm.team_id = t.id AND t.registration_id IS NOT NULL;

-- Step 4: Migrate ctfd_team_credentials.team_id to use registration_id
UPDATE ctfd_team_credentials ctc
SET team_id = t.registration_id
FROM teams t
WHERE ctc.team_id = t.id AND t.registration_id IS NOT NULL;

-- Step 5: Add new foreign key constraint referencing teams.registration_id
ALTER TABLE team_members 
ADD CONSTRAINT team_members_team_id_fkey 
FOREIGN KEY (team_id) REFERENCES teams(registration_id) ON DELETE CASCADE;

-- Step 6: Add new foreign key constraint for ctfd_team_credentials
ALTER TABLE ctfd_team_credentials 
ADD CONSTRAINT ctfd_team_credentials_team_id_fkey 
FOREIGN KEY (team_id) REFERENCES teams(registration_id) ON DELETE CASCADE;

-- Step 7: Add trigger for update timestamp on teams (if not exists)
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_teams_timestamp ON teams;
CREATE TRIGGER update_teams_timestamp 
BEFORE UPDATE ON teams 
FOR EACH ROW
EXECUTE FUNCTION update_timestamp();
