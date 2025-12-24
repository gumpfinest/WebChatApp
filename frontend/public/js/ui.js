// UI Manager - Handles DOM manipulation
import CONFIG from './config.js';
import auth from './auth.js';
import chat from './chat.js';
import rooms from './rooms.js';

class UIManager {
    constructor() {
        this.elements = {};
        this.typingTimeout = null;
    }

    init() {
        // Cache DOM elements
        this.elements = {
            // Screens
            loadingScreen: document.getElementById('loading-screen'),
            authScreen: document.getElementById('auth-screen'),
            chatScreen: document.getElementById('chat-screen'),
            
            // Auth forms
            loginForm: document.getElementById('login-form'),
            registerForm: document.getElementById('register-form'),
            loginUsername: document.getElementById('login-username'),
            loginPassword: document.getElementById('login-password'),
            loginBtn: document.getElementById('login-btn'),
            loginError: document.getElementById('login-error'),
            registerUsername: document.getElementById('register-username'),
            registerPassword: document.getElementById('register-password'),
            registerConfirm: document.getElementById('register-confirm'),
            registerBtn: document.getElementById('register-btn'),
            registerError: document.getElementById('register-error'),
            showRegisterLink: document.getElementById('show-register'),
            showLoginLink: document.getElementById('show-login'),
            
            // Chat
            currentUserSpan: document.getElementById('current-user'),
            currentRoomHeader: document.getElementById('current-room'),
            messagesContainer: document.getElementById('messages-container'),
            messageInput: document.getElementById('message-input'),
            sendBtn: document.getElementById('send-btn'),
            typingIndicator: document.getElementById('typing-indicator'),
            roomsList: document.getElementById('rooms-list'),
            logoutBtn: document.getElementById('logout-btn'),
            settingsBtn: document.getElementById('settings-btn'),
            openCreateRoomBtn: document.getElementById('open-create-room-btn'),
            
            // Modals
            settingsModal: document.getElementById('settings-modal'),
            createRoomModal: document.getElementById('create-room-modal'),
            confirmModal: document.getElementById('confirm-modal')
        };
    }

    // Screen management
    showAuthScreen() {
        this.elements.loadingScreen.classList.add('hidden');
        this.elements.authScreen.classList.remove('hidden');
        this.elements.chatScreen.classList.add('hidden');
    }

    showChatScreen() {
        this.elements.loadingScreen.classList.add('hidden');
        this.elements.authScreen.classList.add('hidden');
        this.elements.chatScreen.classList.remove('hidden');
    }

    showLoginForm() {
        this.elements.loginForm.classList.remove('hidden');
        this.elements.registerForm.classList.add('hidden');
    }

    showRegisterForm() {
        this.elements.loginForm.classList.add('hidden');
        this.elements.registerForm.classList.remove('hidden');
    }

