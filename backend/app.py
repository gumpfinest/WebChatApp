from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
import sqlite3
import os
from datetime import datetime
from functools import wraps
import base64

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management
CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Avatar upload settings
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'avatars')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2MB max file size

# Create uploads folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
            display_name TEXT DEFAULT NULL,
            avatar_color TEXT DEFAULT NULL,
            name_color TEXT DEFAULT NULL,
            avatar_url TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Add columns if they don't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN avatar_color TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN name_color TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN display_name TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
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
    
    cursor.execute("SELECT id, username, password_hash, display_name, avatar_color, name_color, avatar_url FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"error": "Invalid username or password"}), 401
    
    # Return token
    token = f"{user['id']}:{user['username']}"
    return jsonify({
        "message": "Login successful",
        "user": {
            "id": user['id'],
            "username": user['username'],
            "displayName": user['display_name'],
            "avatarColor": user['avatar_color'],
            "nameColor": user['name_color'],
            "avatarUrl": user['avatar_url']
        },
        "token": token
    }), 200


@app.route("/api/verify", methods=["GET"])
@login_required
def verify_token():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT display_name, avatar_color, name_color, avatar_url FROM users WHERE id = ?", (request.user_id,))
    user = cursor.fetchone()
    conn.close()
    
    return jsonify({
        "valid": True,
        "user": {
            "id": request.user_id,
            "username": request.username,
            "displayName": user['display_name'] if user else None,
            "avatarColor": user['avatar_color'] if user else None,
            "nameColor": user['name_color'] if user else None,
            "avatarUrl": user['avatar_url'] if user else None
        }
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
        """SELECT m.id, m.username, m.content, m.room, m.timestamp, m.user_id,
                  u.display_name, u.avatar_color, u.name_color, u.avatar_url
           FROM messages m
           LEFT JOIN users u ON m.user_id = u.id
           WHERE m.room = ? ORDER BY m.timestamp DESC LIMIT 50""",
        (room,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    messages = [{
        'id': row['id'],
        'username': row['username'],
        'displayName': row['display_name'],
        'content': row['content'],
        'room': row['room'],
        'timestamp': row['timestamp'],
        'user_id': row['user_id'],
        'avatarColor': row['avatar_color'],
        'nameColor': row['name_color'],
        'avatarUrl': row['avatar_url']
    } for row in reversed(rows)]
    return jsonify(messages)


@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM rooms ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify([row['name'] for row in rows])


@app.route("/api/rooms", methods=["POST"])
@login_required
def create_room():
    data = request.get_json()
    name = data.get('name', '').strip().lower().replace(' ', '-')
    
    if not name:
        return jsonify({"error": "Room name is required"}), 400
    
    if len(name) < 2 or len(name) > 20:
        return jsonify({"error": "Room name must be 2-20 characters"}), 400
    
    # Only allow alphanumeric and hyphens
    if not all(c.isalnum() or c == '-' for c in name):
        return jsonify({"error": "Room name can only contain letters, numbers, and hyphens"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("INSERT INTO rooms (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        
        # Notify all clients about new room
        socketio.emit("room_created", {"name": name})
        
        return jsonify({"message": "Room created", "name": name}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Room already exists"}), 409


@app.route("/api/rooms/<name>", methods=["DELETE"])
@login_required
def delete_room(name):
    if name == 'general':
        return jsonify({"error": "Cannot delete the general room"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM rooms WHERE name = ?", (name,))
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"error": "Room not found"}), 404
    
    # Also delete messages in the room
    cursor.execute("DELETE FROM messages WHERE room = ?", (name,))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Room deleted"})


@app.route("/api/messages/<message_id>", methods=["DELETE"])
@login_required
def delete_message(message_id):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if message exists and belongs to user
    cursor.execute("SELECT user_id, room FROM messages WHERE id = ?", (message_id,))
    message = cursor.fetchone()
    
    if not message:
        conn.close()
        return jsonify({"error": "Message not found"}), 404
    
    if message['user_id'] != request.user_id:
        conn.close()
        return jsonify({"error": "You can only delete your own messages"}), 403
    
    cursor.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Message deleted", "id": message_id})


# ============ ACCOUNT ROUTES ============

@app.route("/api/account", methods=["DELETE"])
@login_required
def delete_account():
    conn = get_db()
    cursor = conn.cursor()
    
    # Delete user's messages
    cursor.execute("DELETE FROM messages WHERE user_id = ?", (request.user_id,))
    
    # Delete user
    cursor.execute("DELETE FROM users WHERE id = ?", (request.user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Account deleted"})


@app.route("/api/account/password", methods=["PUT"])
@login_required
def change_password():
    data = request.get_json()
    current_password = data.get('currentPassword', '')
    new_password = data.get('newPassword', '')
    
    if not current_password or not new_password:
        return jsonify({"error": "Current and new password are required"}), 400
    
    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT password_hash FROM users WHERE id = ?", (request.user_id,))
    user = cursor.fetchone()
    
    if not user or not check_password_hash(user['password_hash'], current_password):
        conn.close()
        return jsonify({"error": "Current password is incorrect"}), 401
    
    new_hash = generate_password_hash(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, request.user_id))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Password changed successfully"})


@app.route("/api/account/profile", methods=["GET"])
@login_required
def get_profile():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT username, display_name, avatar_color, name_color, avatar_url FROM users WHERE id = ?", (request.user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({
        "username": user['username'],
        "displayName": user['display_name'],
        "avatarColor": user['avatar_color'],
        "nameColor": user['name_color'],
        "avatarUrl": user['avatar_url']
    })


@app.route("/api/account/profile", methods=["PUT"])
@login_required
def update_profile():
    data = request.get_json()
    avatar_color = data.get('avatarColor')
    name_color = data.get('nameColor')
    display_name = data.get('displayName')
    
    # Validate colors (should be hex color codes)
    import re
    hex_pattern = re.compile(r'^#[0-9A-Fa-f]{6}$')
    
    if avatar_color and not hex_pattern.match(avatar_color):
        return jsonify({"error": "Invalid avatar color format"}), 400
    
    if name_color and not hex_pattern.match(name_color):
        return jsonify({"error": "Invalid name color format"}), 400
    
    # Validate display name
    if display_name is not None:
        display_name = display_name.strip() if display_name else None
        if display_name and (len(display_name) < 1 or len(display_name) > 32):
            return jsonify({"error": "Display name must be 1-32 characters"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE users SET avatar_color = ?, name_color = ?, display_name = ? WHERE id = ?",
        (avatar_color, name_color, display_name, request.user_id)
    )
    conn.commit()
    conn.close()
    
    return jsonify({
        "message": "Profile updated",
        "displayName": display_name,
        "avatarColor": avatar_color,
        "nameColor": name_color
    })


@app.route("/api/account/avatar", methods=["POST"])
@login_required
def upload_avatar():
    # Check if it's a base64 upload or file upload
    if request.is_json:
        # Base64 upload
        data = request.get_json()
        image_data = data.get('image')
        
        if not image_data:
            return jsonify({"error": "No image data provided"}), 400
        
        try:
            # Parse base64 data (format: data:image/png;base64,...)
            if ',' in image_data:
                header, encoded = image_data.split(',', 1)
                # Get file extension from header
                if 'png' in header:
                    ext = 'png'
                elif 'jpeg' in header or 'jpg' in header:
                    ext = 'jpg'
                elif 'gif' in header:
                    ext = 'gif'
                elif 'webp' in header:
                    ext = 'webp'
                else:
                    return jsonify({"error": "Unsupported image format"}), 400
            else:
                return jsonify({"error": "Invalid image data format"}), 400
            
            # Decode and save
            image_bytes = base64.b64decode(encoded)
            
            # Check file size (2MB limit)
            if len(image_bytes) > MAX_CONTENT_LENGTH:
                return jsonify({"error": "Image too large. Maximum size is 2MB"}), 400
            
            # Generate unique filename
            filename = f"{request.user_id}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            
            # Delete old avatar if exists
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT avatar_url FROM users WHERE id = ?", (request.user_id,))
            user = cursor.fetchone()
            if user and user['avatar_url']:
                old_filename = user['avatar_url'].split('/')[-1]
                old_path = os.path.join(UPLOAD_FOLDER, old_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)
            
            # Save new avatar
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
            
            # Update database
            avatar_url = f"/api/avatars/{filename}"
            cursor.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_url, request.user_id))
            conn.commit()
            conn.close()
            
            return jsonify({
                "message": "Avatar uploaded successfully",
                "avatarUrl": avatar_url
            })
            
        except Exception as e:
            return jsonify({"error": f"Failed to process image: {str(e)}"}), 400
    
    else:
        # File upload
        if 'avatar' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['avatar']
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type. Allowed: png, jpg, jpeg, gif, webp"}), 400
        
        # Generate unique filename
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{request.user_id}_{uuid.uuid4().hex[:8]}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Delete old avatar if exists
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT avatar_url FROM users WHERE id = ?", (request.user_id,))
        user = cursor.fetchone()
        if user and user['avatar_url']:
            old_filename = user['avatar_url'].split('/')[-1]
            old_path = os.path.join(UPLOAD_FOLDER, old_filename)
            if os.path.exists(old_path):
                os.remove(old_path)
        
        # Save new avatar
        file.save(filepath)
        
        # Update database
        avatar_url = f"/api/avatars/{filename}"
        cursor.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_url, request.user_id))
        conn.commit()
        conn.close()
        
        return jsonify({
            "message": "Avatar uploaded successfully",
            "avatarUrl": avatar_url
        })


@app.route("/api/account/avatar", methods=["DELETE"])
@login_required
def delete_avatar():
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current avatar
    cursor.execute("SELECT avatar_url FROM users WHERE id = ?", (request.user_id,))
    user = cursor.fetchone()
    
    if user and user['avatar_url']:
        # Delete file
        filename = user['avatar_url'].split('/')[-1]
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # Update database
        cursor.execute("UPDATE users SET avatar_url = NULL WHERE id = ?", (request.user_id,))
        conn.commit()
    
    conn.close()
    return jsonify({"message": "Avatar removed"})


@app.route("/api/avatars/<filename>")
def serve_avatar(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


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
    
    # Get user's profile data
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT display_name, avatar_color, name_color, avatar_url FROM users WHERE id = ?", (user["user_id"],))
    user_profile = cursor.fetchone()
    
    # Save to database
    cursor.execute(
        "INSERT INTO messages (id, user_id, username, content, room, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, user["user_id"], user["username"], content, room, timestamp)
    )
    conn.commit()
    conn.close()
    
    message = {
        "id": message_id,
        "username": user["username"],
        "displayName": user_profile['display_name'] if user_profile else None,
        "content": content,
        "room": room,
        "timestamp": timestamp,
        "avatarColor": user_profile['avatar_color'] if user_profile else None,
        "nameColor": user_profile['name_color'] if user_profile else None,
        "avatarUrl": user_profile['avatar_url'] if user_profile else None
    }
    
    emit("new_message", message, room=room)


@socketio.on("typing")
def handle_typing(data):
    user = active_users.get(request.sid)
    if not user:
        return
    
    room = data.get("room", "general")
    emit("user_typing", {"username": user["username"]}, room=room, include_self=False)


@socketio.on("delete_message")
def handle_delete_message(data):
    user = active_users.get(request.sid)
    if not user:
        emit("error", {"message": "Not authenticated"})
        return
    
    message_id = data.get("messageId")
    room = data.get("room", "general")
    
    if not message_id:
        return
    
    # Verify ownership and delete
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM messages WHERE id = ?", (message_id,))
    message = cursor.fetchone()
    
    if message and message['user_id'] == user['user_id']:
        cursor.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        conn.commit()
        emit("message_deleted", {"messageId": message_id}, room=room)
    
    conn.close()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
