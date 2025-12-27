// Application Configuration
const CONFIG = {
    // In production with Cloudflare Tunnel, backend is proxied on the same domain
    // Use empty string for same-origin requests, or set BACKEND_URL environment variable
    BACKEND_URL: window.BACKEND_URL || '',
    TOKEN_KEY: 'chatToken',
    REFRESH_TOKEN_KEY: 'chatRefreshToken',
    USER_KEY: 'chatUser',
    TOKEN_EXPIRY_KEY: 'chatTokenExpiry'
};

export default CONFIG;
