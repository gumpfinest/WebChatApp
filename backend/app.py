"""
WebChatApp Backend - Main Application
With integrated security features: JWT, Rate Limiting, Email 2FA, Message Encryption
"""
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
import re

# Import security modules
from security.jwt_auth import jwt_auth
from security.rate_limiter import rate_limiter
from security.email_2fa import email_2fa
from security.encryption import message_encryption

# ============ APP CONFIGURATION ============

app = Flask(__name__)

# Security configuration
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', os.urandom(32).hex())
app.config['JWT_REFRESH_SECRET_KEY'] = os.environ.get('JWT_REFRESH_SECRET_KEY', os.urandom(32).hex())
app.config['ENCRYPTION_MASTER_KEY'] = os.environ.get('ENCRYPTION_MASTER_KEY', None)
app.config['RATE_LIMIT_ENABLED'] = os.environ.get('RATE_LIMIT_ENABLED', 'true').lower() == 'true'

# Email 2FA configuration (set these environment variables for production)
app.config['SMTP_SERVER'] = os.environ.get('SMTP_SERVER')
app.config['SMTP_PORT'] = os.environ.get('SMTP_PORT', 587)
app.config['SMTP_USERNAME'] = os.environ.get('SMTP_USERNAME')
app.config['SMTP_PASSWORD'] = os.environ.get('SMTP_PASSWORD')
app.config['SMTP_FROM_EMAIL'] = os.environ.get('SMTP_FROM_EMAIL')
app.config['SMTP_FROM_NAME'] = os.environ.get('SMTP_FROM_NAME', 'WebChatApp')
app.config['EMAIL_2FA_CODE_LENGTH'] = 6
app.config['EMAIL_2FA_EXPIRY_MINUTES'] = 10

# Initialize security modules
jwt_auth.init_app(app)
rate_limiter.init_app(app)
email_2fa.init_app(app)
message_encryption.init_app(app)

app.secret_key = os.urandom(24)
CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Avatar upload settings
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'avatars')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2MB max file size

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ============ DATABASE SETUP ============

