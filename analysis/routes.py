from flask import Blueprint, request, jsonify
from models.database import get_db
from utils.auth_helper import token_required
from utils.limiter import limiter
from config import get_gemini_key
import google.generativeai as genai
import json

analysis_bp = Blueprint("analysis", __name__)


@analysis_bp.route("/spending", methods=["POST"])
@token_required
@limiter.limit("5 per minute; 20 per hour")
def analyze_spending(user_id):
    data         = request.get_json()
    month        = data.get("month")
    year         = data.get("year")
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

    # İşlem bazlı gelir yoksa profil gelirini fallback olarak kullan
    if total_income == 0:
        total_income = float(user.get("monthly_income") or 0)

    net          = total_income - total_expense
    savings_rate = ((net / total_income) * 100) if total_income > 0 else 0

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

    budget_text     = ""
    budget_overruns = []
    if budget_plans:
        budget_lines = []
        for bp in budget_plans:
            cat_name  = bp.get("category_name", "")
            limit     = bp.get("monthly_limit", 0)
            actual    = category_breakdown.get(cat_name, {}).get("total", 0)
            usage_pct = (actual / limit * 100) if limit > 0 else 0
            status    = "AŞILDI ⚠️" if actual > limit else "normal ✅"
            if actual > limit:
                budget_overruns.append(cat_name)
            budget_lines.append(
                f"- {cat_name}: Limit {limit:.2f} TL | Harcanan {actual:.2f} TL | %{usage_pct:.0f} kullanım | {status}"
            )
        budget_text = "Bütçe Limiti Karşılaştırması:\n" + "\n".join(budget_lines)
    else:
        budget_text = "Bütçe limiti girilmemiş."

    overrun_count  = len(budget_overruns)
    category_count = len(category_breakdown)

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
- Bütçe Aşılan Kategori Sayısı: {overrun_count}
- Harcama Yapılan Kategori Sayısı: {category_count}

Kategori Bazlı Harcamalar:
{categories_text}

{budget_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FİNANSAL SAĞLIK SKORU HESAPLAMA KURALLARI (0-100):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Aşağıdaki 4 faktörü değerlendirerek 0-100 arası bir skor üret:

1. TASARRUF ORANI (%35 ağırlık):
   - %20+ tasarruf → 35 puan
   - %10-20        → 25 puan
   - %5-10         → 15 puan
   - %0-5          → 8 puan
   - Negatif       → 0 puan

2. BÜTÇE DİSİPLİNİ (%25 ağırlık):
   - Bütçe girilmemiş → 20 puan (nötr)
   - 0 aşım           → 25 puan
   - 1 aşım           → 18 puan
   - 2 aşım           → 10 puan
   - 3+ aşım          → 3 puan

3. GELİR/GİDER DENGESİ (%20 ağırlık):
   - Gider < Gelirin %70'i  → 20 puan
   - Gider < Gelirin %85'i  → 14 puan
   - Gider < Gelirin %95'i  → 8 puan
   - Gider >= Gelir         → 0 puan

4. HARCAMA ÇEŞİTLİLİĞİ (%20 ağırlık):
   - 5+ farklı kategori → 20 puan
   - 3-4 kategori       → 14 puan
   - 1-2 kategori       → 8 puan

Skor etiket ve renk eşlemesi:
- 0-40   → label: "Kritik",   color: "#ef4444"
- 41-65  → label: "Orta",     color: "#f59e0b"
- 66-85  → label: "İyi",      color: "#22c55e"
- 86-100 → label: "Mükemmel", color: "#6366f1"

health_comment: Maksimum 10 kelime. En önemli güçlü veya zayıf noktayı belirt.
Örnekler:
- "Tasarruf oranın harika, bütçe disiplinine dikkat et"
- "Market bütçesini aştın, diğer alanlarda dengeli gidiyorsun"
- "Giderlerin gelirine çok yakın, tasarrufa odaklan"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DİĞER ÖNERİ KURALLARI:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
  "health_score": 0,
  "health_label": "Kritik veya Orta veya İyi veya Mükemmel",
  "health_color": "#hex renk kodu",
  "health_comment": "max 10 kelime açıklama",
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
        genai.configure(api_key=get_gemini_key())
        model    = genai.GenerativeModel("gemini-3-flash-preview")
        response = model.generate_content(prompt)
        text     = response.text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)

        # Güvenlik: health_score 0-100 arasında olmalı
        score = result.get("health_score", 0)
        if not isinstance(score, (int, float)) or not (0 <= score <= 100):
            result["health_score"]   = 0
            result["health_label"]   = "Kritik"
            result["health_color"]   = "#ef4444"
            result["health_comment"] = "Skor hesaplanamadı"

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": f"Analiz yapılamadı: {str(e)}"}), 500
