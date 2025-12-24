from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import sqlite3
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management
CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Database setup
DATABASE = 'chat.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            content TEXT NOT NULL,
            room TEXT DEFAULT 'general',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Rooms table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert default room
    cursor.execute("INSERT OR IGNORE INTO rooms (name) VALUES ('general')")
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

# In-memory storage for active socket connections
active_users = {}

# Auth decorator for protected routes
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({"error": "No authorization header"}), 401
        
        try:
            # Simple token: "Bearer user_id:username"
            token = auth_header.split(' ')[1]
            user_id, username = token.split(':')
            request.user_id = int(user_id)
            request.username = username
        except:
            return jsonify({"error": "Invalid token"}), 401
        
        return f(*args, **kwargs)
    return decorated_function


# ============ AUTH ROUTES ============

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    
    if len(username) < 3 or len(username) > 20:
        return jsonify({"error": "Username must be 3-20 characters"}), 400
    
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if username exists
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "Username already exists"}), 409
    
    # Create user
    password_hash = generate_password_hash(password)
    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    
    # Return token
    token = f"{user_id}:{username}"
    return jsonify({
        "message": "Registration successful",
        "user": {"id": user_id, "username": username},
        "token": token
    }), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"error": "Invalid username or password"}), 401
    
    # Return token
    token = f"{user['id']}:{user['username']}"
    return jsonify({
        "message": "Login successful",
        "user": {"id": user['id'], "username": user['username']},
        "token": token
    }), 200


@app.route("/api/verify", methods=["GET"])
@login_required
def verify_token():
    return jsonify({
        "valid": True,
        "user": {"id": request.user_id, "username": request.username}
    })


# ============ API ROUTES ============

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


@app.route("/api/messages", methods=["GET"])
def get_messages():
    room = request.args.get("room", "general")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, content, room, timestamp FROM messages WHERE room = ? ORDER BY timestamp DESC LIMIT 50",
        (room,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    messages = [dict(row) for row in reversed(rows)]
    return jsonify(messages)


@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM rooms ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify([row['name'] for row in rows])


# ============ SOCKET.IO EVENTS ============

@socketio.on("connect")
def handle_connect():
    print(f"Client connected: {request.sid}")


@socketio.on("disconnect")
def handle_disconnect():
    user = active_users.pop(request.sid, None)
    if user:
        emit("user_left", {"username": user["username"]}, broadcast=True)
    print(f"Client disconnected: {request.sid}")


@socketio.on("authenticate")
def handle_authenticate(data):
    """Authenticate socket connection with token"""
    token = data.get('token', '')
    try:
        user_id, username = token.split(':')
        active_users[request.sid] = {
            "user_id": int(user_id),
            "username": username,
            "room": "general"
        }
        emit("authenticated", {"success": True, "username": username})
    except:
        emit("authenticated", {"success": False, "error": "Invalid token"})


@socketio.on("join")
def handle_join(data):
    user = active_users.get(request.sid)
    if not user:
        emit("error", {"message": "Not authenticated"})
        return
    
    room = data.get("room", "general")
    user["room"] = room
    join_room(room)
    
    emit("user_joined", {"username": user["username"], "room": room}, room=room)
    emit("room_joined", {"room": room, "username": user["username"]})


@socketio.on("leave")
def handle_leave(data):
    user = active_users.get(request.sid)
    if not user:
        return
    
    room = data.get("room", "general")
    leave_room(room)
    emit("user_left", {"username": user["username"], "room": room}, room=room)


@socketio.on("message")
def handle_message(data):
    user = active_users.get(request.sid)
    if not user:
        emit("error", {"message": "Not authenticated"})
        return
    
    room = data.get("room", "general")
    content = data.get("content", "").strip()
    
    if not content:
        return
    
    message_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    
    # Save to database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (id, user_id, username, content, room, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, user["user_id"], user["username"], content, room, timestamp)
    )
    conn.commit()
    conn.close()
    
    message = {
        "id": message_id,
        "username": user["username"],
        "content": content,
        "room": room,
        "timestamp": timestamp
    }
    
    emit("new_message", message, room=room)


@socketio.on("typing")
def handle_typing(data):
    user = active_users.get(request.sid)
    if not user:
        return
    
    room = data.get("room", "general")
    emit("user_typing", {"username": user["username"]}, room=room, include_self=False)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
