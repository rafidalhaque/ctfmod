-- Create ctfd_operation_logs table for tracking CTFd API operations
CREATE TABLE IF NOT EXISTS ctfd_operation_logs (
    id SERIAL PRIMARY KEY,
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    team_registration_id BIGINT,
    member_id BIGINT REFERENCES team_members(id) ON DELETE SET NULL,
    operation_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed')),
    request_data JSONB,
    response_data JSONB,
    error_message TEXT,
    ctfd_entity_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_ctfd_operation_logs_team_id ON ctfd_operation_logs(team_id);
CREATE INDEX IF NOT EXISTS idx_ctfd_operation_logs_member_id ON ctfd_operation_logs(member_id);
CREATE INDEX IF NOT EXISTS idx_ctfd_operation_logs_operation_type ON ctfd_operation_logs(operation_type);
CREATE INDEX IF NOT EXISTS idx_ctfd_operation_logs_status ON ctfd_operation_logs(status);
CREATE INDEX IF NOT EXISTS idx_ctfd_operation_logs_created_at ON ctfd_operation_logs(created_at);

-- Enable RLS
ALTER TABLE ctfd_operation_logs ENABLE ROW LEVEL SECURITY;

-- Create policy to allow authenticated users to read/write
CREATE POLICY "Allow authenticated users to read ctfd_operation_logs" ON ctfd_operation_logs
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow authenticated users to insert ctfd_operation_logs" ON ctfd_operation_logs
    FOR INSERT TO authenticated WITH CHECK (true);
