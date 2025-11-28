-- CTF Challenge Manager Database Migration 003
-- Adds schedule fields to rounds table (start_datetime, timezone)
-- Run this in your Supabase SQL Editor after 002_add_rounds_table.sql

-- Add schedule columns to rounds table
ALTER TABLE rounds
ADD COLUMN IF NOT EXISTS start_datetime TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'UTC';

-- Create index for schedule queries
CREATE INDEX IF NOT EXISTS idx_rounds_start_datetime ON rounds(start_datetime);
