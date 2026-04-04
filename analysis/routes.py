from flask import Blueprint, request, jsonify
from models.database import get_db
from utils.auth_helper import token_required
from config import Config
import google.generativeai as genai
import json

analysis_bp = Blueprint("analysis", __name__)
genai.configure(api_key=Config.GEMINI_API_KEY)


@analysis_bp.route("/spending", methods=["POST"])
@token_required
def analyze_spending(user_id):
    data  = request.get_json()
    month = data.get("month")
    year  = data.get("year")
    budget_plans = data.get("budget_plans", [])

    if not month or not year:
        return jsonify({"error": "month ve year zorunlu"}), 400

    start_date = f"{year}-{month:02d}-01"
    end_date   = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"

    db = get_db()

    transactions_result = db.table("transactions") \
        .select("*") \
        .eq("user_id", user_id) \
        .gte("transaction_date", start_date) \
        .lt("transaction_date", end_date) \
        .execute()

    transactions = transactions_result.data
    if not transactions:
        return jsonify({"error": "Bu ay için işlem bulunamadı"}), 200

    user_result = db.table("users").select("monthly_income, risk_profile").eq("id", user_id).execute()
    user = user_result.data[0] if user_result.data else {}

    total_income  = sum(t["amount"] for t in transactions if t["transaction_type"] == "INCOME")
    total_expense = sum(t["amount"] for t in transactions if t["transaction_type"] == "EXPENSE")
    net           = total_income - total_expense
    savings_rate  = ((net / total_income) * 100) if total_income > 0 else 0

    category_breakdown = {}
    for t in transactions:
        if t["transaction_type"] == "EXPENSE":
            name = t["category_name"]
            if name not in category_breakdown:
                category_breakdown[name] = {
                    "icon": t["category_icon"],
                    "total": 0,
                    "count": 0,
                    "category_id": t.get("category_id")
                }
            category_breakdown[name]["total"] += t["amount"]
            category_breakdown[name]["count"] += 1

    categories_text = "\n".join([
        f"- {name}: {v['total']:.2f} TL ({v['count']} işlem)"
        for name, v in sorted(category_breakdown.items(), key=lambda x: -x[1]["total"])
    ])

    budget_text = ""
    if budget_plans:
        budget_lines = []
        for bp in budget_plans:
            cat_name  = bp.get("category_name", "")
            limit     = bp.get("monthly_limit", 0)
            actual    = category_breakdown.get(cat_name, {}).get("total", 0)
            usage_pct = (actual / limit * 100) if limit > 0 else 0
            status    = "AŞILDI ⚠️" if actual > limit else "normal ✅"
            budget_lines.append(
                f"- {cat_name}: Limit {limit:.2f} TL | Harcanan {actual:.2f} TL | %{usage_pct:.0f} kullanım | {status}"
            )
        budget_text = "Bütçe Limiti Karşılaştırması:\n" + "\n".join(budget_lines)
    else:
        budget_text = "Bütçe limiti girilmemiş."

    prompt = f"""
Sen bir kişisel finans asistanısın. Kullanıcının {month}/{year} ayı harcama verilerini analiz et ve Türkçe yanıt ver.

Kullanıcı Bilgileri:
- Aylık Gelir: {user.get('monthly_income', 0):.2f} TL
- Risk Profili: {user.get('risk_profile', 'balanced')}

Bu Ay Özeti:
- Toplam Gelir: {total_income:.2f} TL
- Toplam Gider: {total_expense:.2f} TL
- Net: {net:.2f} TL
- Tasarruf Oranı: %{savings_rate:.1f}

Kategori Bazlı Harcamalar:
{categories_text}

{budget_text}

Önemli kurallar:
- Bütçe aşımı varsa o kategoriye HIGH öncelikli öneri yaz, somut TL tutarı ver
- "X kategorisinde limitini Y TL aştın, bunu Z'ye düşürürsen yıllık W TL tasarruf edersin" formatında yaz
- Bütçe limitini aşmayan kategoriler için MEDIUM veya LOW öneri ver
- Bütçe girilmemişse genel harcama analizine göre öneri üret

Lütfen SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir şey yazma:
{{
  "summary": "2-3 cümlelik genel değerlendirme, bütçe aşımlarını mutlaka belirt",
  "savings_rate": {savings_rate:.1f},
  "total_income": {total_income},
  "total_expense": {total_expense},
  "net_amount": {net},
  "category_breakdown": [
    {{
      "category_name": "kategori adı",
      "category_icon": "emoji",
      "category_color": "#hex renk",
      "total_amount": 0.0,
      "transaction_count": 0,
      "percentage": 0.0
    }}
  ],
  "recommendations": [
    {{
      "title": "öneri başlığı",
      "description": "somut TL tutarları içeren açıklama",
      "priority": "HIGH veya MEDIUM veya LOW",
      "potential_saving": 0.0
    }}
  ]
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
        return jsonify({"error": f"Analiz yapılamadı: {str(e)}"}), 500
