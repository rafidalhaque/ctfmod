-- Migration: Add email attachments table
-- This table stores information about file attachments for email templates

CREATE TABLE IF NOT EXISTS email_attachments (
    id SERIAL PRIMARY KEY,
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL UNIQUE,
    file_size INTEGER NOT NULL DEFAULT 0,
    mime_type VARCHAR(100) DEFAULT 'application/octet-stream',
    is_image BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_email_attachments_is_image ON email_attachments(is_image);
CREATE INDEX IF NOT EXISTS idx_email_attachments_created_at ON email_attachments(created_at DESC);

-- Comment on table
COMMENT ON TABLE email_attachments IS 'Stores file attachments for email templates';
