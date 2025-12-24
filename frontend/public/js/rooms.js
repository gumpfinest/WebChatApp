// Rooms Manager
import api from './api.js';
import socket from './socket.js';

class RoomsManager {
    constructor() {
        this.currentRoom = 'general';
        this.rooms = [];
        this.onRoomChange = null;
        this.onRoomsUpdate = null;
    }

    async loadRooms() {
        try {
            this.rooms = await api.getRooms();
            if (this.onRoomsUpdate) {
                this.onRoomsUpdate(this.rooms);
            }
            return this.rooms;
        } catch (error) {
            console.error('Error loading rooms:', error);
            return [];
        }
    }

    async createRoom(name) {
        const trimmedName = name.trim().toLowerCase().replace(/\s+/g, '-');
        
        if (!trimmedName) {
            throw new Error('Room name cannot be empty');
        }
        
        if (trimmedName.length < 2 || trimmedName.length > 20) {
            throw new Error('Room name must be 2-20 characters');
        }
        
        if (this.rooms.includes(trimmedName)) {
            throw new Error('Room already exists');
        }

        const result = await api.createRoom(trimmedName);
        await this.loadRooms();
        return result;
    }

    async deleteRoom(name) {
        if (name === 'general') {
            throw new Error('Cannot delete the general room');
        }
        
        const result = await api.deleteRoom(name);
        await this.loadRooms();
        
        // If we were in the deleted room, switch to general
        if (this.currentRoom === name) {
            this.switchRoom('general');
        }
        
        return result;
    }

    switchRoom(room) {
        if (room === this.currentRoom) return;

        socket.leaveRoom(this.currentRoom);
        this.currentRoom = room;
        socket.joinRoom(room);

        if (this.onRoomChange) {
            this.onRoomChange(room);
        }
    }

    getCurrentRoom() {
        return this.currentRoom;
    }

    getRooms() {
        return this.rooms;
    }

    reset() {
        this.currentRoom = 'general';
        this.rooms = [];
    }
}

export default new RoomsManager();
