from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from utils.limiter import limiter

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)
    limiter.init_app(app)

    from auth.routes import auth_bp
    from transactions.routes import transactions_bp
    from analysis.routes import analysis_bp
    from budget.routes import budget_bp
    from investment.routes import investment_bp

    app.register_blueprint(auth_bp,         url_prefix="/auth")
    app.register_blueprint(transactions_bp, url_prefix="/transactions")
    app.register_blueprint(analysis_bp,     url_prefix="/analysis")
    app.register_blueprint(budget_bp,       url_prefix="/budget")
    app.register_blueprint(investment_bp,   url_prefix="/investment")

    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({"error": "Çok fazla istek gönderdiniz. Lütfen bekleyin."}), 429

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=Config.DEBUG)
