-- CTF Challenge Manager Database Migration 004
-- Adds email_templates table for dynamic email designer
-- Run this in your Supabase SQL Editor after 003_add_round_schedule.sql

-- Email templates table for storing dynamic email templates
CREATE TABLE IF NOT EXISTS email_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for template name lookups
CREATE INDEX IF NOT EXISTS idx_email_templates_name ON email_templates(name);

-- Enable Row Level Security on email_templates table
ALTER TABLE email_templates ENABLE ROW LEVEL SECURITY;

-- Create policies for email_templates table
CREATE POLICY "Allow authenticated users to read email_templates"
    ON email_templates FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to insert email_templates"
    ON email_templates FOR INSERT
    TO authenticated
    WITH CHECK (true);

CREATE POLICY "Allow authenticated users to update email_templates"
    ON email_templates FOR UPDATE
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to delete email_templates"
    ON email_templates FOR DELETE
    TO authenticated
    USING (true);

-- Trigger for updated_at
CREATE TRIGGER update_email_templates_updated_at
    BEFORE UPDATE ON email_templates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
