-- Migration 010: Add fields for conflict resolution during GitHub sync
-- This migration adds fields to track manual edits and detect conflicts

-- Add manually_edited flag to track if challenge was edited in portal
ALTER TABLE challenges 
ADD COLUMN IF NOT EXISTS manually_edited BOOLEAN DEFAULT FALSE;

-- Add github_data_snapshot to store original GitHub data for conflict detection
ALTER TABLE challenges 
ADD COLUMN IF NOT EXISTS github_data_snapshot JSONB;

-- Add has_conflicts flag to indicate when conflicts are detected
ALTER TABLE challenges 
ADD COLUMN IF NOT EXISTS has_conflicts BOOLEAN DEFAULT FALSE;

-- Add conflicting_fields to store which fields have conflicts
ALTER TABLE challenges 
ADD COLUMN IF NOT EXISTS conflicting_fields JSONB;

-- Create index for faster queries on challenges with conflicts
CREATE INDEX IF NOT EXISTS idx_challenges_has_conflicts ON challenges(has_conflicts) WHERE has_conflicts = TRUE;

-- Create index for manually edited challenges
CREATE INDEX IF NOT EXISTS idx_challenges_manually_edited ON challenges(manually_edited) WHERE manually_edited = TRUE;
