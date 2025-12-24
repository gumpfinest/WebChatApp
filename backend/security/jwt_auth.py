"""
JWT Authentication Module
Handles token generation, validation, and refresh token management
"""
import jwt
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify


class JWTAuth:
    def __init__(self, app=None):
        self.app = app
        self.secret_key = None
        self.refresh_secret_key = None
        self.access_token_expires = timedelta(minutes=15)
        self.refresh_token_expires = timedelta(days=30)
        self.algorithm = 'HS256'
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
        self.secret_key = app.config.get('JWT_SECRET_KEY', os.urandom(32).hex())
        self.refresh_secret_key = app.config.get('JWT_REFRESH_SECRET_KEY', os.urandom(32).hex())
        
        # Store keys in app config for persistence
        app.config['JWT_SECRET_KEY'] = self.secret_key
        app.config['JWT_REFRESH_SECRET_KEY'] = self.refresh_secret_key
        
        # Configurable expiration times
        self.access_token_expires = app.config.get('JWT_ACCESS_TOKEN_EXPIRES', timedelta(minutes=15))
        self.refresh_token_expires = app.config.get('JWT_REFRESH_TOKEN_EXPIRES', timedelta(days=30))
    
    def generate_access_token(self, user_id, username, additional_claims=None):
        """Generate a short-lived access token"""
        payload = {
            'user_id': user_id,
            'username': username,
            'type': 'access',
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + self.access_token_expires
        }
        
        if additional_claims:
            payload.update(additional_claims)
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def generate_refresh_token(self, user_id, username):
        """Generate a long-lived refresh token"""
        payload = {
            'user_id': user_id,
            'username': username,
            'type': 'refresh',
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + self.refresh_token_expires
        }
        
        return jwt.encode(payload, self.refresh_secret_key, algorithm=self.algorithm)
    
    def generate_tokens(self, user_id, username, additional_claims=None):
        """Generate both access and refresh tokens"""
        return {
            'access_token': self.generate_access_token(user_id, username, additional_claims),
            'refresh_token': self.generate_refresh_token(user_id, username),
            'token_type': 'Bearer',
            'expires_in': int(self.access_token_expires.total_seconds())
        }
    
    def verify_access_token(self, token):
        """Verify and decode an access token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get('type') != 'access':
                return None, 'Invalid token type'
            return payload, None
        except jwt.ExpiredSignatureError:
            return None, 'Token has expired'
        except jwt.InvalidTokenError as e:
            return None, f'Invalid token: {str(e)}'
    
    def verify_refresh_token(self, token):
        """Verify and decode a refresh token"""
        try:
            payload = jwt.decode(token, self.refresh_secret_key, algorithms=[self.algorithm])
            if payload.get('type') != 'refresh':
                return None, 'Invalid token type'
            return payload, None
        except jwt.ExpiredSignatureError:
            return None, 'Refresh token has expired'
        except jwt.InvalidTokenError as e:
            return None, f'Invalid refresh token: {str(e)}'
    
    def refresh_access_token(self, refresh_token, additional_claims=None):
        """Generate a new access token using a refresh token"""
        payload, error = self.verify_refresh_token(refresh_token)
        if error:
            return None, error
        
        new_access_token = self.generate_access_token(
            payload['user_id'], 
            payload['username'],
            additional_claims
        )
        return {
            'access_token': new_access_token,
            'token_type': 'Bearer',
            'expires_in': int(self.access_token_expires.total_seconds())
        }, None
    
    def login_required(self, f):
        """Decorator to protect routes with JWT authentication"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            
            if not auth_header:
                return jsonify({'error': 'No authorization header'}), 401
            
            try:
                # Expect "Bearer <token>"
                parts = auth_header.split()
                if len(parts) != 2 or parts[0].lower() != 'bearer':
                    return jsonify({'error': 'Invalid authorization header format'}), 401
                
                token = parts[1]
                payload, error = self.verify_access_token(token)
                
                if error:
                    return jsonify({'error': error}), 401
                
                # Attach user info to request
                request.user_id = payload['user_id']
                request.username = payload['username']
                request.token_payload = payload
                
            except Exception as e:
                return jsonify({'error': f'Authentication failed: {str(e)}'}), 401
            
            return f(*args, **kwargs)
        return decorated_function
    
    def optional_auth(self, f):
        """Decorator that allows but doesn't require authentication"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            request.user_id = None
            request.username = None
            request.token_payload = None
            
            if auth_header:
                try:
                    parts = auth_header.split()
                    if len(parts) == 2 and parts[0].lower() == 'bearer':
                        token = parts[1]
                        payload, _ = self.verify_access_token(token)
                        if payload:
                            request.user_id = payload['user_id']
                            request.username = payload['username']
                            request.token_payload = payload
                except:
                    pass
            
            return f(*args, **kwargs)
        return decorated_function


# Singleton instance
jwt_auth = JWTAuth()
