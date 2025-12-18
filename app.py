from flask import Flask, redirect, url_for
from flask_login import LoginManager
from models.database import init_db, close_db, get_db 
from models.user import get_user_by_id
from utils.cafef import get_current_price
import time

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

# cập nhật dữ liệu từ DAO
def update_market_data_startup():
    symbols = ["ACB", "BID", "BVH", "CTG", "FPT", "GAS", "HPG", "MBB", "MSN", "MWG", 
               "NVL", "PDR", "PLX", "PNJ", "POW", "SAB", "SSI", "STB", "TCB", "TPB", 
               "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"]
    
    print(" Đang cập nhật dữ liệu thị trường...")
    
    with app.app_context():
        conn = get_db()
        cursor = conn.cursor()
        
        for symbol in symbols:
            try:
                # Lấy giá hiện tại từ API
                price = get_current_price(symbol)
                if price == 0: price = 10000 
                
                # TÍNH TOÁN CÁC CỘT CÒN THIẾU
                ref_price = round(price, -2) 
                
                # Tính trần sàn (Biên độ 7% sàn HOSE)
                ceil_price = ref_price * 1.07
                floor_price = ref_price * 0.93
                
                # Lưu ĐỦ 5 cột quan trọng vào DB
                sql = """
                    INSERT INTO market_data (symbol, price, ref_price, ceil_price, floor_price, total_vol, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    AS new_data 
                    ON DUPLICATE KEY UPDATE 
                    price = new_data.price, 
                    ref_price = new_data.ref_price, 
                    ceil_price = new_data.ceil_price,
                    floor_price = new_data.floor_price, 
                    last_updated = NOW()
                """
                cursor.execute(sql, (symbol, price, ref_price, ceil_price, floor_price, total_vol))
                conn.commit()
                
            except Exception as e:
                print(f"Lỗi {symbol}: {e}")
        
        cursor.close()
        print(" Đã cập nhật xong Database!")

if __name__ == "__main__":
    #gọi hàm cập nhật trước khi lên web
    update_market_data_startup()
    
    #  Server bắt đầu chạy
    print(" Server đang khởi động tại http://127.0.0.1:5000")
    app.run(debug=True, port=5000)