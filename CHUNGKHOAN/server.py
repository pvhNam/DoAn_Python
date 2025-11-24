from flask import Flask, render_template, jsonify
import mysql.connector

app = Flask(__name__)

# --- CẤU HÌNH DATABASE ---
# Đảm bảo giống hệt file reset_all.py bạn vừa chạy
DB_CONFIG = {
    'user': 'python',
    'password': '12345',       
    'host': 'localhost',
    'database': 'python' 
}

def get_latest_prices():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True) # dictionary=True để kết quả có tên cột
        
        # Câu lệnh SQL thông minh: Chỉ lấy dữ liệu của ngày mới nhất (MAX date)
        # Giúp bảng giá luôn hiện dữ liệu hôm nay (hoặc phiên gần nhất)
        sql = """
        SELECT symbol, open, high, low, close, volume, trading_date
        FROM stock_history
        WHERE trading_date = (SELECT MAX(trading_date) FROM stock_history)
        ORDER BY symbol ASC
        """
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        # Xử lý tính toán Tăng/Giảm (Vì trong DB chỉ lưu giá, chưa lưu % thay đổi)
        results = []
        for row in rows:
            price = float(row['close'])
            open_price = float(row['open'])
            
            # Tính toán thay đổi so với giá mở cửa
            change = price - open_price
            percent = (change / open_price * 100) if open_price > 0 else 0
            
            row['change_amount'] = change
            row['change_percent'] = percent
            results.append(row)
            
        cursor.close()
        conn.close()
        return results
    except Exception as e:
        print(f"Lỗi SQL: {e}")
        return []

# --- ROUTE 1: Giao diện Web ---
@app.route('/')
def index():
    return render_template('index.html')

# --- ROUTE 2: API trả dữ liệu cho bảng giá ---
@app.route('/api/latest-prices')
def api_prices():
    data = get_latest_prices()
    return jsonify(data)

if __name__ == '__main__':
    print("Web Server đang chạy tại: http://127.0.0.1:5500")
    app.run(debug=True, port=5000)