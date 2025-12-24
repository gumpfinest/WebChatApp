// Authentication Module
// Supports JWT tokens with refresh, 2FA, and legacy token format
import CONFIG from './config.js';
import api from './api.js';

class AuthManager {
    constructor() {
        this.currentUser = null;
        this.authToken = null;
        this.onAuthChange = null; // Callback when auth state changes
        this.pending2FA = null; // Store credentials during 2FA flow
    }

    saveAuth(accessToken, user, refreshToken = null) {
        localStorage.setItem(CONFIG.TOKEN_KEY, accessToken);
        localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(user));
        if (refreshToken) {
            localStorage.setItem(CONFIG.REFRESH_TOKEN_KEY, refreshToken);
        }
        this.authToken = accessToken;
        this.currentUser = user;
    }

    loadAuth() {
        const token = localStorage.getItem(CONFIG.TOKEN_KEY);
        const user = localStorage.getItem(CONFIG.USER_KEY);
        
        if (token && user) {
            this.authToken = token;
            this.currentUser = JSON.parse(user);
            return { token, user: this.currentUser };
        }
        return null;
    }

    clearAuth() {
        localStorage.removeItem(CONFIG.TOKEN_KEY);
        localStorage.removeItem(CONFIG.USER_KEY);
        localStorage.removeItem(CONFIG.REFRESH_TOKEN_KEY);
        localStorage.removeItem(CONFIG.TOKEN_EXPIRY_KEY);
        api.clearTokens();
        this.authToken = null;
        this.currentUser = null;
        this.pending2FA = null;
    }

    async login(username, password) {
        const data = await api.login(username, password);
        
        // Check if Email 2FA is required
        if (data.requires_2fa) {
            // Store credentials for 2FA completion
            this.pending2FA = { username, password, emailHint: data.email_hint };
            return {
                requires2FA: true,
                emailHint: data.email_hint
            };
        }
        
        // Handle JWT tokens
        const token = data.access_token || data.token;
        this.saveAuth(token, data.user, data.refresh_token);
        this.pending2FA = null;
        
        return data;
    }

    async login2FA(email2FACode) {
        // Use stored credentials with the email 2FA code
        if (!this.pending2FA) {
            throw new Error('No pending 2FA login');
        }
        
        const data = await api.login2FA(
            this.pending2FA.username, 
            this.pending2FA.password, 
            email2FACode
        );
        
        const token = data.access_token || data.token;
        this.saveAuth(token, data.user, data.refresh_token);
        this.pending2FA = null;
        
        return data;
    }

    getEmailHint() {
        return this.pending2FA?.emailHint || null;
    }

    hasPending2FA() {
        return this.pending2FA !== null;
    }

    cancelPending2FA() {
        this.pending2FA = null;
    }

    async register(username, password) {
        const data = await api.register(username, password);
        const token = data.access_token || data.token;
        this.saveAuth(token, data.user, data.refresh_token);
        return data;
    }

    async verifySession() {
        const auth = this.loadAuth();
        if (!auth) return false;

        try {
            // First, try to refresh the token if it's expiring soon
            if (api.isTokenExpiringSoon() && api.getRefreshToken()) {
                try {
                    await api.refreshAccessToken();
                    console.log('Token refreshed during session verification');
                } catch (e) {
                    console.warn('Proactive token refresh failed:', e);
                }
            }

            const verification = await api.verifyToken();
            if (verification && verification.valid) {
                // Update user data with latest from server
                this.currentUser = verification.user;
                localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(verification.user));
                return true;
            }
        } catch (error) {
            console.warn('Session verification failed:', error);
            
            // Try to refresh token before giving up
            if (api.getRefreshToken()) {
                try {
                    await api.refreshAccessToken();
                    // Retry verification with new token
                    const verification = await api.verifyToken();
                    if (verification && verification.valid) {
                        this.currentUser = verification.user;
                        localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(verification.user));
                        return true;
                    }
                } catch (refreshError) {
                    console.warn('Token refresh also failed:', refreshError);
                }
            }
        }

        this.clearAuth();
        return false;
    }

    // 2FA Management
    async setup2FA(email) {
        return await api.setup2FA(email);
    }

    async verify2FASetup(code) {
        const result = await api.verify2FA(code);
        // Update user's 2FA status
        if (this.currentUser) {
            this.currentUser.email2FAEnabled = true;
            localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(this.currentUser));
        }
        return result;
    }

    async disable2FA(password) {
        const result = await api.disable2FA(password);
        // Update user's 2FA status
        if (this.currentUser) {
            this.currentUser.email2FAEnabled = false;
            localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(this.currentUser));
        }
        return result;
    }

    is2FAEnabled() {
        return this.currentUser?.email2FAEnabled || false;
    }

    async deleteAccount() {
        await api.deleteAccount();
        this.clearAuth();
    }

    async changePassword(currentPassword, newPassword) {
        return await api.changePassword(currentPassword, newPassword);
    }

    async updateProfile(avatarColor, nameColor, displayName) {
        const result = await api.updateProfile(avatarColor, nameColor, displayName);
        // Update local user data
        this.currentUser.avatarColor = avatarColor;
        this.currentUser.nameColor = nameColor;
        this.currentUser.displayName = displayName;
        localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(this.currentUser));
        return result;
    }

    async uploadAvatar(imageData) {
        const result = await api.uploadAvatar(imageData);
        // Update local user data
        this.currentUser.avatarUrl = result.avatarUrl;
        localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(this.currentUser));
        return result;
    }

    async deleteAvatar() {
        const result = await api.deleteAvatar();
        // Update local user data
        this.currentUser.avatarUrl = null;
        localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(this.currentUser));
        return result;
    }

    isAuthenticated() {
        return this.authToken !== null && this.currentUser !== null;
    }

    getUser() {
        return this.currentUser;
    }

    setUser(user) {
        this.currentUser = user;
        localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(user));
    }

    getToken() {
        return this.authToken;
    }
}

export default new AuthManager();

