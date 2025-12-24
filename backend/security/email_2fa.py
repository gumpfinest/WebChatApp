"""
Email-Based Two-Factor Authentication Module
Sends verification codes via email for 2FA
"""
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import os


class Email2FA:
    def __init__(self, app=None):
        self.app = app
        self.code_length = 6
        self.code_expiry_minutes = 10
        
        # Email configuration - set these via environment variables
        self.smtp_server = None
        self.smtp_port = 587
        self.smtp_username = None
        self.smtp_password = None
        self.from_email = None
        self.from_name = 'WebChatApp'
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
        self.code_length = app.config.get('EMAIL_2FA_CODE_LENGTH', 6)
        self.code_expiry_minutes = app.config.get('EMAIL_2FA_EXPIRY_MINUTES', 10)
        
        # Email settings from config or environment
        self.smtp_server = app.config.get('SMTP_SERVER') or os.environ.get('SMTP_SERVER')
        self.smtp_port = int(app.config.get('SMTP_PORT') or os.environ.get('SMTP_PORT', 587))
        self.smtp_username = app.config.get('SMTP_USERNAME') or os.environ.get('SMTP_USERNAME')
        self.smtp_password = app.config.get('SMTP_PASSWORD') or os.environ.get('SMTP_PASSWORD')
        self.from_email = app.config.get('SMTP_FROM_EMAIL') or os.environ.get('SMTP_FROM_EMAIL')
        self.from_name = app.config.get('SMTP_FROM_NAME') or os.environ.get('SMTP_FROM_NAME', 'WebChatApp')
    
    def generate_code(self):
        """Generate a random numeric verification code"""
        # Generate a secure random number with the specified number of digits
        code = ''.join([str(secrets.randbelow(10)) for _ in range(self.code_length)])
        return code
    
    def get_expiry_time(self):
        """Get the expiry datetime for a new code"""
        return datetime.utcnow() + timedelta(minutes=self.code_expiry_minutes)
    
    def is_code_expired(self, expiry_time):
        """Check if a code has expired"""
        if isinstance(expiry_time, str):
            expiry_time = datetime.fromisoformat(expiry_time)
        return datetime.utcnow() > expiry_time
    
    def verify_code(self, stored_code, provided_code, expiry_time):
        """
        Verify a provided code against the stored code
        
        Args:
            stored_code: The code stored in the database
            provided_code: The code provided by the user
            expiry_time: When the code expires
        
        Returns:
            bool: True if valid, False otherwise
        """
        if not stored_code or not provided_code:
            return False
        
        if self.is_code_expired(expiry_time):
            return False
        
        # Constant-time comparison to prevent timing attacks
        return secrets.compare_digest(str(stored_code), str(provided_code))
    
    def send_code(self, email, code, username=None):
        """
        Send a verification code via email
        
        Args:
            email: Recipient email address
            code: The verification code
            username: Optional username for personalization
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.smtp_server:
            print(f"[EMAIL 2FA] SMTP not configured. Code for {email}: {code}")
            return True  # Return True for development without email
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'Your {self.from_name} Verification Code'
            msg['From'] = f'{self.from_name} <{self.from_email}>'
            msg['To'] = email
            
            greeting = f"Hi {username}," if username else "Hi,"
            
            # Plain text version
            text_content = f"""{greeting}

Your verification code is: {code}

This code will expire in {self.code_expiry_minutes} minutes.

If you didn't request this code, please ignore this email or contact support if you have concerns.

- The {self.from_name} Team
"""
            
            # HTML version
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .code-box {{ 
            background: #f5f5f5; 
            border: 2px dashed #7289da; 
            border-radius: 8px; 
            padding: 20px; 
            text-align: center; 
            margin: 20px 0;
        }}
        .code {{ 
            font-size: 32px; 
            font-weight: bold; 
            letter-spacing: 8px; 
            color: #7289da; 
            font-family: 'Courier New', monospace;
        }}
        .expiry {{ color: #666; font-size: 14px; margin-top: 10px; }}
        .footer {{ color: #999; font-size: 12px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>Verification Code</h2>
        <p>{greeting}</p>
        <p>You requested a verification code to sign in to your {self.from_name} account.</p>
        
        <div class="code-box">
            <div class="code">{code}</div>
            <div class="expiry">This code expires in {self.code_expiry_minutes} minutes</div>
        </div>
        
        <p>If you didn't request this code, please ignore this email or contact support if you have concerns.</p>
        
        <div class="footer">
            <p>This is an automated message from {self.from_name}. Please do not reply to this email.</p>
        </div>
    </div>
</body>
</html>
"""
            
            msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            print(f"[EMAIL 2FA] Failed to send email: {e}")
            # In development, print the code so testing is possible
            print(f"[EMAIL 2FA] Code for {email}: {code}")
            return False
    
    def generate_backup_codes(self, count=8):
        """
        Generate backup codes for account recovery
        
        Args:
            count: Number of backup codes to generate
        
        Returns:
            list: List of backup codes
        """
        codes = []
        for _ in range(count):
            # Generate 8-character alphanumeric codes
            code = secrets.token_hex(4).upper()
            codes.append(code)
        return codes


# Create a singleton instance
email_2fa = Email2FA()
