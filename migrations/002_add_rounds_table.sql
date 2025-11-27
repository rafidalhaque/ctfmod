-- CTF Challenge Manager Database Migration 002
-- Adds rounds table and round_id to targets and challenges tables
-- Run this in your Supabase SQL Editor after 001_initial_schema.sql

-- Rounds table for organizing challenges into rounds (e.g., Preliminary, Final)
CREATE TABLE IF NOT EXISTS rounds (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add round_id column to targets table
ALTER TABLE targets
ADD COLUMN IF NOT EXISTS round_id INTEGER REFERENCES rounds(id) ON DELETE SET NULL;

-- Add round_id column to challenges table
ALTER TABLE challenges
ADD COLUMN IF NOT EXISTS round_id INTEGER REFERENCES rounds(id) ON DELETE SET NULL;

-- Update unique constraint on targets to include round_id
-- First drop the old unique constraint if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'targets_category_difficulty_key'
    ) THEN
        ALTER TABLE targets DROP CONSTRAINT targets_category_difficulty_key;
    END IF;
END $$;

-- Create new unique constraint including round_id
-- Using a partial unique index to handle NULL values properly
CREATE UNIQUE INDEX IF NOT EXISTS idx_targets_category_difficulty_round
ON targets (category, difficulty, COALESCE(round_id, 0));

-- Create indexes for round_id columns
CREATE INDEX IF NOT EXISTS idx_targets_round_id ON targets(round_id);
CREATE INDEX IF NOT EXISTS idx_challenges_round_id ON challenges(round_id);

-- Enable Row Level Security on rounds table
ALTER TABLE rounds ENABLE ROW LEVEL SECURITY;

-- Create policies for rounds table
CREATE POLICY "Allow authenticated users to read rounds"
    ON rounds FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to insert rounds"
    ON rounds FOR INSERT
    TO authenticated
    WITH CHECK (true);

CREATE POLICY "Allow authenticated users to update rounds"
    ON rounds FOR UPDATE
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to delete rounds"
    ON rounds FOR DELETE
    TO authenticated
    USING (true);
