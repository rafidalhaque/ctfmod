# Background Task Email Feature

## Overview

This feature implements background task processing for bulk email sending with configurable delays between each email. This prevents email server throttling and improves system reliability when sending to large numbers of recipients.

## Architecture

### Components

1. **EmailQueue** (`app/email_queue.py`)
   - Singleton pattern for managing email tasks
   - Thread-safe queue for task management
   - Background worker thread for async processing
   - Status tracking for each task

2. **EmailTask** (`app/email_queue.py`)
   - Represents a single bulk email job
   - Contains recipients, template, SMTP settings, and attachments
   - Tracks progress (sent/failed counts, status, timestamps)

3. **API Endpoints** (`app/routes/settings.py`)
   - POST `/settings/email-templates/bulk-send` - Queue bulk email task
   - GET `/settings/email-tasks/<task_id>/status` - Check task status

## Usage

### Sending Bulk Emails with Delay

**Endpoint:** `POST /settings/email-templates/bulk-send`

**Request Body:**
```json
{
  "template_id": 1,
  "include_team_captains": false,
  "attachments": [1, 2],
  "status_filter": ["approved"],
  "delay_seconds": 2
}
```

**Parameters:**
- `template_id` (required): ID of the email template to use
- `include_team_captains` (optional): Include team captains in recipients
- `attachments` (optional): Array of attachment IDs
- `status_filter` (optional): Filter recipients by team status
- `delay_seconds` (optional): Delay in seconds between each email (default: 0)

**Response:**
```json
{
  "success": true,
  "task_id": "uuid-string",
  "total": 150,
  "delay_seconds": 2,
  "message": "Bulk email task queued with 150 recipients. Delay: 2s between emails."
}
```

### Checking Task Status

**Endpoint:** `GET /settings/email-tasks/<task_id>/status`

**Response:**
```json
{
  "success": true,
  "data": {
    "task_id": "uuid-string",
    "status": "processing",
    "sent_count": 75,
    "failed_count": 2,
    "total_count": 150,
    "progress_percentage": 51.33,
    "error_message": null,
    "started_at": "2025-12-11T12:00:00",
    "completed_at": null
  }
}
```

**Status Values:**
- `queued`: Task is waiting to be processed
- `processing`: Task is currently sending emails
- `completed`: Task has finished (check sent/failed counts)
- `failed`: Task encountered a fatal error

## Implementation Details

### How It Works

1. **Task Creation:**
   - User submits bulk email request via API
   - System validates inputs and creates EmailTask
   - Task is added to queue and assigned a unique ID
   - API returns immediately with task_id

2. **Background Processing:**
   - Worker thread picks up task from queue
   - Connects to SMTP server
   - Iterates through recipients
   - Sends email to each recipient
   - Applies configurable delay between emails
   - Logs results to audit table

3. **Status Tracking:**
   - Task status updated in real-time
   - Progress tracked (sent/failed counts)
   - Error messages captured for debugging
   - Audit logs written to database

### Thread Safety

- Queue uses Python's `queue.Queue` (thread-safe)
- Tasks dictionary protected by access patterns
- Singleton pattern ensures single worker thread
- Daemon thread exits gracefully on shutdown

### Error Handling

- SMTP errors caught and logged per recipient
- Task-level errors (connection, auth) fail entire task
- Partial success: Some emails sent, some failed
- Detailed error messages in task status and logs

## Benefits

1. **Non-blocking:** API responds immediately, processing happens in background
2. **Rate Limiting:** Configurable delay prevents SMTP throttling
3. **Monitoring:** Real-time progress tracking via status endpoint
4. **Reliability:** Failed emails logged for retry/investigation
5. **Audit Trail:** All sends logged to database

## Example Workflow