DATABASE = 'chat.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table with security fields
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT DEFAULT NULL,
            display_name TEXT DEFAULT NULL,
            avatar_color TEXT DEFAULT NULL,
            name_color TEXT DEFAULT NULL,
            avatar_url TEXT DEFAULT NULL,
            email_2fa_enabled INTEGER DEFAULT 0,
            email_2fa_code TEXT DEFAULT NULL,
            email_2fa_expiry TIMESTAMP DEFAULT NULL,
            backup_codes TEXT DEFAULT NULL,
            failed_login_attempts INTEGER DEFAULT 0,
            locked_until TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Add new columns if they don't exist (for existing databases)
    new_columns = [
        ("email", "TEXT DEFAULT NULL"),
        ("avatar_color", "TEXT DEFAULT NULL"),
        ("name_color", "TEXT DEFAULT NULL"),
        ("display_name", "TEXT DEFAULT NULL"),
        ("avatar_url", "TEXT DEFAULT NULL"),
        ("email_2fa_enabled", "INTEGER DEFAULT 0"),
        ("email_2fa_code", "TEXT DEFAULT NULL"),
        ("email_2fa_expiry", "TIMESTAMP DEFAULT NULL"),
        ("backup_codes", "TEXT DEFAULT NULL"),
        ("failed_login_attempts", "INTEGER DEFAULT 0"),
        ("locked_until", "TIMESTAMP DEFAULT NULL"),
    ]
    
    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass
    
    # Messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            content TEXT NOT NULL,
            encrypted INTEGER DEFAULT 0,
            room TEXT DEFAULT 'general',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Add encrypted column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE messages ADD COLUMN encrypted INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    
    # Rooms table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            encrypted INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Add encrypted column to rooms if it doesn't exist
    try:
        cursor.execute("ALTER TABLE rooms ADD COLUMN encrypted INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    
    # Refresh tokens table for token invalidation
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            revoked INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    cursor.execute("INSERT OR IGNORE INTO rooms (name, encrypted) VALUES ('general', 1)")
    
    conn.commit()
    conn.close()


init_db()

# In-memory storage for active socket connections
active_users = {}


# ============ AUTH ROUTES ============

@app.route("/api/register", methods=["POST"])
@rate_limiter.limit('register')
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
    
    # Validate username format
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return jsonify({"error": "Username can only contain letters, numbers, underscores, and hyphens"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "Username already exists"}), 409
    
    password_hash = generate_password_hash(password)
    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    
    # Generate JWT tokens
    tokens = jwt_auth.generate_tokens(user_id, username)
    
    return jsonify({
        "message": "Registration successful",
        "user": {"id": user_id, "username": username},
        **tokens
    }), 201


@app.route("/api/login", methods=["POST"])
@rate_limiter.limit('login')
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    email_2fa_code = data.get('email_2fa_code', '')
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, username, password_hash, email, display_name, avatar_color, name_color, 
               avatar_url, email_2fa_enabled, email_2fa_code, email_2fa_expiry, 
               failed_login_attempts, locked_until
        FROM users WHERE username = ?
    """, (username,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({"error": "Invalid username or password"}), 401
    
    # Check if account is locked
    if user['locked_until']:
        locked_until = datetime.fromisoformat(user['locked_until'])
        if datetime.utcnow() < locked_until:
            conn.close()
            return jsonify({
                "error": "Account temporarily locked due to too many failed attempts",
                "locked_until": user['locked_until']
            }), 423
        else:
            # Unlock the account
            cursor.execute("UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = ?", (user['id'],))
            conn.commit()
    
    # Verify password
    if not check_password_hash(user['password_hash'], password):
        # Increment failed attempts
        failed_attempts = user['failed_login_attempts'] + 1
        
        if failed_attempts >= 5:
            # Lock account for 15 minutes
            from datetime import timedelta
            lock_until = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            cursor.execute("UPDATE users SET failed_login_attempts = ?, locked_until = ? WHERE id = ?",
                          (failed_attempts, lock_until, user['id']))
        else:
            cursor.execute("UPDATE users SET failed_login_attempts = ? WHERE id = ?",
                          (failed_attempts, user['id']))
        
        conn.commit()
        conn.close()
        return jsonify({"error": "Invalid username or password"}), 401
    
    # Check Email 2FA if enabled
    if user['email_2fa_enabled'] and user['email']:
        if not email_2fa_code:
            # Generate and send a new code
            code = email_2fa.generate_code()
            expiry = email_2fa.get_expiry_time().isoformat()
            
            cursor.execute("""
                UPDATE users SET email_2fa_code = ?, email_2fa_expiry = ? WHERE id = ?
            """, (code, expiry, user['id']))
            conn.commit()
            
            # Send code via email
            email_2fa.send_code(user['email'], code, user['username'])
            
            conn.close()
            return jsonify({
                "message": "2FA code sent to your email",
                "requires_2fa": True,
                "email_hint": user['email'][:3] + "***" + user['email'][user['email'].index('@'):]
            }), 200
        
        # Verify the provided code
        if not email_2fa.verify_code(user['email_2fa_code'], email_2fa_code, user['email_2fa_expiry']):
            conn.close()
            return jsonify({"error": "Invalid or expired 2FA code"}), 401
        
        # Clear the code after successful verification
        cursor.execute("UPDATE users SET email_2fa_code = NULL, email_2fa_expiry = NULL WHERE id = ?", (user['id'],))
        conn.commit()
    
    # Reset failed attempts on successful login
    cursor.execute("UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = ?", (user['id'],))
    conn.commit()
    conn.close()
    
    # Generate JWT tokens
    tokens = jwt_auth.generate_tokens(user['id'], user['username'])
    
    return jsonify({
        "message": "Login successful",
        "user": {
            "id": user['id'],
            "username": user['username'],
            "email": user['email'],
            "displayName": user['display_name'],
            "avatarColor": user['avatar_color'],
            "nameColor": user['name_color'],
            "avatarUrl": user['avatar_url'],
            "email2FAEnabled": bool(user['email_2fa_enabled'])
        },
        **tokens
    }), 200


@app.route("/api/refresh", methods=["POST"])
def refresh_token():
    """Refresh the access token using a refresh token"""
    data = request.get_json()
    refresh_token = data.get('refresh_token')
    
    if not refresh_token:
        return jsonify({"error": "Refresh token required"}), 400
    
    result, error = jwt_auth.refresh_access_token(refresh_token)
    
    if error:
        return jsonify({"error": error}), 401
    
    return jsonify(result), 200


@app.route("/api/verify", methods=["GET"])
@jwt_auth.login_required
def verify_token():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT email, display_name, avatar_color, name_color, avatar_url, email_2fa_enabled 
        FROM users WHERE id = ?
    """, (request.user_id,))
    user = cursor.fetchone()
    conn.close()
    
    return jsonify({
        "valid": True,
        "user": {
            "id": request.user_id,
            "username": request.username,
            "email": user['email'] if user else None,
            "displayName": user['display_name'] if user else None,
            "avatarColor": user['avatar_color'] if user else None,
            "nameColor": user['name_color'] if user else None,
            "avatarUrl": user['avatar_url'] if user else None,
            "email2FAEnabled": bool(user['email_2fa_enabled']) if user else False
        }
    })


