-- Create email_audit_logs table for tracking email sending attempts
CREATE TABLE IF NOT EXISTS email_audit_logs (
    id SERIAL PRIMARY KEY,
    template_id INTEGER REFERENCES email_templates(id) ON DELETE SET NULL,
    template_name VARCHAR(255),
    recipient_email VARCHAR(255) NOT NULL,
    recipient_name VARCHAR(255),
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    team_name VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'sent',  -- 'sent', 'failed'
    error_message TEXT,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_email_audit_logs_status ON email_audit_logs(status);
CREATE INDEX IF NOT EXISTS idx_email_audit_logs_sent_at ON email_audit_logs(sent_at);
CREATE INDEX IF NOT EXISTS idx_email_audit_logs_template_id ON email_audit_logs(template_id);
CREATE INDEX IF NOT EXISTS idx_email_audit_logs_team_id ON email_audit_logs(team_id);
CREATE INDEX IF NOT EXISTS idx_email_audit_logs_recipient_email ON email_audit_logs(recipient_email);

-- Enable RLS
ALTER TABLE email_audit_logs ENABLE ROW LEVEL SECURITY;

-- Create policy to allow authenticated users to read/write
CREATE POLICY "Allow authenticated users to read email_audit_logs" ON email_audit_logs
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow authenticated users to insert email_audit_logs" ON email_audit_logs
    FOR INSERT TO authenticated WITH CHECK (true);
