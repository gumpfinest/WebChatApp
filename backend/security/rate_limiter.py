"""
Rate Limiter Module
Provides configurable rate limiting for API endpoints
"""
from flask import request, jsonify
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict
import threading


class RateLimiter:
    def __init__(self, app=None):
        self.app = app
        self.storage = defaultdict(list)  # In-memory storage
        self.lock = threading.Lock()
        self.enabled = True
        
        # Default limits
        self.default_limits = {
            'login': {'requests': 5, 'window': 60},      # 5 per minute
            'register': {'requests': 3, 'window': 300},  # 3 per 5 minutes
            'message': {'requests': 30, 'window': 60},   # 30 per minute
            'default': {'requests': 100, 'window': 60},  # 100 per minute
        }
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
        self.enabled = app.config.get('RATE_LIMIT_ENABLED', True)
        
        # Allow custom limits from config
        custom_limits = app.config.get('RATE_LIMITS', {})
        self.default_limits.update(custom_limits)
    
    def _get_identifier(self):
        """Get unique identifier for the requester (IP address)"""
        # Support for proxies (X-Forwarded-For)
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        return request.remote_addr or '127.0.0.1'
    
    def _cleanup_old_requests(self, key, window_seconds):
        """Remove requests outside the time window"""
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        self.storage[key] = [ts for ts in self.storage[key] if ts > cutoff]
    
    def is_rate_limited(self, limit_type='default', identifier=None):
        """Check if the current request should be rate limited"""
        if not self.enabled:
            return False, None
        
        if identifier is None:
            identifier = self._get_identifier()
        
        limits = self.default_limits.get(limit_type, self.default_limits['default'])
        max_requests = limits['requests']
        window_seconds = limits['window']
        
        key = f"{limit_type}:{identifier}"
        
        with self.lock:
            self._cleanup_old_requests(key, window_seconds)
            
            if len(self.storage[key]) >= max_requests:
                # Calculate retry-after
                oldest = min(self.storage[key]) if self.storage[key] else datetime.utcnow()
                retry_after = int((oldest + timedelta(seconds=window_seconds) - datetime.utcnow()).total_seconds())
                return True, max(1, retry_after)
            
            # Record this request
            self.storage[key].append(datetime.utcnow())
            return False, None
    
    def get_remaining_requests(self, limit_type='default', identifier=None):
        """Get the number of remaining requests in the current window"""
        if identifier is None:
            identifier = self._get_identifier()
        
        limits = self.default_limits.get(limit_type, self.default_limits['default'])
        max_requests = limits['requests']
        window_seconds = limits['window']
        
        key = f"{limit_type}:{identifier}"
        
        with self.lock:
            self._cleanup_old_requests(key, window_seconds)
            return max(0, max_requests - len(self.storage[key]))
    
    def limit(self, limit_type='default'):
        """Decorator to apply rate limiting to a route"""
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                is_limited, retry_after = self.is_rate_limited(limit_type)
                
                if is_limited:
                    response = jsonify({
                        'error': 'Too many requests',
                        'message': f'Rate limit exceeded. Please try again in {retry_after} seconds.',
                        'retry_after': retry_after
                    })
                    response.status_code = 429
                    response.headers['Retry-After'] = str(retry_after)
                    return response
                
                # Add rate limit headers to response
                result = f(*args, **kwargs)
                
                # If result is a tuple (response, status_code), handle it
                if isinstance(result, tuple):
                    response = result[0]
                    if hasattr(response, 'headers'):
                        remaining = self.get_remaining_requests(limit_type)
                        limits = self.default_limits.get(limit_type, self.default_limits['default'])
                        response.headers['X-RateLimit-Limit'] = str(limits['requests'])
                        response.headers['X-RateLimit-Remaining'] = str(remaining)
                        response.headers['X-RateLimit-Window'] = str(limits['window'])
                    return result
                
                # If result is just a response object
                if hasattr(result, 'headers'):
                    remaining = self.get_remaining_requests(limit_type)
                    limits = self.default_limits.get(limit_type, self.default_limits['default'])
                    result.headers['X-RateLimit-Limit'] = str(limits['requests'])
                    result.headers['X-RateLimit-Remaining'] = str(remaining)
                    result.headers['X-RateLimit-Window'] = str(limits['window'])
                
                return result
            return decorated_function
        return decorator
    
    def reset(self, identifier=None, limit_type=None):
        """Reset rate limits for an identifier"""
        if identifier is None:
            identifier = self._get_identifier()
        
        with self.lock:
            if limit_type:
                key = f"{limit_type}:{identifier}"
                self.storage.pop(key, None)
            else:
                # Reset all limits for this identifier
                keys_to_remove = [k for k in self.storage.keys() if k.endswith(f":{identifier}")]
                for key in keys_to_remove:
                    self.storage.pop(key, None)
    
    def clear_all(self):
        """Clear all rate limit data"""
        with self.lock:
            self.storage.clear()


# Singleton instance
rate_limiter = RateLimiter()