# ============ 2FA ROUTES ============

@app.route("/api/account/2fa/setup", methods=["POST"])
@jwt_auth.login_required
def setup_2fa():
    """Initialize Email 2FA setup - requires email address"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email:
        return jsonify({"error": "Email address is required"}), 400
    
    # Basic email validation
    if '@' not in email or '.' not in email:
        return jsonify({"error": "Invalid email address"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if 2FA is already enabled
    cursor.execute("SELECT email_2fa_enabled, email FROM users WHERE id = ?", (request.user_id,))
    user = cursor.fetchone()
    
    if user and user['email_2fa_enabled']:
        conn.close()
        return jsonify({"error": "2FA is already enabled"}), 400
    
    # Generate a verification code to confirm email ownership
    code = email_2fa.generate_code()
    expiry = email_2fa.get_expiry_time().isoformat()
    
    # Store email and verification code temporarily
    cursor.execute("""
        UPDATE users SET email = ?, email_2fa_code = ?, email_2fa_expiry = ? WHERE id = ?
    """, (email, code, expiry, request.user_id))
    conn.commit()
    conn.close()
    
    # Send verification code to email
    email_sent = email_2fa.send_code(email, code, request.username)
    
    return jsonify({
        "message": "Verification code sent to your email",
        "email_hint": email[:3] + "***" + email[email.index('@'):],
        "email_sent": email_sent
    })


@app.route("/api/account/2fa/verify", methods=["POST"])
@jwt_auth.login_required
def verify_2fa_setup():
    """Verify email ownership and enable 2FA"""
    data = request.get_json()
    code = data.get('code', '')
    
    if not code:
        return jsonify({"error": "Verification code required"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT email, email_2fa_code, email_2fa_expiry, email_2fa_enabled FROM users WHERE id = ?
    """, (request.user_id,))
    user = cursor.fetchone()
    
    if not user or not user['email'] or not user['email_2fa_code']:
        conn.close()
        return jsonify({"error": "2FA setup not initiated. Please start setup first."}), 400
    
    if user['email_2fa_enabled']:
        conn.close()
        return jsonify({"error": "2FA is already enabled"}), 400
    
    # Verify the code
    if not email_2fa.verify_code(user['email_2fa_code'], code, user['email_2fa_expiry']):
        conn.close()
        return jsonify({"error": "Invalid or expired verification code"}), 401
    
    # Generate backup codes
    backup_codes = email_2fa.generate_backup_codes()
    backup_codes_hashed = ','.join([generate_password_hash(bc) for bc in backup_codes])
    
    # Enable 2FA
    cursor.execute("""
        UPDATE users SET email_2fa_enabled = 1, email_2fa_code = NULL, 
        email_2fa_expiry = NULL, backup_codes = ? WHERE id = ?
    """, (backup_codes_hashed, request.user_id))
    conn.commit()
    conn.close()
    
    return jsonify({
        "message": "Email 2FA enabled successfully",
        "backupCodes": backup_codes
    })


