// Socket.IO Connection Manager
import CONFIG from './config.js';
import auth from './auth.js';

class SocketManager {
    constructor() {
        this.socket = null;
        this.eventHandlers = {};
    }

    connect() {
        if (this.socket) {
            this.socket.disconnect();
        }

        this.socket = io(CONFIG.BACKEND_URL);

        this.socket.on('connect', () => {
            console.log('Connected to server');
            this.socket.emit('authenticate', { token: auth.getToken() });
        });

        this.socket.on('authenticated', (data) => {
            if (data.success) {
                console.log('Socket authenticated');
                this.trigger('authenticated', data);
            } else {
                console.error('Socket authentication failed:', data.error);
                this.trigger('auth_failed', data);
            }
        });

        this.socket.on('disconnect', () => {
            console.log('Disconnected from server');
            this.trigger('disconnected');
        });

        this.socket.on('new_message', (message) => {
            this.trigger('new_message', message);
        });

        this.socket.on('message_deleted', (data) => {
            this.trigger('message_deleted', data);
        });

        this.socket.on('user_joined', (data) => {
            this.trigger('user_joined', data);
        });

        this.socket.on('user_left', (data) => {
            this.trigger('user_left', data);
        });

        this.socket.on('user_typing', (data) => {
            this.trigger('user_typing', data);
        });

        this.socket.on('room_joined', (data) => {
            this.trigger('room_joined', data);
        });

        this.socket.on('room_created', (data) => {
            this.trigger('room_created', data);
        });

        this.socket.on('error', (data) => {
            console.error('Socket error:', data.message);
            this.trigger('error', data);
        });
    }

    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
    }

    joinRoom(room) {
        if (this.socket) {
            this.socket.emit('join', { room });
        }
    }

    leaveRoom(room) {
        if (this.socket) {
            this.socket.emit('leave', { room });
        }
    }

    sendMessage(content, room) {
        if (this.socket) {
            this.socket.emit('message', { content, room });
        }
    }

    deleteMessage(messageId, room) {
        if (this.socket) {
            this.socket.emit('delete_message', { messageId, room });
        }
    }

    sendTyping(room) {
        if (this.socket) {
            this.socket.emit('typing', { room });
        }
    }

    // Event handling
    on(event, handler) {
        if (!this.eventHandlers[event]) {
            this.eventHandlers[event] = [];
        }
        this.eventHandlers[event].push(handler);
    }

    off(event, handler) {
        if (this.eventHandlers[event]) {
            this.eventHandlers[event] = this.eventHandlers[event].filter(h => h !== handler);
        }
    }

    trigger(event, data) {
        if (this.eventHandlers[event]) {
            this.eventHandlers[event].forEach(handler => handler(data));
        }
    }
}

export default new SocketManager();
