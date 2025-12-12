from flask import Blueprint, render_template
from flask_login import login_required
from utils.cafef import get_current_price
import random
import time

market_bp = Blueprint("market", __name__)

# Danh sách các mã Bluechip
STOCKS_LIST = ["ACB", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "MBB", "MSN", "MWG", "NVL", "PDR", "PLX", "PNJ", "POW", "SAB", "SSI", "STB", "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"]

@market_bp.route("/market")
@login_required
def market():
    stock_data = []
    print("--- Loading Bảng Giá Pro ---")
    
    # Lấy 10 mã đầu để demo cho nhanh (muốn full thì bỏ [:10])
    for symbol in STOCKS_LIST[:15]: 
        current_price = get_current_price(symbol)
        
        # Nếu lỗi mạng hoặc API trả về 0, dùng giá mặc định fake để bảng không bị trắng
        if current_price == 0: 
            current_price = 20000 
        
        # LOGIC TÍNH TOÁN GIẢ LẬP ĐỂ HIỂN THỊ ĐỦ CỘT
        # 1. Giá tham chiếu (Giả sử bằng giá hiện tại làm tròn)
        ref_price = round(current_price, -2) 
        
        # 2. Tính Trần (Ceil) +7%, Sàn (Floor) -7% (Luật sàn HOSE)
        ceil_price = ref_price * 1.07
        floor_price = ref_price * 0.93
        
        # 3. Random khối lượng giả để bảng trông sinh động
        vol_fake = random.randint(10, 500) * 10 
        total_vol = random.randint(100000, 5000000)

        # Đưa hết vào object để đẩy sang HTML
        stock_data.append({
            "symbol": symbol,
            "price": current_price,
            "ref": ref_price,
            "ceil": ceil_price,
            "floor": floor_price,
            "vol_fake": vol_fake,
            "total_vol": total_vol
        })
        
        # Nghỉ xíu cho đỡ bị chặn
        time.sleep(0.02)

    return render_template("market.html", stocks=stock_data)

# ... Giữ nguyên hàm stock_detail cũ ...
@market_bp.route("/stock/<symbol>")
@login_required
def stock_detail(symbol):
    from utils.cafef import get_price_history # Import ở đây tránh vòng lặp
    history = get_price_history(symbol, 365)
    current = get_current_price(symbol)
    return render_template("stock_detail.html", symbol=symbol, history=history, current=current)