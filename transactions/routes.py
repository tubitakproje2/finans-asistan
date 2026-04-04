from flask import Blueprint, request, jsonify
from models.database import get_db
from utils.auth_helper import token_required
from datetime import datetime

transactions_bp = Blueprint("transactions", __name__)

@transactions_bp.route("", methods=["POST"])
@token_required
def add_transaction(user_id):
    data = request.get_json()

    category_id      = data.get("category_id")
    category_name    = data.get("category_name", "")
    category_icon    = data.get("category_icon", "")
    category_color   = data.get("category_color", "")
    amount           = data.get("amount")
    description      = data.get("description", "")
    transaction_date = data.get("transaction_date")
    transaction_type = data.get("transaction_type")
    payment_method   = data.get("payment_method", "bank_card")

    if not all([category_id, amount, transaction_date, transaction_type]):
        return jsonify({"error": "Zorunlu alanlar eksik"}), 400

    if transaction_type not in ("INCOME", "EXPENSE"):
        return jsonify({"error": "Geçersiz işlem tipi"}), 400

    if amount <= 0:
        return jsonify({"error": "Tutar sıfırdan büyük olmalı"}), 400

    db = get_db()

    result = db.table("transactions").insert({
        "user_id":          user_id,
        "category_id":      category_id,
        "category_name":    category_name,
        "category_icon":    category_icon,
        "category_color":   category_color,
        "amount":           amount,
        "description":      description,
        "transaction_date": transaction_date,
        "transaction_type": transaction_type,
        "payment_method":   payment_method
    }).execute()

    return jsonify({"transaction": result.data[0]}), 201


@transactions_bp.route("", methods=["GET"])
@token_required
def get_transactions(user_id):
    month = request.args.get("month", type=int)
    year  = request.args.get("year", type=int)

    if not month or not year:
        return jsonify({"error": "month ve year zorunlu"}), 400

    start_date = f"{year}-{month:02d}-01"
    end_date   = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"

    db = get_db()

    result = db.table("transactions") \
        .select("*") \
        .eq("user_id", user_id) \
        .gte("transaction_date", start_date) \
        .lt("transaction_date", end_date) \
        .order("transaction_date", desc=True) \
        .execute()

    transactions  = result.data
    total_income  = sum(t["amount"] for t in transactions if t["transaction_type"] == "INCOME")
    total_expense = sum(t["amount"] for t in transactions if t["transaction_type"] == "EXPENSE")

    return jsonify({
        "transactions":  transactions,
        "total_income":  total_income,
        "total_expense": total_expense
    }), 200


@transactions_bp.route("/<transaction_id>", methods=["DELETE"])
@token_required
def delete_transaction(user_id, transaction_id):
    db = get_db()

    existing = db.table("transactions") \
        .select("id") \
        .eq("id", transaction_id) \
        .eq("user_id", user_id) \
        .execute()

    if not existing.data:
        return jsonify({"error": "İşlem bulunamadı"}), 404

    db.table("transactions").delete().eq("id", transaction_id).execute()

    return jsonify({"message": "İşlem silindi"}), 200


@transactions_bp.route("/sync", methods=["POST"])
@token_required
def sync_transactions(user_id):
    data               = request.get_json()
    local_transactions = data.get("transactions", [])

    if not local_transactions:
        return jsonify({"synced": 0}), 200

    db     = get_db()
    synced = 0

    for t in local_transactions:
        existing = db.table("transactions") \
            .select("id") \
            .eq("id", t.get("id")) \
            .execute()

        if not existing.data:
            db.table("transactions").insert({
                "id":               t.get("id"),
                "user_id":          user_id,
                "category_id":      t.get("category_id"),
                "category_name":    t.get("category_name", ""),
                "category_icon":    t.get("category_icon", ""),
                "category_color":   t.get("category_color", ""),
                "amount":           t.get("amount"),
                "description":      t.get("description", ""),
                "transaction_date": t.get("transaction_date"),
                "transaction_type": t.get("transaction_type"),
                "payment_method":   t.get("payment_method", "bank_card")
            }).execute()
            synced += 1

    return jsonify({"synced": synced}), 200
