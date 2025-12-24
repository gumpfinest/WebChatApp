from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
from datetime import datetime

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# In-memory storage (replace with database in production)
users = {}
messages = []
rooms = {"general": []}


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


@app.route("/api/messages", methods=["GET"])
def get_messages():
    room = request.args.get("room", "general")
    room_messages = [msg for msg in messages if msg.get("room") == room]
    return jsonify(room_messages[-50:])  # Return last 50 messages


@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    return jsonify(list(rooms.keys()))


# Socket.IO events
@socketio.on("connect")
def handle_connect():
    print(f"Client connected: {request.sid}")


@socketio.on("disconnect")
def handle_disconnect():
    user = users.pop(request.sid, None)
    if user:
        emit("user_left", {"username": user["username"]}, broadcast=True)
    print(f"Client disconnected: {request.sid}")


@socketio.on("join")
def handle_join(data):
    username = data.get("username", f"User_{request.sid[:6]}")
    room = data.get("room", "general")
    
    users[request.sid] = {"username": username, "room": room}
    join_room(room)
    
    emit("user_joined", {"username": username, "room": room}, room=room)
    emit("room_joined", {"room": room, "username": username})


@socketio.on("leave")
def handle_leave(data):
    room = data.get("room", "general")
    user = users.get(request.sid)
    
    if user:
        leave_room(room)
        emit("user_left", {"username": user["username"], "room": room}, room=room)


@socketio.on("message")
def handle_message(data):
    user = users.get(request.sid, {"username": "Anonymous"})
    room = data.get("room", "general")
    
    message = {
        "id": str(uuid.uuid4()),
        "username": user["username"],
        "content": data.get("content", ""),
        "room": room,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    messages.append(message)
    emit("new_message", message, room=room)


@socketio.on("typing")
def handle_typing(data):
    user = users.get(request.sid, {"username": "Anonymous"})
    room = data.get("room", "general")
    emit("user_typing", {"username": user["username"]}, room=room, include_self=False)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