@app.route("/api/account/2fa/resend", methods=["POST"])
@jwt_auth.login_required
def resend_2fa_code():
    """Resend 2FA verification code during setup"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT email, email_2fa_enabled FROM users WHERE id = ?", (request.user_id,))
    user = cursor.fetchone()
    
    if not user or not user['email']:
        conn.close()
        return jsonify({"error": "No email configured. Start 2FA setup first."}), 400
    
    if user['email_2fa_enabled']:
        conn.close()
        return jsonify({"error": "2FA is already enabled"}), 400
    
    # Generate a new code
    code = email_2fa.generate_code()
    expiry = email_2fa.get_expiry_time().isoformat()
    
    cursor.execute("""
        UPDATE users SET email_2fa_code = ?, email_2fa_expiry = ? WHERE id = ?
    """, (code, expiry, request.user_id))
    conn.commit()
    conn.close()
    
    # Send the code
    email_2fa.send_code(user['email'], code, request.username)
    
    return jsonify({
        "message": "Verification code resent",
        "email_hint": user['email'][:3] + "***" + user['email'][user['email'].index('@'):]
    })


@app.route("/api/account/2fa/disable", methods=["POST"])
@jwt_auth.login_required
def disable_2fa():
    """Disable 2FA (requires current password)"""
    data = request.get_json()
    password = data.get('password', '')
    
    if not password:
        return jsonify({"error": "Password required"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT password_hash, email_2fa_enabled FROM users WHERE id = ?
    """, (request.user_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404
    
    if not check_password_hash(user['password_hash'], password):
        conn.close()
        return jsonify({"error": "Invalid password"}), 401
    
    if not user['email_2fa_enabled']:
        conn.close()
        return jsonify({"error": "2FA is not enabled"}), 400
    
    # Disable 2FA (keep email for account recovery purposes)
    cursor.execute("""
        UPDATE users SET email_2fa_enabled = 0, email_2fa_code = NULL, 
        email_2fa_expiry = NULL, backup_codes = NULL WHERE id = ?
    """, (request.user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "2FA disabled successfully"})


# ============ API ROUTES ============

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat() + 'Z'})


@app.route("/api/messages", methods=["GET"])
def get_messages():
    room = request.args.get("room", "general")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT m.id, m.username, m.content, m.room, m.timestamp, m.user_id, m.encrypted,
                  u.display_name, u.avatar_color, u.name_color, u.avatar_url
           FROM messages m
           LEFT JOIN users u ON m.user_id = u.id
           WHERE m.room = ? ORDER BY m.timestamp DESC LIMIT 50""",
        (room,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    messages = []
    for row in reversed(rows):
        content = row['content']
        # Decrypt message if encrypted
        if row['encrypted']:
            content = message_encryption.decrypt_from_storage(content, room) or '[Encrypted message]'
        
        messages.append({
            'id': row['id'],
            'username': row['username'],
            'displayName': row['display_name'],
            'content': content,
            'room': row['room'],
            'timestamp': row['timestamp'],
            'user_id': row['user_id'],
            'avatarColor': row['avatar_color'],
            'nameColor': row['name_color'],
            'avatarUrl': row['avatar_url']
        })
    
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
@jwt_auth.login_required
def create_room():
    data = request.get_json()
    name = data.get('name', '').strip().lower().replace(' ', '-')
    
    if not name:
        return jsonify({"error": "Room name is required"}), 400
    
    if len(name) < 2 or len(name) > 20:
        return jsonify({"error": "Room name must be 2-20 characters"}), 400
    
    if not all(c.isalnum() or c == '-' for c in name):
        return jsonify({"error": "Room name can only contain letters, numbers, and hyphens"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("INSERT INTO rooms (name, encrypted) VALUES (?, 1)", (name,))
        conn.commit()
        conn.close()
        
        socketio.emit("room_created", {"name": name})
        
        return jsonify({"message": "Room created", "name": name}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Room already exists"}), 409


@app.route("/api/rooms/<name>", methods=["DELETE"])
@jwt_auth.login_required
def delete_room(name):
    if name == 'general':
        return jsonify({"error": "Cannot delete the general room"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM rooms WHERE name = ?", (name,))
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"error": "Room not found"}), 404
    
    cursor.execute("DELETE FROM messages WHERE room = ?", (name,))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Room deleted"})


@app.route("/api/messages/<message_id>", methods=["DELETE"])
@jwt_auth.login_required
def delete_message(message_id):
    conn = get_db()
    cursor = conn.cursor()
    
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
@jwt_auth.login_required
def delete_account():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM messages WHERE user_id = ?", (request.user_id,))
    cursor.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (request.user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (request.user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Account deleted"})


@app.route("/api/account/password", methods=["PUT"])
@jwt_auth.login_required
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
@jwt_auth.login_required
def get_profile():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT username, display_name, avatar_color, name_color, avatar_url, email_2fa_enabled, email 
        FROM users WHERE id = ?
    """, (request.user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({
        "username": user['username'],
        "displayName": user['display_name'],
        "avatarColor": user['avatar_color'],
        "nameColor": user['name_color'],
        "avatarUrl": user['avatar_url'],
        "email2FAEnabled": bool(user['email_2fa_enabled']),
        "email": user['email']
    })


@app.route("/api/account/profile", methods=["PUT"])
@jwt_auth.login_required
def update_profile():
    data = request.get_json()
    avatar_color = data.get('avatarColor')
    name_color = data.get('nameColor')
    display_name = data.get('displayName')
    
    hex_pattern = re.compile(r'^#[0-9A-Fa-f]{6}$')
    
    if avatar_color and not hex_pattern.match(avatar_color):
        return jsonify({"error": "Invalid avatar color format"}), 400
    
    if name_color and not hex_pattern.match(name_color):
        return jsonify({"error": "Invalid name color format"}), 400
    
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
@jwt_auth.login_required
def upload_avatar():
    if request.is_json:
        data = request.get_json()
        image_data = data.get('image')
        
        if not image_data:
            return jsonify({"error": "No image data provided"}), 400
        
        try:
            if ',' in image_data:
                header, encoded = image_data.split(',', 1)
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
            
            image_bytes = base64.b64decode(encoded)
            
            if len(image_bytes) > MAX_CONTENT_LENGTH:
                return jsonify({"error": "Image too large. Maximum size is 2MB"}), 400
            
            filename = f"{request.user_id}_{uuid.uuid4().hex[:8]}.{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT avatar_url FROM users WHERE id = ?", (request.user_id,))
            user = cursor.fetchone()
            if user and user['avatar_url']:
                old_filename = user['avatar_url'].split('/')[-1]
                old_path = os.path.join(UPLOAD_FOLDER, old_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)
            
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
            
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
        if 'avatar' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['avatar']
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400
        
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{request.user_id}_{uuid.uuid4().hex[:8]}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT avatar_url FROM users WHERE id = ?", (request.user_id,))
        user = cursor.fetchone()
        if user and user['avatar_url']:
            old_filename = user['avatar_url'].split('/')[-1]
            old_path = os.path.join(UPLOAD_FOLDER, old_filename)
            if os.path.exists(old_path):
                os.remove(old_path)
        
        file.save(filepath)
        
        avatar_url = f"/api/avatars/{filename}"
        cursor.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_url, request.user_id))
        conn.commit()
        conn.close()
        
        return jsonify({
            "message": "Avatar uploaded successfully",
            "avatarUrl": avatar_url
        })


