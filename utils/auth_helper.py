from functools import wraps
from flask import request, jsonify
from jose import jwt, JWTError
from config import Config
from models.database import get_db
from datetime import datetime, timezone, timedelta

def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")

def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub")
    except JWTError:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Token eksik"}), 401
        token = auth_header.split(" ")[1]
        user_id = decode_token(token)
        if not user_id:
            return jsonify({"error": "Geçersiz token"}), 401
        return f(user_id, *args, **kwargs)
    return decorated
