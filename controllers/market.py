import yfinance as yf
from flask import jsonify, Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user 
from utils.cafef import get_current_price
from utils.analysis import predict_trend
import random
import time
from models.database import get_db

market_bp = Blueprint("market", __name__)

# --- 1. CHI TIẾT CỔ PHIẾU ---
@market_bp.route("/market/<symbol>")
def stock_detail(symbol):
    symbol = symbol.upper()
    
    current_price = get_current_price(symbol)
    if current_price == 0:
        current_price = 10000 
    
    history = []
    conn = None
    cursor = None
    
    try:
        conn = get_db()
        if conn is None: raise Exception("Không thể kết nối Database")
        if not conn.is_connected(): conn.ping(reconnect=True, attempts=3, delay=2)

        cursor = conn.cursor(dictionary=True)
        
        sql = """
            SELECT date, open, high, low, close, volume, percent_change
            FROM stock_history
            WHERE symbol = %s 
            ORDER BY date ASC
        """
        cursor.execute(sql, (symbol,))
        rows = cursor.fetchall()

        for row in rows:
            history.append({
                'date': str(row['date']), 
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': int(row['volume']),
                'percent_change': float(row['percent_change']) if row.get('percent_change') is not None else 0.0
            })
            
    except Exception as e:
        print(f"Lỗi chart ({symbol}): {e}")
        history = []
        
    finally:
        if cursor: cursor.close()

    return render_template(
        "stock_detail.html", 
        symbol=symbol, 
        current=current_price, 
        history=history
    )

@market_bp.route("/market")
def market():
    conn = get_db()
    if conn is None:
        return "Lỗi kết nối CSDL", 500
        
    try:
        if not conn.is_connected(): conn.ping(reconnect=True, attempts=3, delay=2)
        cursor = conn.cursor(dictionary=True)

        sql = """
            SELECT 
                m.symbol, 
                m.ref_price, 
                m.ceil_price, 
                m.floor_price,
                
                -- Lấy giá đóng cửa mới nhất
                (SELECT close FROM stock_history_1d WHERE symbol = m.symbol ORDER BY date DESC LIMIT 1) as live_price,
                
                -- Lấy tổng khối lượng mới nhất
                (SELECT volume FROM stock_history_1d WHERE symbol = m.symbol ORDER BY date DESC LIMIT 1) as live_vol,
                
                -- [MỚI] Lấy phần trăm thay đổi mới nhất
                (SELECT percent_change FROM stock_history_1d WHERE symbol = m.symbol ORDER BY date DESC LIMIT 1) as percent_change
                
            FROM market_data m
        """
        cursor.execute(sql)
        db_rows = cursor.fetchall()
        
        stock_data = []
        for row in db_rows:
            ref_price = float(row['ref_price']) if row['ref_price'] is not None else 10.0
            
            if row['live_price'] is not None:
                price = float(row['live_price'])
            else:
                price = ref_price

            pct_change = float(row['percent_change']) if row['percent_change'] is not None else 0.0
            
            if row['live_vol'] is not None:
                total_vol = int(row['live_vol'])
            else:
                total_vol = random.randint(1000, 50000) * 10

            vol_fake = random.randint(10, 500) * 10
            
            stock_data.append({
                "symbol": row['symbol'],
                "price": price,
                "ref": ref_price,
                "ceil": float(row['ceil_price']) if row['ceil_price'] else 0.0,
                "floor": float(row['floor_price']) if row['floor_price'] else 0.0,
                "total_vol": total_vol,
                
                "percent_change": pct_change, 
                
                "vol_fake": vol_fake, 
                "buy_price_1": price - 50,
                "buy_vol_1": vol_fake * 2,
            })
            
    except Exception as e:
        print(f"Lỗi Market Route: {e}")
        stock_data = []
    finally:
        if cursor: cursor.close()
        
    return render_template("market.html", stocks=stock_data)

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