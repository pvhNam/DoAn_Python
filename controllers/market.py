# controllers/market.py

import yfinance as yf
from flask import jsonify, Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user 
from utils.cafef import get_current_price
from utils.analysis import predict_trend
import random
import time
from models.database import get_db
import base64
from utils.gemini_analysis import analyze_chart_image
import tempfile
import os

market_bp = Blueprint("market", __name__)

# CHI TIẾT CỔ PHIẾU (ĐÃ MỞ CÔNG KHAI)
@market_bp.route("/market/<symbol>")
def stock_detail(symbol):
    symbol = symbol.upper()
    
    # 1. Lấy giá hiện tại (vẫn dùng giá thực tế từ Cafef - chưa điều chỉnh)
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

        # Tự động reconnect nếu kết nối bị ngắt
        if not conn.is_connected():
            conn.ping(reconnect=True, attempts=3, delay=2)

        cursor = conn.cursor(dictionary=True)
        
        # Query thêm adjusted_close để tính giá điều chỉnh
        sql = """
            SELECT date, open, high, low, close, volume, adjusted_close 
            FROM stock_history 
            WHERE symbol = %s 
            ORDER BY date ASC
        """
        cursor.execute(sql, (symbol,))
        rows = cursor.fetchall()

        for row in rows:
            close_raw = float(row['close'])
            adj_close = float(row['adjusted_close'])
            
            # Tính tỷ lệ điều chỉnh, tránh chia cho 0
            if close_raw == 0:
                ratio = 1.0
            else:
                ratio = adj_close / close_raw
            
            # Áp dụng điều chỉnh cho open, high, low
            # Close dùng trực tiếp adjusted_close để chính xác tuyệt đối
            history.append({
                'date': str(row['date']), 
                'open': float(row['open']) * ratio,
                'high': float(row['high']) * ratio,
                'low': float(row['low']) * ratio,
                'close': adj_close,  # Giá đóng cửa đã điều chỉnh
                'volume': int(row['volume'])
            })
            
    except Exception as e:
        print(f"Lỗi chart ({symbol}): {e}")
        history = []  # Trả về rỗng để tránh crash web
        
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return render_template(
        "stock_detail.html", 
        symbol=symbol, 
        current=current_price,   # Giá hiện tại vẫn là giá thực (chưa điều chỉnh) - phù hợp với giao dịch thực tế
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
        vol_fake = random.randint(10, 500) * 10  # Dùng để hiển thị bảng khớp lệnh giả lập
        
        stock_data.append({
            "symbol": row['symbol'],
            "price": price,
            "ref": float(row['ref_price']),
            "ceil": float(row['ceil_price']),
            "floor": float(row['floor_price']),
            "total_vol": int(row['total_vol']),  # Lấy volume thực từ ngày gần nhất
            "vol_fake": vol_fake, 
            "buy_price_1": price - 50,
            "buy_vol_1": vol_fake * 2,
        })
        
    return render_template("market.html", stocks=stock_data)


# API AI PREDICT (giữ nguyên - vì analysis.py dùng yfinance nên đã tự động adjusted)
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
@market_bp.route("/api/gemini/<symbol>", methods=["POST"])
def api_gemini(symbol):
    try:
        data = request.get_json()
        image_data_url = data.get("image")

        if not image_data_url:
            return jsonify({"error": "Không nhận được ảnh"}), 400

        # Loại bỏ header data:url
        header, encoded = image_data_url.split(",", 1)
        image_data = base64.b64decode(encoded)

        # Lưu tạm file ảnh
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            tmp_file.write(image_data)
            tmp_path = tmp_file.name

        # Gọi Gemini phân tích
        analysis = analyze_chart_image(tmp_path, symbol.upper())

        # Xóa file tạm
        os.unlink(tmp_path)

        return jsonify({"analysis": analysis})

    except Exception as e:
        print(f"Lỗi API Gemini: {e}")
        return jsonify({"error": "Lỗi xử lý ảnh hoặc gọi Gemini"}), 500