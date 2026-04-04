from flask import Blueprint, request, jsonify
from models.database import get_db
from utils.auth_helper import token_required
from datetime import datetime
import uuid

budget_bp = Blueprint("budget", __name__)


@budget_bp.route("", methods=["GET"])
@token_required
def get_budget_plans(user_id):
    month = request.args.get("month", type=int)
    year  = request.args.get("year",  type=int)

    if not month or not year:
        return jsonify({"error": "month ve year zorunlu"}), 400

    db = get_db()
    result = db.table("budget_plans") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("month", month) \
        .eq("year", year) \
        .execute()

    return jsonify({"budget_plans": result.data}), 200


@budget_bp.route("", methods=["POST"])
@token_required
def add_budget_plan(user_id):
    data = request.get_json()

    category_id    = data.get("category_id")
    category_name  = data.get("category_name", "")
    category_icon  = data.get("category_icon", "")
    category_color = data.get("category_color", "")
    monthly_limit  = data.get("monthly_limit")
    month          = data.get("month")
    year           = data.get("year")

    if not all([category_id, monthly_limit, month, year]):
        return jsonify({"error": "Zorunlu alanlar eksik"}), 400

    if monthly_limit <= 0:
        return jsonify({"error": "Limit sıfırdan büyük olmalı"}), 400

    db = get_db()

    # Aynı kategori + ay + yıl için zaten plan var mı?
    existing = db.table("budget_plans") \
        .select("id") \
        .eq("user_id", user_id) \
        .eq("category_id", category_id) \
        .eq("month", month) \
        .eq("year", year) \
        .execute()

    if existing.data:
        return jsonify({"error": "Bu kategori için zaten bütçe planı var"}), 409

    result = db.table("budget_plans").insert({
        "id":             str(uuid.uuid4()),
        "user_id":        user_id,
        "category_id":    category_id,
        "category_name":  category_name,
        "category_icon":  category_icon,
        "category_color": category_color,
        "monthly_limit":  monthly_limit,
        "month":          month,
        "year":           year
    }).execute()

    return jsonify({"budget_plan": result.data[0]}), 201


@budget_bp.route("/<plan_id>", methods=["DELETE"])
@token_required
def delete_budget_plan(user_id, plan_id):
    db = get_db()

    existing = db.table("budget_plans") \
        .select("id") \
        .eq("id", plan_id) \
        .eq("user_id", user_id) \
        .execute()

    if not existing.data:
        return jsonify({"error": "Plan bulunamadı"}), 404

    db.table("budget_plans").delete().eq("id", plan_id).execute()

    return jsonify({"message": "Plan silindi"}), 200


@budget_bp.route("/sync", methods=["POST"])
@token_required
def sync_budget_plans(user_id):
    """Android'deki Room'daki planları backend'e push eder."""
    data  = request.get_json()
    plans = data.get("budget_plans", [])

    if not plans:
        return jsonify({"synced": 0}), 200

    db     = get_db()
    synced = 0

    for p in plans:
        existing = db.table("budget_plans") \
            .select("id") \
            .eq("id", p.get("id")) \
            .execute()

        if not existing.data:
            db.table("budget_plans").insert({
                "id":             p.get("id"),
                "user_id":        user_id,
                "category_id":    p.get("category_id"),
                "category_name":  p.get("category_name", ""),
                "category_icon":  p.get("category_icon", ""),
                "category_color": p.get("category_color", ""),
                "monthly_limit":  p.get("monthly_limit"),
                "month":          p.get("month"),
                "year":           p.get("year")
            }).execute()
            synced += 1

    return jsonify({"synced": synced}), 200
