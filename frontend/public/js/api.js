// API Service - Handles all HTTP requests to the backend
// Supports JWT authentication with automatic token refresh
import CONFIG from './config.js';

class ApiService {
    constructor() {
        this.baseUrl = CONFIG.BACKEND_URL;
        this.refreshPromise = null; // Prevent multiple simultaneous refresh calls
    }

    getToken() {
        return localStorage.getItem(CONFIG.TOKEN_KEY);
    }

    getRefreshToken() {
        return localStorage.getItem(CONFIG.REFRESH_TOKEN_KEY);
    }

    setTokens(accessToken, refreshToken, expiresIn) {
        localStorage.setItem(CONFIG.TOKEN_KEY, accessToken);
        if (refreshToken) {
            localStorage.setItem(CONFIG.REFRESH_TOKEN_KEY, refreshToken);
        }
        if (expiresIn) {
            const expiry = Date.now() + (expiresIn * 1000);
            localStorage.setItem(CONFIG.TOKEN_EXPIRY_KEY, expiry.toString());
        }
    }

    clearTokens() {
        localStorage.removeItem(CONFIG.TOKEN_KEY);
        localStorage.removeItem(CONFIG.REFRESH_TOKEN_KEY);
        localStorage.removeItem(CONFIG.TOKEN_EXPIRY_KEY);
    }

    isTokenExpiringSoon() {
        const expiry = localStorage.getItem(CONFIG.TOKEN_EXPIRY_KEY);
        if (!expiry) return true; // No expiry stored - assume needs refresh
        // Refresh if less than 2 minutes remaining OR already expired
        return Date.now() > (parseInt(expiry) - 120000);
    }

    isTokenExpired() {
        const expiry = localStorage.getItem(CONFIG.TOKEN_EXPIRY_KEY);
        if (!expiry) return true; // No expiry stored - assume expired
        return Date.now() > parseInt(expiry);
    }

    getHeaders(includeAuth = true) {
        const headers = { 'Content-Type': 'application/json' };
        if (includeAuth) {
            const token = this.getToken();
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
        }
        return headers;
    }

    async refreshAccessToken() {
        // If already refreshing, wait for that promise
        if (this.refreshPromise) {
            return this.refreshPromise;
        }

        const refreshToken = this.getRefreshToken();
        if (!refreshToken) {
            throw new Error('No refresh token available');
        }

        this.refreshPromise = fetch(`${this.baseUrl}/api/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken })
        })
        .then(async response => {
            const data = await response.json();
            if (!response.ok) {
                this.clearTokens();
                throw new Error(data.error || 'Token refresh failed');
            }
            this.setTokens(data.access_token, null, data.expires_in);
            return data;
        })
        .finally(() => {
            this.refreshPromise = null;
        });

        return this.refreshPromise;
    }

    async fetchWithAuth(url, options = {}) {
        // Check if token needs refresh before making request
        if (this.isTokenExpiringSoon() && this.getRefreshToken()) {
            try {
                await this.refreshAccessToken();
            } catch (e) {
                console.warn('Token refresh failed:', e);
            }
        }

        // Add auth header
        options.headers = {
            ...options.headers,
            ...this.getHeaders(true)
        };

        let response = await fetch(url, options);

        // If unauthorized, try to refresh token once
        if (response.status === 401 && this.getRefreshToken()) {
            try {
                await this.refreshAccessToken();
                options.headers = {
                    ...options.headers,
                    ...this.getHeaders(true)
                };
                response = await fetch(url, options);
            } catch (e) {
                // Refresh failed, let the 401 propagate
            }
        }

        return response;
    }

    // Auth endpoints
    async login(username, password) {
        const body = { username, password };
        
        const response = await fetch(`${this.baseUrl}/api/login`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify(body)
        });
        const data = await response.json();
        
        // Check if 2FA is required (special case - not an error)
        if (data.requires_2fa) {
            return {
                requires_2fa: true,
                email_hint: data.email_hint
            };
        }
        
        if (!response.ok) {
            const error = new Error(data.error || 'Login failed');
            throw error;
        }
        
        // Store JWT tokens
        if (data.access_token) {
            this.setTokens(data.access_token, data.refresh_token, data.expires_in);
        } else if (data.token) {
            // Legacy token support
            localStorage.setItem(CONFIG.TOKEN_KEY, data.token);
        }
        
        return data;
    }

    // Login with Email 2FA code
    async login2FA(username, password, email2FACode) {
        const body = { username, password, email_2fa_code: email2FACode };
        
        const response = await fetch(`${this.baseUrl}/api/login`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify(body)
        });
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Login failed');
        }
        
        // Store JWT tokens
        if (data.access_token) {
            this.setTokens(data.access_token, data.refresh_token, data.expires_in);
        }
        
        return data;
    }

    async register(username, password) {
        const response = await fetch(`${this.baseUrl}/api/register`, {
            method: 'POST',
            headers: this.getHeaders(false),
            body: JSON.stringify({ username, password })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Registration failed');
        
        // Store JWT tokens
        if (data.access_token) {
            this.setTokens(data.access_token, data.refresh_token, data.expires_in);
        } else if (data.token) {
            localStorage.setItem(CONFIG.TOKEN_KEY, data.token);
        }
        
        return data;
    }

    async verifyToken() {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/verify`);
        if (!response.ok) return null;
        return await response.json();
    }

