"""
Message Encryption Module
Provides end-to-end encryption for chat messages using AES-256-GCM
"""
import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend


class MessageEncryption:
    def __init__(self, app=None):
        self.app = app
        self.master_key = None
        self.key_length = 32  # 256 bits
        self.nonce_length = 12  # 96 bits for GCM
        self.tag_length = 16  # 128 bits
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
        
        # Get or generate master key
        master_key_hex = app.config.get('ENCRYPTION_MASTER_KEY')
        if master_key_hex:
            self.master_key = bytes.fromhex(master_key_hex)
        else:
            # Generate a new master key (should be stored securely in production)
            self.master_key = os.urandom(self.key_length)
            app.config['ENCRYPTION_MASTER_KEY'] = self.master_key.hex()
            print("WARNING: Generated new encryption master key. Store ENCRYPTION_MASTER_KEY in environment for persistence.")
    
    def _derive_room_key(self, room_name):
        """
        Derive a unique encryption key for each room
        This allows room-specific encryption while using a single master key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.key_length,
            salt=room_name.encode('utf-8'),
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(self.master_key)
    
    def _derive_user_key(self, user_id, username):
        """
        Derive a unique encryption key for a user
        Used for private messages or user-specific encryption
        """
        user_salt = f"{user_id}:{username}".encode('utf-8')
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.key_length,
            salt=user_salt,
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(self.master_key)
    
    def encrypt_message(self, plaintext, room_name):
        """
        Encrypt a message for a specific room
        
        Args:
            plaintext: The message content to encrypt
            room_name: The room the message belongs to
            
        Returns:
            dict with encrypted data and nonce (both base64 encoded)
        """
        if not plaintext:
            return None
        
        # Derive room-specific key
        key = self._derive_room_key(room_name)
        
        # Generate random nonce
        nonce = os.urandom(self.nonce_length)
        
        # Encrypt using AES-256-GCM
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(
            nonce,
            plaintext.encode('utf-8'),
            room_name.encode('utf-8')  # Additional authenticated data
        )
        
        # Return base64 encoded values
        return {
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'encrypted': True
        }
    
    def decrypt_message(self, encrypted_data, room_name):
        """
        Decrypt a message for a specific room
        
        Args:
            encrypted_data: dict with 'ciphertext' and 'nonce' (base64 encoded)
            room_name: The room the message belongs to
            
        Returns:
            Decrypted plaintext string
        """
        if not encrypted_data or not encrypted_data.get('encrypted'):
            return encrypted_data.get('ciphertext') if encrypted_data else None
        
        try:
            # Derive room-specific key
            key = self._derive_room_key(room_name)
            
            # Decode base64 values
            ciphertext = base64.b64decode(encrypted_data['ciphertext'])
            nonce = base64.b64decode(encrypted_data['nonce'])
            
            # Decrypt using AES-256-GCM
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(
                nonce,
                ciphertext,
                room_name.encode('utf-8')  # Additional authenticated data
            )
            
            return plaintext.decode('utf-8')
        
        except Exception as e:
            # Return None if decryption fails (message may have been tampered with)
            return None
    
    def encrypt_for_storage(self, content, room_name):
        """
        Encrypt content and return a single string for database storage
        Format: nonce:ciphertext (both base64 encoded)
        """
        if not content:
            return None
        
        encrypted = self.encrypt_message(content, room_name)
        return f"{encrypted['nonce']}:{encrypted['ciphertext']}"
    
    def decrypt_from_storage(self, stored_content, room_name):
        """
        Decrypt content stored in the format: nonce:ciphertext
        """
        if not stored_content or ':' not in stored_content:
            return stored_content  # Return as-is if not encrypted format
        
        try:
            nonce, ciphertext = stored_content.split(':', 1)
            encrypted_data = {
                'nonce': nonce,
                'ciphertext': ciphertext,
                'encrypted': True
            }
            return self.decrypt_message(encrypted_data, room_name)
        except Exception:
            return stored_content  # Return as-is if decryption fails
    
    def hash_for_search(self, content):
        """
        Create a searchable hash of content
        Note: This is a one-way hash, used for exact match searching
        """
        return hashlib.sha256(content.lower().encode('utf-8')).hexdigest()
    
    def generate_key_for_export(self, password, salt=None):
        """
        Generate an encryption key from a password for key export/import
        Useful for backing up encryption keys
        """
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.key_length,
            salt=salt,
            iterations=480000,  # Higher iterations for password-derived keys
            backend=default_backend()
        )
        key = kdf.derive(password.encode('utf-8'))
        
        return {
            'key': base64.b64encode(key).decode('utf-8'),
            'salt': base64.b64encode(salt).decode('utf-8')
        }


# Singleton instance
message_encryption = MessageEncryption()
