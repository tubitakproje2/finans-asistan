from flask import Blueprint, request, jsonify
from models.database import get_db
from utils.auth_helper import token_required
from config import Config
import google.generativeai as genai
import json

investment_bp = Blueprint("investment", __name__)
genai.configure(api_key=Config.GEMINI_API_KEY)


@investment_bp.route("/recommend", methods=["POST"])
@token_required
def recommend(user_id):
    data  = request.get_json()
    month = data.get("month")
    year  = data.get("year")

    if not month or not year:
        return jsonify({"error": "month ve year zorunlu"}), 400

    db = get_db()

    # Kullanıcı bilgileri
    user_result = db.table("users").select("monthly_income, risk_profile, full_name").eq("id", user_id).execute()
    if not user_result.data:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 404
    user = user_result.data[0]

    # Bu ayın işlemleri
    start_date = f"{year}-{month:02d}-01"
    end_date   = f"{year}-{month + 1:02d}-01" if month < 12 else f"{year + 1}-01-01"

    tx_result = db.table("transactions") \
        .select("*") \
        .eq("user_id", user_id) \
        .gte("transaction_date", start_date) \
        .lt("transaction_date", end_date) \
        .execute()

    transactions = tx_result.data
    if not transactions:
        return jsonify({"error": "Bu ay için işlem bulunamadı"}), 404

    total_income  = sum(t["amount"] for t in transactions if t["transaction_type"] == "INCOME")
    total_expense = sum(t["amount"] for t in transactions if t["transaction_type"] == "EXPENSE")
    net           = total_income - total_expense

    # Kategori bazlı harcama özeti
    category_breakdown = {}
    for t in transactions:
        if t["transaction_type"] == "EXPENSE":
            name = t["category_name"]
            if name not in category_breakdown:
                category_breakdown[name] = {"total": 0, "count": 0, "icon": t["category_icon"]}
            category_breakdown[name]["total"]  += t["amount"]
            category_breakdown[name]["count"]  += 1

    categories_text = "\n".join([
        f"- {name}: {v['total']:.2f} TL ({v['count']} işlem)"
        for name, v in sorted(category_breakdown.items(), key=lambda x: -x[1]["total"])
    ])

    # Tasarruf potansiyeli olan kategoriler (harcamanın %30'undan fazlası)
    saveable = {
        name: v for name, v in category_breakdown.items()
        if v["total"] > total_expense * 0.30
    }

    risk_profile = user.get("risk_profile", "balanced")

    prompt = f"""
Sen bir kişisel finans danışmanısın. Kullanıcının {month}/{year} ayı verilerine göre yatırım önerisi oluştur.

Kullanıcı Bilgileri:
- Aylık Gelir: {user.get('monthly_income', total_income):.2f} TL
- Risk Profili: {risk_profile}

Bu Ay Özeti:
- Toplam Gelir: {total_income:.2f} TL
- Toplam Gider: {total_expense:.2f} TL
- Kalan (Yatırılabilir): {net:.2f} TL

Kategori Bazlı Harcamalar:
{categories_text}

Risk profiline göre yatırım dağılımı rehberi:
- conservative (tutumlu): BIST %20, ETF %30, acil_fon %50
- balanced (dengeli): BIST %50, ETF %40, acil_fon %10
- aggressive (agresif): BIST %70, ETF %25, acil_fon %5

Lütfen SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir şey yazma:
{{
  "investable_amount": {net:.2f},
  "distribution": {{
    "bist_percentage": 50,
    "etf_percentage": 40,
    "emergency_percentage": 10
  }},
  "amounts": {{
    "bist": 0.0,
    "etf": 0.0,
    "emergency": 0.0
  }},
  "yearly_projection": {{
    "year_1": 0.0,
    "year_3": 0.0,
    "year_5": 0.0
  }},
  "savings_opportunities": [
    {{
      "category": "kategori adı",
      "icon": "emoji",
      "current_spending": 0.0,
      "suggested_spending": 0.0,
      "monthly_saving": 0.0,
      "yearly_saving": 0.0,
      "message": "Bu parayı X yatırıma çevirirsen yıllık Y TL kazanabilirsin"
    }}
  ],
  "risk_summary": "Risk profili ve strateji hakkında 2 cümle",
  "ai_comment": "Kullanıcıya özel motivasyon cümlesi"
}}
"""

    try:
        model    = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        text     = response.text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)
        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": f"Öneri oluşturulamadı: {str(e)}"}), 500
