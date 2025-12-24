// Chat Manager - Handles messages
import api from './api.js';
import auth from './auth.js';
import socket from './socket.js';
import rooms from './rooms.js';

class ChatManager {
    constructor() {
        this.messages = [];
        this.onNewMessage = null;
        this.onMessageDeleted = null;
        this.onMessagesLoaded = null;
    }

    async loadMessages(room) {
        try {
            this.messages = await api.getMessages(room);
            if (this.onMessagesLoaded) {
                this.onMessagesLoaded(this.messages);
            }
            return this.messages;
        } catch (error) {
            console.error('Error loading messages:', error);
            return [];
        }
    }

    sendMessage(content) {
        const trimmedContent = content.trim();
        if (!trimmedContent) return false;

        socket.sendMessage(trimmedContent, rooms.getCurrentRoom());
        return true;
    }

    async deleteMessage(messageId) {
        try {
            await api.deleteMessage(messageId);
            socket.deleteMessage(messageId, rooms.getCurrentRoom());
            return true;
        } catch (error) {
            console.error('Error deleting message:', error);
            throw error;
        }
    }

    sendTyping() {
        socket.sendTyping(rooms.getCurrentRoom());
    }

    addMessage(message) {
        this.messages.push(message);
        if (this.onNewMessage) {
            this.onNewMessage(message);
        }
    }

    removeMessage(messageId) {
        this.messages = this.messages.filter(m => m.id !== messageId);
        if (this.onMessageDeleted) {
            this.onMessageDeleted(messageId);
        }
    }

    isOwnMessage(message) {
        const user = auth.getUser();
        return user && message.username === user.username;
    }

    clearMessages() {
        this.messages = [];
    }
}

export default new ChatManager();
