"""
Background task manager for bulk email sending with delays.
"""
import threading
import queue
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
import os
import re
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


class EmailTask:
    """Represents a single email sending task."""
    
    def __init__(self, task_id: str, template_id: int, template_name: str, 
                 recipients: List[Dict], smtp_settings: Dict, 
                 template_data: Dict, attachments: List[Dict], 
                 upload_folder: str, delay_seconds: int = 0):
        self.task_id = task_id
        self.template_id = template_id
        self.template_name = template_name
        self.recipients = recipients
        self.smtp_settings = smtp_settings
        self.template_data = template_data
        self.attachments = attachments
        self.upload_folder = upload_folder
        self.delay_seconds = delay_seconds
        self.status = 'queued'  # queued, processing, completed, failed
        self.sent_count = 0
        self.failed_count = 0
        self.total_count = len(recipients)
        self.error_message = None
        self.started_at = None
        self.completed_at = None
        self.audit_logs = []


class EmailQueue:
    """Singleton queue manager for handling bulk email tasks with delays."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.task_queue = queue.Queue()
        self.tasks: Dict[str, EmailTask] = {}
        self.worker_thread = None
        self.running = False
        self.supabase_client = None
        logger.info("EmailQueue initialized")
    
    def set_supabase_client(self, client):
        """Set the Supabase client for logging."""
        self.supabase_client = client
    
    def start_worker(self):
        """Start the background worker thread."""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.running = True
            self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
            self.worker_thread.start()
            logger.info("Email worker thread started")
    
    def stop_worker(self):
        """Stop the background worker thread."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
            logger.info("Email worker thread stopped")
    
    def add_task(self, task: EmailTask) -> str:
        """Add a new email task to the queue."""
        self.tasks[task.task_id] = task
        self.task_queue.put(task.task_id)
        logger.info(f"Task {task.task_id} added to queue with {task.total_count} recipients")
        
        # Ensure worker is running
        self.start_worker()
        
        return task.task_id
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get the status of a task."""
        task = self.tasks.get(task_id)
        if not task:
            return None
        
        return {
            'task_id': task.task_id,
            'status': task.status,
            'sent_count': task.sent_count,
            'failed_count': task.failed_count,
            'total_count': task.total_count,
            'progress_percentage': round((task.sent_count + task.failed_count) / task.total_count * 100, 2) if task.total_count > 0 else 0,
            'error_message': task.error_message,
            'started_at': task.started_at.isoformat() if task.started_at else None,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None
        }
    
    def _process_queue(self):
        """Background worker that processes email tasks."""
        logger.info("Email queue worker started processing")
        
        while self.running:
            try:
                # Get task with timeout to allow checking running flag
                try:
                    task_id = self.task_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                task = self.tasks.get(task_id)
                if not task:
                    logger.warning(f"Task {task_id} not found in tasks dict")
                    continue
                
                # Process the task
                self._send_bulk_emails(task)
                
            except Exception as e:
                logger.error(f"Error in email queue worker: {str(e)}", exc_info=True)
        
        logger.info("Email queue worker stopped")
    
    def _send_bulk_emails(self, task: EmailTask):
        """Send emails for a task with delays between each email."""
        task.status = 'processing'
        task.started_at = datetime.now()
        logger.info(f"Starting task {task.task_id} with {task.total_count} emails, delay: {task.delay_seconds}s")
        
        server = None
        try:
            # Connect to SMTP server
            smtp_settings = task.smtp_settings
            if smtp_settings.get('use_ssl'):
                server = smtplib.SMTP_SSL(
                    smtp_settings['host'], 
                    smtp_settings['port'], 
                    timeout=30
                )
            else:
                server = smtplib.SMTP(
                    smtp_settings['host'], 
                    smtp_settings['port'], 
                    timeout=30
                )
                if smtp_settings.get('use_tls'):
                    server.starttls()
            
            if smtp_settings.get('username') and smtp_settings.get('password'):
                server.login(smtp_settings['username'], smtp_settings['password'])
            
            # Send emails with delay
            for i, recipient in enumerate(task.recipients):
                if not self.running:
                    logger.info(f"Task {task.task_id} cancelled")
                    task.status = 'failed'
                    task.error_message = 'Task cancelled'
                    break
                
                error_message = None
                try:
                    self._send_single_email(task, recipient, server)
                    task.sent_count += 1
                    
                    # Log successful send
                    task.audit_logs.append({
                        'template_id': task.template_id,
                        'template_name': task.template_name,
                        'recipient_email': recipient['email'],
                        'recipient_name': recipient['user_name'],
                        'team_id': recipient.get('team_db_id'),
                        'team_name': recipient['team_name'],
                        'status': 'sent',
                        'error_message': None
                    })
                    
                except Exception as e:
                    task.failed_count += 1
                    error_message = str(e)
                    logger.error(f"Failed to send email to {recipient['email']}: {error_message}")
                    
                    # Log failed send
                    task.audit_logs.append({
                        'template_id': task.template_id,
                        'template_name': task.template_name,
                        'recipient_email': recipient['email'],
                        'recipient_name': recipient['user_name'],
                        'team_id': recipient.get('team_db_id'),
                        'team_name': recipient['team_name'],
                        'status': 'failed',
                        'error_message': error_message
                    })
                
                # Apply delay between emails (except for the last one)
                if i < len(task.recipients) - 1 and task.delay_seconds > 0:
                    time.sleep(task.delay_seconds)
            
            task.status = 'completed'
            logger.info(f"Task {task.task_id} completed: {task.sent_count} sent, {task.failed_count} failed")
            
        except smtplib.SMTPAuthenticationError as e:
            task.status = 'failed'
            task.error_message = f'SMTP authentication failed: {str(e)}'
            logger.error(f"Task {task.task_id} failed: {task.error_message}")
        except smtplib.SMTPConnectError as e:
            task.status = 'failed'
            task.error_message = f'Failed to connect to SMTP server: {str(e)}'
            logger.error(f"Task {task.task_id} failed: {task.error_message}")
        except Exception as e:
            task.status = 'failed'
            task.error_message = f'{type(e).__name__}: {str(e)}'
            logger.error(f"Task {task.task_id} failed: {task.error_message}", exc_info=True)
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
            
            task.completed_at = datetime.now()
            
            # Save audit logs to database
            if task.audit_logs and self.supabase_client:
                try:
                    self.supabase_client.table('email_audit_logs').insert(task.audit_logs).execute()
                except Exception as log_error:
                    logger.warning(f"Failed to save audit logs for task {task.task_id}: {str(log_error)}")
    
    def _send_single_email(self, task: EmailTask, recipient: Dict, server):
        """Send a single email."""
        # Replace variables in template
        subject = task.template_data['subject']
        body = task.template_data['body']
        
        variables = {
            'user_name': recipient['user_name'],
            'user_email': recipient['user_email'],
            'user_ctfd_username': recipient['user_ctfd_username'],
            'user_ctfd_password': recipient['user_ctfd_password'],
            'team_name': recipient['team_name'],
            'registration_id': recipient.get('registration_id', ''),
            'team_ctfd_username': recipient['team_ctfd_username'],
            'team_ctfd_password': recipient['team_ctfd_password'],
            'event_name': task.smtp_settings.get('event_name', ''),
            'site_name': task.smtp_settings.get('site_name', ''),
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%H:%M')
        }
        
        for var_name, var_value in variables.items():
            subject = subject.replace('{{' + var_name + '}}', str(var_value or ''))
            body = body.replace('{{' + var_name + '}}', str(var_value or ''))
        
        # Create message
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = f"{task.smtp_settings['sender_name']} <{task.smtp_settings['sender_email']}>"
        msg['To'] = recipient['email']
        
        # Create alternative part for text and HTML
        msg_alternative = MIMEMultipart('alternative')
        
        # Create related part for HTML with inline images
        msg_related = MIMEMultipart('related')
        
        # Plain text version - strip HTML tags
        text_content = body.replace('<br>', '\n').replace('<p>', '\n').replace('</p>', '\n')
        text_content = re.sub('<[^<]+?>', '', text_content)
        
        msg_alternative.attach(MIMEText(text_content, 'plain'))
        
        # Process inline images
        inline_images = []
        img_pattern = r'src=["\'](?:/uploads/email_attachments/|\{\{cid:)([^"\']+)["\']'
        matches = re.findall(img_pattern, body)
        
        for i, match in enumerate(matches):
            filename = match.rstrip('}}')
            file_path = os.path.join(task.upload_folder, secure_filename(filename))
            
            if os.path.exists(file_path) and self._is_allowed_image(filename):
                cid = f'image{i}'
                body = re.sub(
                    r'src=["\'](?:/uploads/email_attachments/|\{\{cid:)' + re.escape(match) + r'["\']',
                    f'src="cid:{cid}"',
                    body
                )
                inline_images.append((file_path, cid, filename))
        
        # Attach HTML content
        msg_related.attach(MIMEText(body, 'html'))
        
        # Attach inline images
        for file_path, cid, filename in inline_images:
            with open(file_path, 'rb') as img_file:
                img_data = img_file.read()
                ext = filename.rsplit('.', 1)[1].lower()
                mime_subtype = 'jpeg' if ext == 'jpg' else ext
                img = MIMEImage(img_data, _subtype=mime_subtype)
                img.add_header('Content-ID', f'<{cid}>')
                img.add_header('Content-Disposition', 'inline', filename=filename)
                msg_related.attach(img)
        
        msg_alternative.attach(msg_related)
        msg.attach(msg_alternative)
        
        # Attach file attachments
        for attachment in task.attachments:
            file_path = os.path.join(task.upload_folder, attachment['stored_filename'])
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{attachment["original_filename"]}"'
                    )
                    msg.attach(part)
        
        # Send email
        server.sendmail(
            task.smtp_settings['sender_email'], 
            recipient['email'], 
            msg.as_string()
        )
    
    def _is_allowed_image(self, filename: str) -> bool:
        """Check if file is an allowed image type.
        
        Note: This duplicates allowed_image() from settings.py to keep
        EmailQueue independent of Flask context for background processing.
        """
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


# Global singleton instance
email_queue = EmailQueue()
