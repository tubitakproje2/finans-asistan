from flask import Blueprint, request, jsonify
from models.database import get_db
from utils.auth_helper import create_token, token_required
import bcrypt

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    full_name = data.get("full_name", "").strip()
    password = data.get("password", "")

    if not email or not full_name or not password:
        return jsonify({"error": "Tüm alanlar zorunlu"}), 400
    if len(password) < 6:
        return jsonify({"error": "Şifre en az 6 karakter olmalı"}), 400

    db = get_db()

    existing = db.table("users").select("id").eq("email", email).execute()
    if existing.data:
        return jsonify({"error": "Bu e-posta zaten kayıtlı"}), 409

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    result = db.table("users").insert({
        "email": email,
        "full_name": full_name,
        "password_hash": hashed,
        "monthly_income": 0,
        "risk_profile": "balanced"
    }).execute()

    user = result.data[0]
    token = create_token(user["id"])

    return jsonify({
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "monthly_income": user["monthly_income"],
            "risk_profile": user["risk_profile"]
        }
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "E-posta ve şifre zorunlu"}), 400

    db = get_db()

    result = db.table("users").select("*").eq("email", email).execute()
    if not result.data:
        return jsonify({"error": "Geçersiz e-posta veya şifre"}), 401

    user = result.data[0]

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Geçersiz e-posta veya şifre"}), 401

    token = create_token(user["id"])

    return jsonify({
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "monthly_income": user["monthly_income"],
            "risk_profile": user["risk_profile"]
        }
    }), 200


@auth_bp.route("/logout", methods=["POST"])
@token_required
def logout(user_id):
    return jsonify({"message": "Çıkış yapıldı"}), 200


@auth_bp.route("/profile", methods=["PUT"])
@token_required
def update_profile(user_id):
    data = request.get_json()
    monthly_income = data.get("monthly_income")
    risk_profile = data.get("risk_profile")

    if risk_profile not in ("conservative", "balanced", "aggressive"):
        return jsonify({"error": "Geçersiz risk profili"}), 400

    db = get_db()

    result = db.table("users").update({
        "monthly_income": monthly_income,
        "risk_profile": risk_profile
    }).eq("id", user_id).execute()

    user = result.data[0]

    return jsonify({
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "monthly_income": user["monthly_income"],
            "risk_profile": user["risk_profile"]
        }
    }), 200
