# Web Chat Application

A real-time web chat application built with **Node.js** (frontend server) and **Python Flask** (backend API with WebSocket support).

## Project Structure

```
WebChatApp/
├── backend/                 # Python Flask Backend
│   ├── app.py              # Main Flask application with Socket.IO
│   └── requirements.txt    # Python dependencies
├── frontend/               # Node.js Frontend
│   ├── server.js          # Express server
│   ├── package.json       # Node.js dependencies
│   └── public/            # Static files
│       ├── index.html     # Main HTML page
│       ├── styles.css     # Styling
│       └── app.js         # Client-side JavaScript
├── Main.py                # (Original file - can be removed)
└── README.md              # This file
```

## Features

- Real-time messaging with WebSockets
- Username-based authentication
- Chat rooms support
- Typing indicators
- Responsive design
- Modern Discord-like UI

## Prerequisites

- **Python 3.8+**
- **Node.js 16+**
- **npm** (comes with Node.js)

## Installation & Setup

### 1. Backend Setup (Python)

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Frontend Setup (Node.js)

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install
```

## Running the Application

### 1. Start the Backend Server

```bash
cd backend
python app.py
```

The backend will run on `http://localhost:5000`

### 2. Start the Frontend Server

```bash
cd frontend
npm start
```

The frontend will run on `http://localhost:3000`

### 3. Open the Application

Open your browser and navigate to `http://localhost:3000`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/messages?room=<room>` | Get messages for a room |
| GET | `/api/rooms` | Get list of rooms |

## WebSocket Events

### Client → Server

| Event | Data | Description |
|-------|------|-------------|
| `join` | `{username, room}` | Join a chat room |
| `leave` | `{room}` | Leave a chat room |
| `message` | `{content, room}` | Send a message |
| `typing` | `{room}` | Notify typing |

### Server → Client

| Event | Data | Description |
|-------|------|-------------|
| `new_message` | `{id, username, content, room, timestamp}` | New message received |
| `user_joined` | `{username, room}` | User joined room |
| `user_left` | `{username, room}` | User left room |
| `user_typing` | `{username}` | User is typing |

## Development

### Running in Development Mode

**Backend:**
```bash
cd backend
python app.py  # Flask runs in debug mode by default
```

**Frontend:**
```bash
cd frontend
npm run dev  # Uses nodemon for auto-reload
```

## Tech Stack

- **Backend:** Python, Flask, Flask-SocketIO, Flask-CORS
- **Frontend:** Node.js, Express, Socket.IO Client
- **Styling:** Vanilla CSS with modern design

## License

MIT License
