// Main Application Entry Point
import api from './api.js';
import auth from './auth.js';
import socket from './socket.js';
import rooms from './rooms.js';
import chat from './chat.js';
import ui from './ui.js';

class App {
    constructor() {
        this.initialized = false;
    }

    async init() {
        // Initialize UI
        ui.init();

        // Set up event handlers
        this.setupAuthHandlers();
        this.setupChatHandlers();
        this.setupRoomHandlers();
        this.setupSettingsHandlers();
        this.setup2FAHandlers();
        this.setupSocketHandlers();
        this.setupModalHandlers();

        // Check for existing session
        await this.checkSession();
        
        this.initialized = true;
    }

    async checkSession() {
        try {
            await api.healthCheck();
            console.log('Backend is healthy');
            
            if (await auth.verifySession()) {
                this.enterChat();
            } else {
                ui.showAuthScreen();
            }
        } catch (error) {
            console.warn('Backend not available:', error);
            ui.showAuthScreen();
        }
    }

    enterChat() {
        const user = auth.getUser();
        ui.setCurrentUser(user.username, user.avatarColor, user.nameColor, user.avatarUrl, user.displayName);
        ui.showChatScreen();
        
        socket.connect();
        rooms.loadRooms();
    }

    logout() {
        socket.disconnect();
        auth.clearAuth();
        rooms.reset();
        chat.clearMessages();
        ui.clearMessages();
        ui.resetAuthForms();
        ui.showAuthScreen();
        ui.showLoginForm();
    }

