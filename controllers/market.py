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
    symbol = symbol.upper().strip() # Thêm .strip() để xóa khoảng trắng thừa nếu có
    
    current_price = get_current_price(symbol)
    if current_price == 0:
        current_price = 10000 
    
    history = []
    order_book = []  
    
    conn = get_db()
    cursor = None
    
    try:
        if not conn.is_connected():
            conn.ping(reconnect=True, attempts=3, delay=2)
            
        # 1. LẤY LỊCH SỬ GIÁ
        cursor = conn.cursor(dictionary=True) # Mở cursor 1
        cursor.execute("""
            SELECT date, open, high, low, close, volume, percent_change
            FROM stock_history
            WHERE symbol = %s 
            ORDER BY date ASC
        """, (symbol,))
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
        
        # [QUAN TRỌNG] Đóng cursor lịch sử ngay sau khi dùng xong để tránh lỗi xung đột
        cursor.close() 
        cursor = None 

        # 2. LẤY SỔ LỆNH (Đưa ra ngoài if login để ai cũng xem được)
        try:
            # Mở lại kết nối nếu lỡ bị đóng
            if not conn.is_connected(): conn.ping(reconnect=True, attempts=3, delay=2)

            cursor_order = conn.cursor(dictionary=True, buffered=True)
            
            # Lấy 50 lệnh mới nhất (PENDING hoặc MATCHED)
            sql_order = """
                SELECT * FROM orders 
                WHERE symbol = %s 
                AND status IN ('PENDING', 'MATCHED')
                ORDER BY created_at DESC 
                LIMIT 50
            """
            cursor_order.execute(sql_order, (symbol,))
            raw_orders = cursor_order.fetchall()
            
            order_book = [] # Reset lại danh sách
            
            for o in raw_orders:
                # Xử lý thời gian an toàn hơn
                c_at = o.get('created_at')
                time_display = "--:--"
                
                if c_at:
                    try:
                        if hasattr(c_at, 'strftime'):
                            time_display = c_at.strftime('%H:%M')
                        else:
                            # Nếu là chuỗi, cắt chuỗi thủ công
                            s = str(c_at)
                            if len(s) >= 16:
                                time_display = s[11:16]
                            else:
                                time_display = s 
                    except:
                        time_display = "Lỗi giờ"
                
                # Gán lại vào dict
                o['time_str'] = time_display 
                
                # Quan trọng: Đảm bảo các trường số không bị None để tránh lỗi HTML
                o['price'] = float(o['price']) if o['price'] else 0.0
                o['quantity'] = int(o['quantity']) if o['quantity'] else 0
                
                order_book.append(o)
            
            cursor_order.close()
            
            # [DEBUG QUAN TRỌNG] In ra terminal để kiểm tra
            print(f"✅ Đã lấy được {len(order_book)} lệnh cho mã {symbol}")

        except Exception as e_order:
            print(f"⚠️ LỖI LẤY SỔ LỆNH CHI TIẾT: {e_order}")
            order_book = [] # Trả về rỗng nếu lỗi
        
    finally:
        # Đảm bảo đóng kết nối nếu cursor vẫn còn mở (phòng hờ)
        if cursor:
            cursor.close()
    
    return render_template(
        "stock_detail.html",
        symbol=symbol,
        current=current_price,
        history=history,
        order_book=order_book   
    )

# --- 2. DANH SÁCH THỊ TRƯỜNG (BẢNG GIÁ) ---
@market_bp.route("/market")
def market():
    conn = get_db()
    if conn is None:
        return "Lỗi kết nối CSDL", 500
        
    try:
        if not conn.is_connected(): conn.ping(reconnect=True, attempts=3, delay=2)
        cursor = conn.cursor(dictionary=True)

        # [QUAN TRỌNG] Truy vấn kết hợp lấy dữ liệu mới nhất
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
            # 1. XỬ LÝ GIÁ & THAM CHIẾU (An toàn tuyệt đối)
            ref_price = float(row['ref_price']) if row['ref_price'] is not None else 10.0
            
            # Ưu tiên lấy giá live, nếu không thì lấy giá tham chiếu
            if row['live_price'] is not None:
                price = float(row['live_price'])
            else:
                price = ref_price

            # 2. XỬ LÝ PHẦN TRĂM (Fix lỗi mất số 0.0)
            # Logic: Chỉ khi nào là None mới trả về None. Còn 0.0 vẫn giữ nguyên là 0.0
            pct_change = float(row['percent_change']) if row['percent_change'] is not None else 0.0
            
            # 3. XỬ LÝ KHỐI LƯỢNG
            if row['live_vol'] is not None:
                total_vol = int(row['live_vol'])
            else:
                total_vol = random.randint(1000, 50000) * 10

            # Fake data cho giao diện sinh động
            vol_fake = random.randint(10, 500) * 10
            
            stock_data.append({
                "symbol": row['symbol'],
                "price": price,
                "ref": ref_price,
                "ceil": float(row['ceil_price']) if row['ceil_price'] else 0.0,
                "floor": float(row['floor_price']) if row['floor_price'] else 0.0,
                "total_vol": total_vol,
                
                "percent_change": pct_change, # [QUAN TRỌNG] Truyền đúng giá trị đã xử lý
                
                "vol_fake": vol_fake, 
                "buy_price_1": price - 50,
                "buy_vol_1": vol_fake * 2,
            })
            
    except Exception as e:
        print(f"Lỗi Market Route: {e}")
        stock_data = []
    finally:
        if cursor: cursor.close()
        # [QUAN TRỌNG] KHÔNG ĐÓNG CONN
        
    return render_template("market.html", stocks=stock_data)

# --- 3. API AI PREDICT ---
@market_bp.route("/api/predict/<symbol>")
def api_predict(symbol):
    symbol = symbol.upper()
    print(f"\n--- Đang gọi AI Predict cho mã: {symbol} ---") # LOG 1
    
    try:
        # Gọi hàm từ file analysis.py
        data, trend, reason, score = predict_trend(symbol, days_ahead=14)
        
        print(f"✅ AI trả về thành công: Trend={trend}, Score={score}") # LOG 2
        
        return jsonify({
            "symbol": symbol,
            "trend": trend,
            "reason": reason,
            "score": score,
            "data": data 
        })
        
    except Exception as e:
        # ĐÂY LÀ DÒNG QUAN TRỌNG NHẤT: In lỗi ra terminal màu đỏ
        print(f"❌ ❌ ❌ LỖI NGHIÊM TRỌNG KHI GỌI AI ({symbol}): {str(e)}")
        import traceback
        traceback.print_exc() # In chi tiết dòng code bị lỗi
        
        return jsonify({"error": str(e)}), 500