@app.route("/api/account/avatar", methods=["DELETE"])
@jwt_auth.login_required
def delete_avatar():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT avatar_url FROM users WHERE id = ?", (request.user_id,))
    user = cursor.fetchone()
    
    if user and user['avatar_url']:
        filename = user['avatar_url'].split('/')[-1]
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        
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
    """Authenticate socket connection with JWT token"""
    token = data.get('token', '')
    
    # Support both old format (user_id:username) and new JWT format
    if ':' in token and len(token.split(':')) == 2:
        # Legacy token format
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
    else:
        # JWT token
        payload, error = jwt_auth.verify_access_token(token)
        if payload:
            active_users[request.sid] = {
                "user_id": payload['user_id'],
                "username": payload['username'],
                "room": "general"
            }
            emit("authenticated", {"success": True, "username": payload['username']})
        else:
            emit("authenticated", {"success": False, "error": error or "Invalid token"})


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
@rate_limiter.limit('message')
def handle_message(data):
    user = active_users.get(request.sid)
    if not user:
        emit("error", {"message": "Not authenticated"})
        return
    
    room = data.get("room", "general")
    content = data.get("content", "").strip()
    
    if not content:
        return
    
    # Validate message length
    if len(content) > 2000:
        emit("error", {"message": "Message too long (max 2000 characters)"})
        return
    
    message_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    # Get user's profile data
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT display_name, avatar_color, name_color, avatar_url FROM users WHERE id = ?", (user["user_id"],))
    user_profile = cursor.fetchone()
    
    # Encrypt message for storage
    encrypted_content = message_encryption.encrypt_for_storage(content, room)
    
    # Save to database
    cursor.execute(
        "INSERT INTO messages (id, user_id, username, content, room, timestamp, encrypted) VALUES (?, ?, ?, ?, ?, ?, 1)",
        (message_id, user["user_id"], user["username"], encrypted_content, room, timestamp)
    )
    conn.commit()
    conn.close()
    
    message = {
        "id": message_id,
        "username": user["username"],
        "displayName": user_profile['display_name'] if user_profile else None,
        "content": content,  # Send unencrypted to clients
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