    // Error display
    showError(elementId, message) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = message;
            element.classList.add('visible');
            setTimeout(() => {
                element.classList.remove('visible');
            }, 5000);
        }
    }

    // User info
    setCurrentUser(username, avatarColor = null, nameColor = null, avatarUrl = null, displayName = null) {
        const name = displayName || username;
        this.elements.currentUserSpan.textContent = name;
        
        // Set user avatar in sidebar
        const userAvatar = document.getElementById('user-avatar');
        if (userAvatar) {
            const fullAvatarUrl = this.getAvatarUrl(avatarUrl);
            if (fullAvatarUrl) {
                userAvatar.innerHTML = `<img src="${fullAvatarUrl}" alt="${name}" class="sidebar-avatar-image">`;
                userAvatar.style.backgroundColor = 'transparent';
            } else {
                userAvatar.innerHTML = '';
                userAvatar.textContent = this.getInitials(name);
                userAvatar.style.backgroundColor = this.getUserColor(username, avatarColor);
            }
        }
        
        // Apply name color to username in sidebar
        if (nameColor) {
            this.elements.currentUserSpan.style.color = nameColor;
        }
    }

    // Update sidebar avatar and colors
    updateUserAppearance(username, avatarColor, nameColor, avatarUrl = null, displayName = null) {
        const name = displayName || username;
        const userAvatar = document.getElementById('user-avatar');
        
        if (userAvatar) {
            const fullAvatarUrl = this.getAvatarUrl(avatarUrl);
            if (fullAvatarUrl) {
                userAvatar.innerHTML = `<img src="${fullAvatarUrl}" alt="${name}" class="sidebar-avatar-image">`;
                userAvatar.style.backgroundColor = 'transparent';
            } else {
                userAvatar.innerHTML = '';
                userAvatar.textContent = this.getInitials(name);
                userAvatar.style.backgroundColor = this.getUserColor(username, avatarColor);
            }
        }
        
        // Update display name
        this.elements.currentUserSpan.textContent = name;
        
        if (nameColor) {
            this.elements.currentUserSpan.style.color = nameColor;
        } else {
            this.elements.currentUserSpan.style.color = '#dcddde'; // Reset to default
        }
    }

    // Messages
    renderMessages(messages) {
        this.elements.messagesContainer.innerHTML = '';
        messages.forEach(msg => this.addMessage(msg));
    }

    // Generate a consistent color based on username (fallback when no custom color)
    getDefaultColor(username) {
        const colors = [
            '#5865F2', '#57F287', '#FEE75C', '#EB459E', '#ED4245',
            '#9B59B6', '#3498DB', '#1ABC9C', '#E67E22', '#E74C3C'
        ];
        let hash = 0;
        for (let i = 0; i < username.length; i++) {
            hash = username.charCodeAt(i) + ((hash << 5) - hash);
        }
        return colors[Math.abs(hash) % colors.length];
    }

    // Get avatar color (custom or default)
    getUserColor(username, customColor = null) {
        return customColor || this.getDefaultColor(username);
    }

    // Get name color (custom or default)
    getNameColor(customColor = null) {
        return customColor || '#7289da'; // Default Discord-like blue
    }

    // Get initials from username
    getInitials(username) {
        return username.charAt(0).toUpperCase();
    }

    // Get initials from username or display name
    getInitials(name) {
        return name.charAt(0).toUpperCase();
    }

    // Get full avatar URL
    getAvatarUrl(avatarPath) {
        if (!avatarPath) return null;
        return `${CONFIG.BACKEND_URL}${avatarPath}`;
    }

    // Format timestamp to user's local timezone
    formatTimestamp(isoString) {
        const date = new Date(isoString);
        const now = new Date();
        const isToday = date.toDateString() === now.toDateString();
        
        if (isToday) {
            // Show only time for today's messages
            return date.toLocaleTimeString(undefined, { 
                hour: '2-digit', 
                minute: '2-digit' 
            });
        } else {
            // Show date and time for older messages
            return date.toLocaleString(undefined, { 
                month: 'short', 
                day: 'numeric',
                hour: '2-digit', 
                minute: '2-digit' 
            });
        }
    }

    addMessage(message) {
        const messageEl = document.createElement('div');
        messageEl.className = 'message';
        messageEl.dataset.messageId = message.id;
        
        const timestamp = this.formatTimestamp(message.timestamp);
        const isOwn = chat.isOwnMessage(message);
        const avatarColor = this.getUserColor(message.username, message.avatarColor);
        const nameColor = this.getNameColor(message.nameColor);
        const displayName = message.displayName || message.username;
        const initials = this.getInitials(displayName);
        const avatarUrl = this.getAvatarUrl(message.avatarUrl);
        
        if (isOwn) {
            messageEl.classList.add('own-message');
        }
        
        // Build avatar HTML - image or initials
        let avatarHtml;
        if (avatarUrl) {
            avatarHtml = `
                <div class="message-avatar">
                    <img src="${avatarUrl}" alt="${this.escapeHtml(displayName)}" class="avatar-image">
                </div>
            `;
        } else {
            avatarHtml = `
                <div class="message-avatar" style="background-color: ${avatarColor}">
                    ${initials}
                </div>
            `;
        }
        
        messageEl.innerHTML = `
            ${avatarHtml}
            <div class="message-body">
                <div class="message-header">
                    <span class="message-username" style="color: ${nameColor}">${this.escapeHtml(displayName)}</span>
                    <span class="message-timestamp">${timestamp}</span>
                    ${isOwn ? `<button class="delete-message-btn" data-id="${message.id}" title="Delete message">×</button>` : ''}
                </div>
                <div class="message-content">${this.escapeHtml(message.content)}</div>
            </div>
        `;
        
        this.elements.messagesContainer.appendChild(messageEl);
        this.scrollToBottom();
    }

    removeMessage(messageId) {
        const messageEl = this.elements.messagesContainer.querySelector(`[data-message-id="${messageId}"]`);
        if (messageEl) {
            messageEl.remove();
        }
    }

    addSystemMessage(text) {
        const messageEl = document.createElement('div');
        messageEl.className = 'message system';
        messageEl.innerHTML = `<div class="message-content">${this.escapeHtml(text)}</div>`;
        this.elements.messagesContainer.appendChild(messageEl);
        this.scrollToBottom();
    }

    clearMessages() {
        this.elements.messagesContainer.innerHTML = '';
    }

    scrollToBottom() {
        this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
    }

    // Typing indicator
    showTypingIndicator(username) {
        this.elements.typingIndicator.textContent = `${username} is typing...`;
        
        clearTimeout(this.typingTimeout);
        this.typingTimeout = setTimeout(() => {
            this.elements.typingIndicator.textContent = '';
        }, 2000);
    }

    // Rooms
    renderRooms(roomList) {
        const currentRoom = rooms.getCurrentRoom();
        this.elements.roomsList.innerHTML = roomList.map(room => `
            <div class="room-item ${room === currentRoom ? 'active' : ''}" data-room="${room}">
                <span class="room-name"># ${room}</span>
                ${room !== 'general' ? `<button class="delete-room-btn" data-room="${room}" title="Delete room">×</button>` : ''}
            </div>
        `).join('');
    }

    setCurrentRoom(room) {
        this.elements.currentRoomHeader.textContent = `# ${room}`;
        document.querySelectorAll('.room-item').forEach(el => {
            el.classList.toggle('active', el.dataset.room === room);
        });
    }

    // Modals
    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('visible');
        }
    }

    hideModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('visible');
        }
    }

    hideAllModals() {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.classList.remove('visible');
        });
    }

    // Confirmation dialog
    showConfirm(title, message, onConfirm) {
        document.getElementById('confirm-title').textContent = title;
        document.getElementById('confirm-message').textContent = message;
        
        const confirmBtn = document.getElementById('confirm-yes-btn');
        const newConfirmBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        
        newConfirmBtn.addEventListener('click', () => {
            this.hideModal('confirm-modal');
            onConfirm();
        });
        
        this.showModal('confirm-modal');
    }

    // Button states
    setButtonLoading(button, loading, originalText) {
        if (loading) {
            button.disabled = true;
            button.dataset.originalText = button.textContent;
            button.textContent = 'Loading...';
        } else {
            button.disabled = false;
            button.textContent = originalText || button.dataset.originalText;
        }
    }

    // Form reset
    resetAuthForms() {
        this.elements.loginUsername.value = '';
        this.elements.loginPassword.value = '';
        this.elements.registerUsername.value = '';
        this.elements.registerPassword.value = '';
        this.elements.registerConfirm.value = '';
    }

    // Utility
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getElement(id) {
        return this.elements[id] || document.getElementById(id);
    }
}

export default new UIManager();
