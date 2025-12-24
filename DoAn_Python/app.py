from flask import Flask, redirect, url_for
from flask_login import LoginManager
from models.database import init_db, close_db
from models.user import get_user_by_id

# Import controllers
from controllers.auth import auth_bp
from controllers.market import market_bp
from controllers.trade import trade_bp

app = Flask(__name__)
app.secret_key = "vps_stock_secret_key_2025"

# Cấu hình Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

# Đăng ký đóng DB
app.teardown_appcontext(close_db)

# Đăng ký Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(market_bp)
app.register_blueprint(trade_bp)

@app.route("/")
def index():
    return redirect(url_for("market.market"))

if __name__ == "__main__":
    init_db() # Khởi tạo DB nếu chưa có
    app.run(debug=True, port=5000)