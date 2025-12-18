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
    
    # Lấy giá hiện tại
    current_price = get_current_price(symbol)
    if current_price == 0:
        current_price = 10000 
    
    # Lấy dữ liệu lịch sử
    history = []
    try:
        ticker = yf.Ticker(f"{symbol}.VN")
        df = ticker.history(period="6mo") 
        for index, row in df.iterrows():
            history.append({
                'date': index.strftime('%Y-%m-%d'),
                'open': row['Open'],
                'high': row['High'],
                'low': row['Low'],
                'close': row['Close'],
                'volume': row['Volume']
            })
    except Exception as e:
        print(f"Lỗi chart: {e}")
        history = []

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
            "total_vol": row['total_vol'],
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