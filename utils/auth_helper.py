from functools import wraps
from flask import request, jsonify
from jose import jwt, JWTError
from config import Config
from models.database import get_db
from datetime import datetime, timezone, timedelta
import secrets

ACCESS_TOKEN_EXPIRE  = timedelta(days=7)
REFRESH_TOKEN_EXPIRE = timedelta(days=30)

def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + ACCESS_TOKEN_EXPIRE
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")

def create_refresh_token(user_id: str) -> str:
    token = secrets.token_urlsafe(64)
    expires_at = datetime.now(timezone.utc) + REFRESH_TOKEN_EXPIRE
    db = get_db()
    db.table("refresh_tokens").insert({
        "user_id":    user_id,
        "token":      token,
        "expires_at": expires_at.isoformat()
    }).execute()
    return token

def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub")
    except JWTError:
        return None

def verify_refresh_token(token: str) -> str | None:
    db = get_db()
    result = db.table("refresh_tokens").select("*").eq("token", token).execute()
    if not result.data:
        return None
    row = result.data[0]
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        db.table("refresh_tokens").delete().eq("token", token).execute()
        return None
    return row["user_id"]

def revoke_refresh_token(token: str) -> None:
    db = get_db()
    db.table("refresh_tokens").delete().eq("token", token).execute()

def revoke_all_refresh_tokens(user_id: str) -> None:
    db = get_db()
    db.table("refresh_tokens").delete().eq("user_id", user_id).execute()

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
