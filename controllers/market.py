import yfinance as yf
from flask import jsonify, Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from utils.cafef import get_current_price
from utils.analysis import predict_trend # <--- DÒNG NÀY CHỈ ĐƯỢC Ở ĐÂY
import random
import time
from models.database import get_db

market_bp = Blueprint("market", __name__)

# --- ROUTE 1: CHI TIẾT CỔ PHIẾU ---
@market_bp.route("/market/<symbol>")
@login_required
def stock_detail(symbol):
    symbol = symbol.upper()
    current_price = get_current_price(symbol)
    if current_price == 0: current_price = 10000 
    
    history = []
    try:
        ticker = yf.Ticker(f"{symbol}.VN")
        df = ticker.history(period="6mo") 
        for index, row in df.iterrows():
            history.append({
                'date': index.strftime('%Y-%m-%d'),
                'open': row['Open'], 'high': row['High'], 'low': row['Low'], 'close': row['Close'], 'volume': row['Volume']
            })
    except Exception as e:
        print(f"Lỗi chart: {e}")

    return render_template("stock_detail.html", symbol=symbol, current=current_price, history=history)

# --- ROUTE 2: DANH SÁCH THỊ TRƯỜNG ---
@market_bp.route("/market")
@login_required
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
            "symbol": row['symbol'], "price": price,
            "ref": float(row['ref_price']), "ceil": float(row['ceil_price']), "floor": float(row['floor_price']),
            "total_vol": row['total_vol'], "vol_fake": vol_fake
        })
    return render_template("market.html", stocks=stock_data)

# --- ROUTE 3: API AI PREDICT ---
# --- ROUTE 3: API AI PREDICT ---
@market_bp.route("/api/predict/<symbol>")
@login_required
def api_predict(symbol):
    symbol = symbol.upper()
    
    # --- SỬA DÒNG NÀY (Thêm biến 'reason' vào) ---
    # Cũ (Lỗi): data, trend = predict_trend(...)
    # Mới (Đúng):
    data, trend, reason = predict_trend(symbol, days_ahead=14) 
    
    return jsonify({
        "symbol": symbol,
        "trend": trend,
        "reason": reason, # Nhớ trả về lý do để web hiển thị
        "data": data 
    })