    // Email 2FA endpoints
    async setup2FA(email) {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/account/2fa/setup`, {
            method: 'POST',
            body: JSON.stringify({ email })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to setup 2FA');
        return data;
    }

    async verify2FA(code) {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/account/2fa/verify`, {
            method: 'POST',
            body: JSON.stringify({ code })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to verify 2FA');
        return data;
    }

    async resend2FACode() {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/account/2fa/resend`, {
            method: 'POST'
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to resend code');
        return data;
    }

    async disable2FA(password) {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/account/2fa/disable`, {
            method: 'POST',
            body: JSON.stringify({ password })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to disable 2FA');
        return data;
    }

    // Messages endpoints
    async getMessages(room) {
        const response = await fetch(`${this.baseUrl}/api/messages?room=${room}`);
        return await response.json();
    }

    async deleteMessage(messageId) {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/messages/${messageId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to delete message');
        return data;
    }

    // Rooms endpoints
    async getRooms() {
        const response = await fetch(`${this.baseUrl}/api/rooms`);
        return await response.json();
    }

    async createRoom(name) {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/rooms`, {
            method: 'POST',
            body: JSON.stringify({ name })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to create room');
        return data;
    }

    async deleteRoom(name) {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/rooms/${name}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to delete room');
        return data;
    }

    // Account endpoints
    async deleteAccount() {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/account`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to delete account');
        return data;
    }

    async changePassword(currentPassword, newPassword) {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/account/password`, {
            method: 'PUT',
            body: JSON.stringify({ currentPassword, newPassword })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to change password');
        return data;
    }

    async getProfile() {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/account/profile`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to get profile');
        return data;
    }

    async updateProfile(avatarColor, nameColor, displayName) {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/account/profile`, {
            method: 'PUT',
            body: JSON.stringify({ avatarColor, nameColor, displayName })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to update profile');
        return data;
    }

    async uploadAvatar(imageData) {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/account/avatar`, {
            method: 'POST',
            body: JSON.stringify({ image: imageData })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to upload avatar');
        return data;
    }

    async deleteAvatar() {
        const response = await this.fetchWithAuth(`${this.baseUrl}/api/account/avatar`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to delete avatar');
        return data;
    }

    getAvatarUrl(avatarPath) {
        if (!avatarPath) return null;
        return `${this.baseUrl}${avatarPath}`;
    }

    async healthCheck() {
        const response = await fetch(`${this.baseUrl}/api/health`);
        return await response.json();
    }
}

export default new ApiService();

