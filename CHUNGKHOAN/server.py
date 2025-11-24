from flask import Flask, render_template
import mysql.connector

app = Flask(__name__)

DB_CONFIG = {
    'user': 'python',
    'password': '12345',       
    'host': 'localhost',
    'database': 'python'
}

def get_latest_prices():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        sql = """
        SELECT t1.*
        FROM stock_history t1
        INNER JOIN (
            SELECT symbol, MAX(trading_date) as max_date
            FROM stock_history
            GROUP BY symbol
        ) t2 ON t1.symbol = t2.symbol AND t1.trading_date = t2.max_date
        ORDER BY t1.symbol ASC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        # --- XỬ LÝ FORMAT NGAY TẠI PYTHON (Thay cho JS) ---
        for row in rows:
            op = float(row['open'])
            cl = float(row['close'])
            change = cl - op
            percent = (change / op * 100) if op > 0 else 0
            
            # 1. Định dạng số (thêm dấu phẩy: 28,500.00)
            row['price_str'] = "{:,.2f}".format(cl)
            row['change_str'] = "{:,.2f}".format(change)
            row['percent_str'] = "{:,.2f}%".format(percent)
            row['vol_str'] = "{:,}".format(row['volume'])
            row['high_str'] = "{:,.2f}".format(float(row['high']))
            row['low_str'] = "{:,.2f}".format(float(row['low']))

            # 2. Xử lý màu sắc và mũi tên
            if change > 0:
                row['css_class'] = 'row-up'    # Class màu xanh
                row['arrow'] = '▲'
                row['sign'] = '+'
            elif change < 0:
                row['css_class'] = 'row-down'  # Class màu đỏ
                row['arrow'] = '▼'
                row['sign'] = ''
            else:
                row['css_class'] = 'row-ref'   # Class màu vàng
                row['arrow'] = ''
                row['sign'] = ''
            
        cursor.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"Lỗi SQL: {e}")
        return []

# --- CHỈ CÒN ĐÚNG 1 ROUTE NÀY ---
@app.route('/')
def index():
    # Lấy dữ liệu từ Python
    stock_list = get_latest_prices()
    
    # Truyền biến stock_list sang file HTML để vẽ bảng
    return render_template('index.html', stocks=stock_list)

if __name__ == '__main__':
    print("🚀 Web chạy tại: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)