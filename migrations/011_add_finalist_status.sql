-- CTF Challenge Manager Database Migration 011
-- Adds finalist status support with position and round reference
-- Run this in your Supabase SQL Editor after 010_add_conflict_resolution_fields.sql

-- ============================
-- Add finalist-related columns to teams table
-- ============================

-- Add is_finalist flag (boolean to easily filter finalist teams)
ALTER TABLE teams ADD COLUMN IF NOT EXISTS is_finalist BOOLEAN DEFAULT FALSE;

-- Add reference to the round from which the team qualified as finalist
ALTER TABLE teams ADD COLUMN IF NOT EXISTS finalist_round_id INTEGER REFERENCES rounds(id) ON DELETE SET NULL;

-- Add position/rank from the previous round's scoreboard
ALTER TABLE teams ADD COLUMN IF NOT EXISTS finalist_position INTEGER;

-- Optional: Store the team's score from the previous round for reference
ALTER TABLE teams ADD COLUMN IF NOT EXISTS finalist_score_previous_round NUMERIC;

-- Create index for filtering finalist teams
CREATE INDEX IF NOT EXISTS idx_teams_is_finalist ON teams(is_finalist);
CREATE INDEX IF NOT EXISTS idx_teams_finalist_round_id ON teams(finalist_round_id);

-- Add constraint to ensure finalist_position is positive when set
ALTER TABLE teams ADD CONSTRAINT chk_finalist_position_positive 
    CHECK (finalist_position IS NULL OR finalist_position > 0);

-- Ensure that if is_finalist is true, then finalist_round_id and finalist_position must be set
-- This can be done via application logic or a trigger, keeping it flexible for now

-- Update trigger for updated_at already exists from previous migrations