    // Auth event handlers
    setupAuthHandlers() {
        // Switch forms
        ui.elements.showRegisterLink.addEventListener('click', (e) => {
            e.preventDefault();
            ui.showRegisterForm();
        });

        ui.elements.showLoginLink.addEventListener('click', (e) => {
            e.preventDefault();
            ui.showLoginForm();
        });

        // Login
        ui.elements.loginBtn.addEventListener('click', () => this.handleLogin());
        ui.elements.loginUsername.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') ui.elements.loginPassword.focus();
        });
        ui.elements.loginPassword.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleLogin();
        });

        // Register
        ui.elements.registerBtn.addEventListener('click', () => this.handleRegister());
        ui.elements.registerUsername.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') ui.elements.registerPassword.focus();
        });
        ui.elements.registerPassword.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') ui.elements.registerConfirm.focus();
        });
        ui.elements.registerConfirm.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleRegister();
        });

        // Logout
        ui.elements.logoutBtn.addEventListener('click', () => this.logout());
    }

    async handleLogin() {
        const username = ui.elements.loginUsername.value.trim();
        const password = ui.elements.loginPassword.value;

        if (!username || !password) {
            ui.showError('login-error', 'Please enter username and password');
            return;
        }

        ui.setButtonLoading(ui.elements.loginBtn, true);

        try {
            const result = await auth.login(username, password);
            
            // Check if 2FA is required
            if (result && result.requires2FA) {
                ui.setButtonLoading(ui.elements.loginBtn, false, 'Login');
                this.show2FALoginModal(result.emailHint);
                return;
            }
            
            this.enterChat();
        } catch (error) {
            ui.showError('login-error', error.message);
        } finally {
            ui.setButtonLoading(ui.elements.loginBtn, false, 'Login');
        }
    }

    async handleRegister() {
        const username = ui.elements.registerUsername.value.trim();
        const password = ui.elements.registerPassword.value;
        const confirm = ui.elements.registerConfirm.value;

        if (!username || !password || !confirm) {
            ui.showError('register-error', 'Please fill in all fields');
            return;
        }

        if (password !== confirm) {
            ui.showError('register-error', 'Passwords do not match');
            return;
        }

        ui.setButtonLoading(ui.elements.registerBtn, true);

        try {
            await auth.register(username, password);
            this.enterChat();
        } catch (error) {
            ui.showError('register-error', error.message);
        } finally {
            ui.setButtonLoading(ui.elements.registerBtn, false, 'Create Account');
        }
    }

    // Chat event handlers
    setupChatHandlers() {
        // Send message
        ui.elements.sendBtn.addEventListener('click', () => this.handleSendMessage());
        ui.elements.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.handleSendMessage();
            } else {
                chat.sendTyping();
            }
        });

        // Delete message
        ui.elements.messagesContainer.addEventListener('click', (e) => {
            if (e.target.classList.contains('delete-message-btn')) {
                const messageId = e.target.dataset.id;
                this.handleDeleteMessage(messageId);
            }
        });

        // Chat callbacks
        chat.onMessagesLoaded = (messages) => ui.renderMessages(messages);
        chat.onNewMessage = (message) => ui.addMessage(message);
        chat.onMessageDeleted = (messageId) => ui.removeMessage(messageId);
    }

    handleSendMessage() {
        const content = ui.elements.messageInput.value;
        if (chat.sendMessage(content)) {
            ui.elements.messageInput.value = '';
        }
    }

    handleDeleteMessage(messageId) {
        ui.showConfirm('Delete Message', 'Are you sure you want to delete this message?', async () => {
            try {
                await chat.deleteMessage(messageId);
            } catch (error) {
                alert('Failed to delete message: ' + error.message);
            }
        });
    }

    // Room event handlers
    setupRoomHandlers() {
        // Room click (on room name, not delete button)
        ui.elements.roomsList.addEventListener('click', (e) => {
            // Handle delete room button
            if (e.target.classList.contains('delete-room-btn')) {
                e.stopPropagation();
                const roomName = e.target.dataset.room;
                this.handleDeleteRoom(roomName);
                return;
            }
            
            // Handle room selection (click on room-item or room-name)
            const roomItem = e.target.closest('.room-item');
            if (roomItem) {
                rooms.switchRoom(roomItem.dataset.room);
            }
        });

        // Open create room modal button (the "+" in sidebar)
        ui.elements.openCreateRoomBtn?.addEventListener('click', () => {
            ui.showModal('create-room-modal');
        });

        // Submit create room form (the "Create" button in modal)
        document.getElementById('create-room-btn')?.addEventListener('click', () => this.handleCreateRoom());
        document.getElementById('new-room-name')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleCreateRoom();
        });

        // Room callbacks
        rooms.onRoomChange = (room) => {
            ui.setCurrentRoom(room);
            ui.clearMessages();
            chat.loadMessages(room);
        };

        rooms.onRoomsUpdate = (roomList) => {
            ui.renderRooms(roomList);
        };
    }

    handleDeleteRoom(roomName) {
        ui.showConfirm('Delete Room', `Are you sure you want to delete the room "${roomName}"? All messages in this room will be lost.`, async () => {
            try {
                await rooms.deleteRoom(roomName);
            } catch (error) {
                alert('Failed to delete room: ' + error.message);
            }
        });
    }

    async handleCreateRoom() {
        const input = document.getElementById('new-room-name');
        const name = input.value.trim();

        if (!name) {
            alert('Please enter a room name');
            return;
        }

        try {
            await rooms.createRoom(name);
            input.value = '';
            ui.hideModal('create-room-modal');
        } catch (error) {
            alert(error.message);
        }
    }

    // Settings handlers
    setupSettingsHandlers() {
        // Open settings
        ui.elements.settingsBtn?.addEventListener('click', () => {
            this.loadColorSettings();
            this.load2FAStatus();
            ui.showModal('settings-modal');
        });

        // Color pickers - live preview
        const avatarColorPicker = document.getElementById('avatar-color');
        const nameColorPicker = document.getElementById('name-color');
        const avatarPreview = document.getElementById('avatar-preview');
        const namePreview = document.getElementById('name-preview');

        avatarColorPicker?.addEventListener('input', (e) => {
            if (avatarPreview) {
                avatarPreview.style.backgroundColor = e.target.value;
            }
        });

        nameColorPicker?.addEventListener('input', (e) => {
            if (namePreview) {
                namePreview.style.color = e.target.value;
            }
        });

        // Reset color buttons
        document.getElementById('reset-avatar-color')?.addEventListener('click', () => {
            const user = auth.getUser();
            const defaultColor = ui.getDefaultColor(user.username);
            if (avatarColorPicker) avatarColorPicker.value = defaultColor;
            if (avatarPreview) avatarPreview.style.backgroundColor = defaultColor;
        });

        document.getElementById('reset-name-color')?.addEventListener('click', () => {
            const defaultColor = '#7289da';
            if (nameColorPicker) nameColorPicker.value = defaultColor;
            if (namePreview) namePreview.style.color = defaultColor;
        });

        // Save profile (colors + display name)
        document.getElementById('save-profile-btn')?.addEventListener('click', () => this.handleSaveProfile());

        // Avatar upload
        document.getElementById('avatar-upload')?.addEventListener('change', (e) => this.handleAvatarUpload(e));
        
        // Remove avatar
        document.getElementById('remove-avatar-btn')?.addEventListener('click', () => this.handleRemoveAvatar());

        // Change password
        document.getElementById('change-password-btn')?.addEventListener('click', () => this.handleChangePassword());

        // Delete account
        document.getElementById('delete-account-btn')?.addEventListener('click', () => {
            ui.showConfirm('Delete Account', 'Are you sure you want to delete your account? This action cannot be undone.', async () => {
                try {
                    await auth.deleteAccount();
                    this.logout();
                } catch (error) {
                    alert('Failed to delete account: ' + error.message);
                }
            });
        });
    }

    loadColorSettings() {
        const user = auth.getUser();
        const avatarColorPicker = document.getElementById('avatar-color');
        const nameColorPicker = document.getElementById('name-color');
        const avatarPreview = document.getElementById('avatar-preview');
        const namePreview = document.getElementById('name-preview');
        const displayNameInput = document.getElementById('display-name');
        const settingsAvatarPreview = document.getElementById('settings-avatar-preview');
        const settingsAvatarInitial = document.getElementById('settings-avatar-initial');
        const settingsAvatarImage = document.getElementById('settings-avatar-image');

        const displayName = user.displayName || user.username;
        const avatarColor = user.avatarColor || ui.getDefaultColor(user.username);
        const nameColor = user.nameColor || '#7289da';

        if (avatarColorPicker) avatarColorPicker.value = avatarColor;
        if (nameColorPicker) nameColorPicker.value = nameColor;
        if (displayNameInput) displayNameInput.value = user.displayName || '';
        
        if (avatarPreview) {
            avatarPreview.textContent = displayName.charAt(0).toUpperCase();
            avatarPreview.style.backgroundColor = avatarColor;
        }
        if (namePreview) {
            namePreview.textContent = displayName;
            namePreview.style.color = nameColor;
        }
        
        // Update settings avatar preview
        if (settingsAvatarPreview) {
            settingsAvatarPreview.style.backgroundColor = avatarColor;
        }
        if (settingsAvatarInitial) {
            settingsAvatarInitial.textContent = displayName.charAt(0).toUpperCase();
        }
        
        // Show avatar image if exists
        if (user.avatarUrl) {
            const fullUrl = ui.getAvatarUrl(user.avatarUrl);
            if (settingsAvatarImage) {
                settingsAvatarImage.src = fullUrl;
                settingsAvatarImage.classList.remove('hidden');
            }
            if (settingsAvatarInitial) {
                settingsAvatarInitial.classList.add('hidden');
            }
        } else {
            if (settingsAvatarImage) {
                settingsAvatarImage.classList.add('hidden');
            }
            if (settingsAvatarInitial) {
                settingsAvatarInitial.classList.remove('hidden');
            }
        }
    }

    async handleAvatarUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        // Validate file type
        const validTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
        if (!validTypes.includes(file.type)) {
            alert('Invalid file type. Please upload PNG, JPG, GIF, or WebP.');
            return;
        }

        // Validate file size (2MB)
        if (file.size > 2 * 1024 * 1024) {
            alert('File too large. Maximum size is 2MB.');
            return;
        }

        // Convert to base64
        const reader = new FileReader();
        reader.onload = async (e) => {
            try {
                const imageData = e.target.result;
                const result = await auth.uploadAvatar(imageData);
                
                // Update preview
                const settingsAvatarImage = document.getElementById('settings-avatar-image');
                const settingsAvatarInitial = document.getElementById('settings-avatar-initial');
                
                if (settingsAvatarImage) {
                    settingsAvatarImage.src = ui.getAvatarUrl(result.avatarUrl);
                    settingsAvatarImage.classList.remove('hidden');
                }
                if (settingsAvatarInitial) {
                    settingsAvatarInitial.classList.add('hidden');
                }
                
                // Update sidebar
                const user = auth.getUser();
                ui.updateUserAppearance(user.username, user.avatarColor, user.nameColor, user.avatarUrl, user.displayName);
                
                alert('Avatar uploaded successfully!');
            } catch (error) {
                alert('Failed to upload avatar: ' + error.message);
            }
        };
        reader.readAsDataURL(file);
        
        // Clear the input so the same file can be selected again
        event.target.value = '';
    }

    async handleRemoveAvatar() {
        const user = auth.getUser();
        if (!user.avatarUrl) {
            alert('No avatar to remove');
            return;
        }

        try {
            await auth.deleteAvatar();
            
            // Update preview
            const settingsAvatarImage = document.getElementById('settings-avatar-image');
            const settingsAvatarInitial = document.getElementById('settings-avatar-initial');
            
            if (settingsAvatarImage) {
                settingsAvatarImage.classList.add('hidden');
            }
            if (settingsAvatarInitial) {
                settingsAvatarInitial.classList.remove('hidden');
            }
            
            // Update sidebar
            const updatedUser = auth.getUser();
            ui.updateUserAppearance(updatedUser.username, updatedUser.avatarColor, updatedUser.nameColor, null, updatedUser.displayName);
            
            alert('Avatar removed');
        } catch (error) {
            alert('Failed to remove avatar: ' + error.message);
        }
    }

    async handleSaveProfile() {
        const avatarColor = document.getElementById('avatar-color')?.value;
        const nameColor = document.getElementById('name-color')?.value;
        const displayName = document.getElementById('display-name')?.value.trim() || null;

        try {
            await auth.updateProfile(avatarColor, nameColor, displayName);
            const user = auth.getUser();
            ui.updateUserAppearance(user.username, avatarColor, nameColor, user.avatarUrl, displayName);
            alert('Profile saved successfully!');
        } catch (error) {
            alert('Failed to save profile: ' + error.message);
        }
    }

    async handleChangePassword() {
        const currentPassword = document.getElementById('current-password').value;
        const newPassword = document.getElementById('new-password').value;
        const confirmPassword = document.getElementById('confirm-new-password').value;

        if (!currentPassword || !newPassword || !confirmPassword) {
            alert('Please fill in all password fields');
            return;
        }

        if (newPassword !== confirmPassword) {
            alert('New passwords do not match');
            return;
        }

        if (newPassword.length < 6) {
            alert('New password must be at least 6 characters');
            return;
        }

        try {
            await auth.changePassword(currentPassword, newPassword);
            alert('Password changed successfully');
            document.getElementById('current-password').value = '';
            document.getElementById('new-password').value = '';
            document.getElementById('confirm-new-password').value = '';
        } catch (error) {
            alert('Failed to change password: ' + error.message);
        }
    }

    // 2FA Handlers
    setup2FAHandlers() {
        // Enable 2FA button
        document.getElementById('enable-2fa-btn')?.addEventListener('click', () => this.handleEnable2FA());
        
        // Disable 2FA button
        document.getElementById('disable-2fa-btn')?.addEventListener('click', () => this.handleDisable2FA());
        
        // Verify 2FA setup button
        document.getElementById('verify-2fa-setup-btn')?.addEventListener('click', () => this.handleVerify2FASetup());
        
        // Resend 2FA code button
        document.getElementById('resend-2fa-code-btn')?.addEventListener('click', () => this.handleResend2FACode());
        
        // Copy backup codes
        document.getElementById('copy-backup-codes-btn')?.addEventListener('click', () => {
            const codesList = document.getElementById('backup-codes-list');
            if (codesList) {
                const codes = Array.from(codesList.children).map(li => li.textContent).join('\n');
                navigator.clipboard.writeText(codes);
                alert('Backup codes copied to clipboard!');
            }
        });
        
        // Close 2FA setup modal
        document.getElementById('close-2fa-setup-btn')?.addEventListener('click', () => {
            ui.hideModal('two-fa-setup-modal');
            this.load2FAStatus(); // Refresh status
        });
        
        // 2FA Login handlers
        document.getElementById('2fa-login-verify-btn')?.addEventListener('click', () => this.handle2FALogin());
        document.getElementById('2fa-login-code')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handle2FALogin();
        });
        document.getElementById('2fa-login-cancel-btn')?.addEventListener('click', () => {
            ui.hideModal('two-fa-login-modal');
            auth.cancelPending2FA();
        });
        
        // Input validation - only numbers
        document.getElementById('2fa-verify-code')?.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/[^0-9]/g, '');
        });
        document.getElementById('2fa-login-code')?.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/[^0-9]/g, '');
        });
    }

    async load2FAStatus() {
        const statusElement = document.getElementById('2fa-status');
        const statusText = document.getElementById('2fa-status-text');
        const enabledSection = document.getElementById('2fa-enabled-section');
        const disabledSection = document.getElementById('2fa-disabled-section');
        const emailDisplay = document.getElementById('2fa-email-display');
        
        try {
            const user = auth.getUser();
            const twoFactorEnabled = user?.email2FAEnabled || false;
            
            if (twoFactorEnabled) {
                statusText.textContent = '2FA is enabled';
                statusElement.classList.add('enabled');
                statusElement.classList.remove('disabled');
                enabledSection?.classList.remove('hidden');
                disabledSection?.classList.add('hidden');
                if (emailDisplay && user?.email) {
                    emailDisplay.textContent = `Email: ${user.email}`;
                }
            } else {
                statusText.textContent = '2FA is not enabled';
                statusElement.classList.add('disabled');
                statusElement.classList.remove('enabled');
                enabledSection?.classList.add('hidden');
                disabledSection?.classList.remove('hidden');
            }
        } catch (error) {
            statusText.textContent = 'Error loading status';
        }
    }

    async handleEnable2FA() {
        const email = document.getElementById('2fa-email')?.value.trim();
        
        if (!email) {
            alert('Please enter your email address');
            return;
        }
        
        // Basic email validation
        if (!email.includes('@') || !email.includes('.')) {
            alert('Please enter a valid email address');
            return;
        }
        
        try {
            const result = await api.setup2FA(email);
            
            // Show verification modal
            document.getElementById('2fa-email-hint').textContent = result.email_hint;
            document.getElementById('2fa-verify-code').value = '';
            document.getElementById('2fa-setup-step-1')?.classList.remove('hidden');
            document.getElementById('2fa-setup-step-2')?.classList.add('hidden');
            
            ui.showModal('two-fa-setup-modal');
        } catch (error) {
            alert('Failed to setup 2FA: ' + error.message);
        }
    }

    async handleResend2FACode() {
        try {
            const result = await api.resend2FACode();
            alert('Verification code resent to your email');
        } catch (error) {
            alert('Failed to resend code: ' + error.message);
        }
    }

    async handleVerify2FASetup() {
        const code = document.getElementById('2fa-verify-code')?.value;
        
        if (!code || code.length !== 6) {
            alert('Please enter a valid 6-digit code');
            return;
        }
        
        try {
            const result = await api.verify2FA(code);
            
            // Update user data
            const user = auth.getUser();
            user.email2FAEnabled = true;
            auth.setUser(user);
            
            // Show backup codes
            const backupCodesList = document.getElementById('backup-codes-list');
            if (backupCodesList && result.backupCodes) {
                backupCodesList.innerHTML = result.backupCodes.map(code => `<li>${code}</li>`).join('');
            }
            
            // Switch to step 2
            document.getElementById('2fa-setup-step-1')?.classList.add('hidden');
            document.getElementById('2fa-setup-step-2')?.classList.remove('hidden');
            
        } catch (error) {
            alert('Failed to verify code: ' + error.message);
        }
    }

    async handleDisable2FA() {
        const password = document.getElementById('disable-2fa-password')?.value;
        
        if (!password) {
            alert('Please enter your password to disable 2FA');
            return;
        }
        
        ui.showConfirm('Disable 2FA', 'Are you sure you want to disable two-factor authentication? This will make your account less secure.', async () => {
            try {
                await api.disable2FA(password);
                
                // Update user data
                const user = auth.getUser();
                user.email2FAEnabled = false;
                auth.setUser(user);
                
                // Clear password field
                document.getElementById('disable-2fa-password').value = '';
                
                this.load2FAStatus();
                alert('2FA has been disabled');
            } catch (error) {
                alert('Failed to disable 2FA: ' + error.message);
            }
        });
    }

    // Handle 2FA login when required
    show2FALoginModal(emailHint) {
        document.getElementById('2fa-login-code').value = '';
        document.getElementById('2fa-login-email-hint').textContent = emailHint || 'your registered email';
        ui.showModal('two-fa-login-modal');
        document.getElementById('2fa-login-code')?.focus();
    }

    async handle2FALogin() {
        const code = document.getElementById('2fa-login-code')?.value;
        
        if (!code || code.length !== 6) {
            alert('Please enter a valid 6-digit code');
            return;
        }
        
        try {
            await auth.login2FA(code);
            ui.hideModal('two-fa-login-modal');
            this.enterChat();
        } catch (error) {
            alert('Invalid code: ' + error.message);
        }
    }

    // Socket event handlers
    setupSocketHandlers() {
        socket.on('authenticated', () => {
            socket.joinRoom(rooms.getCurrentRoom());
        });

        socket.on('auth_failed', () => {
            this.logout();
        });

        socket.on('room_joined', (data) => {
            chat.loadMessages(data.room);
        });

        socket.on('new_message', (message) => {
            chat.addMessage(message);
        });

        socket.on('message_deleted', (data) => {
            chat.removeMessage(data.messageId);
        });

        socket.on('user_joined', (data) => {
            ui.addSystemMessage(`${data.username} joined the chat`);
        });

        socket.on('user_left', (data) => {
            ui.addSystemMessage(`${data.username} left the chat`);
        });

        socket.on('user_typing', (data) => {
            ui.showTypingIndicator(data.username);
        });

        socket.on('room_created', (data) => {
            rooms.loadRooms();
        });
    }

    // Modal handlers
    setupModalHandlers() {
        // Close modals on overlay click
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    ui.hideModal(modal.id);
                }
            });
        });

        // Close buttons
        document.querySelectorAll('.modal-close, .cancel-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                ui.hideAllModals();
            });
        });

        // ESC key closes modals
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                ui.hideAllModals();
            }
        });
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const app = new App();
    app.init();
});
