import yfinance as yf
from flask import jsonify, Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user 
from utils.cafef import get_current_price
from utils.analysis import predict_trend
import random
import time
from models.database import get_db

market_bp = Blueprint("market", __name__)

# CHI TIẾT CỔ PHIẾU (ĐÃ MỞ CÔNG KHAI)
@market_bp.route("/market/<symbol>")
def stock_detail(symbol):
    symbol = symbol.upper()
    
    # 1. Lấy giá hiện tại
    current_price = get_current_price(symbol)
    if current_price == 0:
        current_price = 10000 
    
    history = []
    conn = None
    cursor = None
    
    try:
        conn = get_db()
        if conn is None:
            raise Exception("Không thể kết nối Database")

        # --- FIX LỖI CONNECTION NOT AVAILABLE ---
        # Tự động kết nối lại nếu bị ngắt
        if not conn.is_connected():
            conn.ping(reconnect=True, attempts=3, delay=2)

        cursor = conn.cursor(dictionary=True)
        
        # Lấy dữ liệu và sắp xếp theo ngày tăng dần
        sql = """
            SELECT date, open, high, low, close, volume 
            FROM stock_history 
            WHERE symbol = %s 
            ORDER BY date ASC
        """
        cursor.execute(sql, (symbol,))
        rows = cursor.fetchall()

        for row in rows:
            # --- FIX LỖI SAI BIỂU ĐỒ ---
            # 1. Date phải là string 'YYYY-MM-DD'
            # 2. Giá tiền (Decimal) phải ép về float
            history.append({
                'date': str(row['date']), 
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': int(row['volume'])
            })
            
    except Exception as e:
        print(f"Lỗi chart ({symbol}): {e}")
        history = [] # Trả về rỗng để không crash web
        
    finally:
        # Đóng kết nối an toàn
        if cursor:
            cursor.close()

    return render_template(
        "stock_detail.html", 
        symbol=symbol, 
        current=current_price, 
        history=history
    )
# DANH SÁCH THỊ TRƯỜNG
@market_bp.route("/market")
def market():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM market_data")
    db_rows = cursor.fetchall()
    cursor.close()
    
    stock_data = []
    for row in db_rows:
        price = float(row['price'])
        vol_fake = random.randint(10, 500) * 10
        
        stock_data.append({
            "symbol": row['symbol'],
            "price": price,
            "ref": float(row['ref_price']),
            "ceil": float(row['ceil_price']),
            "floor": float(row['floor_price']),
            "total_vol": int(row['total_vol']),  # Đảm bảo int và lấy từ DB (đã liên kết)
            "vol_fake": vol_fake, 
            "buy_price_1": price - 50,
            "buy_vol_1": vol_fake * 2,
        })
        
    return render_template("market.html", stocks=stock_data)

# API AI PREDICT
@market_bp.route("/api/predict/<symbol>")
def api_predict(symbol):
    symbol = symbol.upper()
    try:
        data, trend, reason = predict_trend(symbol, days_ahead=14)
        return jsonify({
            "symbol": symbol,
            "trend": trend,
            "reason": reason,
            "data": data 
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500