```python
# 1. Start bulk email with 2-second delay
response = requests.post('/settings/email-templates/bulk-send', json={
    'template_id': 5,
    'delay_seconds': 2
})
task_id = response.json()['task_id']

# 2. Check status periodically
status = requests.get(f'/settings/email-tasks/{task_id}/status')
print(f"Progress: {status.json()['data']['progress_percentage']}%")

# 3. Wait for completion
while status.json()['data']['status'] in ['queued', 'processing']:
    time.sleep(5)
    status = requests.get(f'/settings/email-tasks/{task_id}/status')

# 4. Check results
final_status = status.json()['data']
print(f"Sent: {final_status['sent_count']}, Failed: {final_status['failed_count']}")
```

## Configuration

### Email Delay
Configure via API parameter:
- **Default:** 0 seconds (no delay)
- **Recommended:** 1-5 seconds for large batches
- **Maximum:** No hard limit, but consider total time

### SMTP Settings
Configured in application settings:
- Host, Port, Username, Password
- TLS/SSL options
- Sender name and email

## Testing

Run the test suite:
```bash
python tests/test_email_queue.py
python tests/test_bulk_email_api.py
```

## Future Enhancements

Potential improvements for future versions:

1. **Persistence:** Store tasks in database for recovery after restart
2. **Retry Logic:** Automatic retry of failed emails
3. **Scheduling:** Schedule tasks for future execution
4. **Multiple Workers:** Parallel processing with worker pool
5. **Priority Queue:** High-priority tasks processed first
6. **Cancellation:** API endpoint to cancel running tasks
7. **Rate Limiting:** Automatic adaptive delay based on SMTP response

## Security Considerations

✅ **Addressed:**
- Input validation for delay_seconds parameter
- Error messages don't expose sensitive data
- Task status only accessible to authenticated users
- SMTP credentials stored securely in settings

⚠️ **Recommendations:**
- Implement rate limiting on bulk send endpoint
- Add permission checks (admin-only access)
- Monitor for abuse (excessive task creation)
- Consider email quotas per user/timeframe

## Troubleshooting

### Task Stuck in "queued" Status
- Check if worker thread is running
- Restart application to reinitialize worker
- Check application logs for errors

### High Failure Rate
- Verify SMTP settings are correct
- Check SMTP server logs for throttling
- Increase delay_seconds to reduce rate
- Verify recipient email addresses are valid

### Task "failed" with SMTP Error
- Check SMTP authentication credentials
- Verify SMTP server is accessible
- Check firewall/network settings
- Review task error_message for details

## Code Structure

```
app/
├── email_queue.py          # Background task manager
│   ├── EmailTask           # Task data structure
│   ├── EmailQueue          # Queue manager + worker
│   └── email_queue         # Singleton instance
│
├── routes/
│   └── settings.py         # API endpoints
│       ├── bulk_send_email()           # Queue task
│       └── get_email_task_status()     # Check status
│
└── __init__.py             # Flask app initialization

tests/
├── test_email_queue.py     # Unit tests
└── test_bulk_email_api.py  # Integration tests
```

## Database Schema

Email audit logs are automatically created during task processing:

```sql
email_audit_logs (
    id SERIAL,
    template_id INTEGER,
    template_name VARCHAR,
    recipient_email VARCHAR,
    recipient_name VARCHAR,
    team_id INTEGER,
    team_name VARCHAR,
    status VARCHAR,  -- 'sent' or 'failed'
    error_message TEXT,
    sent_at TIMESTAMP
)
```

## Performance

**Metrics (estimated):**
- Task creation: < 100ms
- Status check: < 10ms
- Email sending: ~500-1000ms per email (network dependent)
- Memory: ~1KB per queued task
- CPU: Minimal (background thread)

**Scalability:**
- Tested with 1000+ recipients per task
- Multiple concurrent tasks supported
- Linear time complexity: O(n) where n = recipient count
- Queue size limited by available memory

## Support

For issues or questions:
1. Check application logs
2. Review task error_message
3. Verify SMTP configuration
4. Consult this documentation
5. Contact system administrator
