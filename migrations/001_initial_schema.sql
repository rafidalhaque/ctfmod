-- CTF Challenge Manager Database Schema
-- Run this in your Supabase SQL Editor

-- Enable Row Level Security
ALTER DATABASE postgres SET "app.jwt_secret" TO 'your-jwt-secret';

-- Challenges table
CREATE TABLE IF NOT EXISTS challenges (
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Settings table
CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Targets table
CREATE TABLE IF NOT EXISTS targets (
    id SERIAL PRIMARY KEY,
    category VARCHAR(100) NOT NULL,
    difficulty VARCHAR(50) NOT NULL,
    target_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(category, difficulty)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_challenges_category ON challenges(category);
CREATE INDEX IF NOT EXISTS idx_challenges_difficulty ON challenges(difficulty);
CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges(status);
CREATE INDEX IF NOT EXISTS idx_challenges_setter ON challenges(setter);
CREATE INDEX IF NOT EXISTS idx_challenges_pr_number ON challenges(pr_number);
CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key);
CREATE INDEX IF NOT EXISTS idx_targets_category_difficulty ON targets(category, difficulty);

-- Enable Row Level Security (RLS)
ALTER TABLE challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE targets ENABLE ROW LEVEL SECURITY;

-- Create policies for authenticated users
CREATE POLICY "Allow authenticated users to read challenges"
    ON challenges FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to insert challenges"
    ON challenges FOR INSERT
    TO authenticated
    WITH CHECK (true);

CREATE POLICY "Allow authenticated users to update challenges"
    ON challenges FOR UPDATE
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to delete challenges"
    ON challenges FOR DELETE
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to read settings"
    ON settings FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to insert settings"
    ON settings FOR INSERT
    TO authenticated
    WITH CHECK (true);

CREATE POLICY "Allow authenticated users to update settings"
    ON settings FOR UPDATE
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to read targets"
    ON targets FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to insert targets"
    ON targets FOR INSERT
    TO authenticated
    WITH CHECK (true);

CREATE POLICY "Allow authenticated users to update targets"
    ON targets FOR UPDATE
    TO authenticated
    USING (true);

CREATE POLICY "Allow authenticated users to delete targets"
    ON targets FOR DELETE
    TO authenticated
    USING (true);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_challenges_updated_at
    BEFORE UPDATE ON challenges
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_settings_updated_at
    BEFORE UPDATE ON settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert default settings
INSERT INTO settings (key, value) VALUES
    ('site_name', 'CTF Challenge Manager'),
    ('event_name', 'Science Fest CTF'),
    ('categories', 'Web, Pwn, Rev, Crypto, Forensics, Misc'),
    ('difficulties', 'Easy, Medium, Hard')
ON CONFLICT (key) DO NOTHING;
