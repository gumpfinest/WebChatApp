"""
Two-Factor Authentication Module
Implements TOTP (Time-based One-Time Password) for 2FA
"""
import pyotp
import qrcode
import io
import base64
from datetime import datetime


class TwoFactorAuth:
    def __init__(self, app=None):
        self.app = app
        self.issuer_name = 'WebChatApp'
        self.digits = 6
        self.interval = 30  # seconds
        self.valid_window = 1  # Accept codes from 1 interval before/after
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
        self.issuer_name = app.config.get('TOTP_ISSUER_NAME', 'WebChatApp')
        self.digits = app.config.get('TOTP_DIGITS', 6)
        self.interval = app.config.get('TOTP_INTERVAL', 30)
        self.valid_window = app.config.get('TOTP_VALID_WINDOW', 1)
    
    def generate_secret(self):
        """Generate a new TOTP secret for a user"""
        return pyotp.random_base32()
    
    def get_totp(self, secret):
        """Create a TOTP instance from a secret"""
        return pyotp.TOTP(
            secret,
            digits=self.digits,
            interval=self.interval
        )
    
    def verify_code(self, secret, code):
        """Verify a TOTP code against a secret"""
        if not secret or not code:
            return False
        
        try:
            totp = self.get_totp(secret)
            # valid_window allows for clock drift
            return totp.verify(code, valid_window=self.valid_window)
        except Exception:
            return False
    
    def get_current_code(self, secret):
        """Get the current TOTP code (for testing/debugging)"""
        totp = self.get_totp(secret)
        return totp.now()
    
    def get_provisioning_uri(self, secret, username):
        """Get the provisioning URI for QR code generation"""
        totp = self.get_totp(secret)
        return totp.provisioning_uri(
            name=username,
            issuer_name=self.issuer_name
        )
    
    def generate_qr_code(self, secret, username, format='base64'):
        """
        Generate a QR code for setting up 2FA
        
        Args:
            secret: The TOTP secret
            username: The username for the account
            format: 'base64' returns data URL, 'bytes' returns raw image bytes
        
        Returns:
            QR code as base64 data URL or bytes
        """
        uri = self.get_provisioning_uri(secret, username)
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        if format == 'bytes':
            return buffer.getvalue()
        
        # Return as base64 data URL
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{img_base64}"
    
    def generate_backup_codes(self, count=10):
        """
        Generate backup codes for account recovery
        These should be stored hashed in the database
        
        Returns:
            List of backup codes
        """
        import secrets
        codes = []
        for _ in range(count):
            # Generate 8-character alphanumeric code
            code = secrets.token_hex(4).upper()
            # Format as XXXX-XXXX for readability
            codes.append(f"{code[:4]}-{code[4:]}")
        return codes
    
    def setup_2fa_response(self, secret, username):
        """
        Generate the complete 2FA setup response
        
        Returns:
            dict with secret, QR code, and provisioning URI
        """
        return {
            'secret': secret,
            'qr_code': self.generate_qr_code(secret, username),
            'provisioning_uri': self.get_provisioning_uri(secret, username),
            'backup_codes': self.generate_backup_codes()
        }


# Singleton instance
two_factor_auth = TwoFactorAuth()
