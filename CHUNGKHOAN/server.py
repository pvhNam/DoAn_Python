from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'khoabaomat' # để dùng session

# cấu hình Database
DB_CONFIG = {
    'user': 'python',
    'password': '12345',       
    'host': 'localhost',
    'database': 'python'
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# lấy giá chứng khoán mới nhất
def get_latest_prices():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = """
        SELECT t1.* FROM stock_history t1
        INNER JOIN (
            SELECT symbol, MAX(trading_date) as max_date
            FROM stock_history GROUP BY symbol
        ) t2 ON t1.symbol = t2.symbol AND t1.trading_date = t2.max_date
        ORDER BY t1.symbol ASC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        for row in rows:
            op= float(row['open'])
            cl= float(row['close'])
            change = cl - op
            percent = (change / op * 100) if op > 0 else 0
            
            row['price_str'] = "{:,.2f}".format(cl)
            row['change_str'] = "{:,.2f}".format(change)
            row['percent_str'] = "{:,.2f}%".format(percent)
            row['vol_str'] = "{:,}".format(row['volume'])
            row['high_str'] = "{:,.2f}".format(float(row['high']))
            row['low_str'] = "{:,.2f}".format(float(row['low']))

            if change > 0:
                row['css_class'], row['arrow'], row['sign'] = 'row-up', '▲', '+'
            elif change < 0:
                row['css_class'], row['arrow'], row['sign'] = 'row-down', '▼', ''
            else:
                row['css_class'], row['arrow'], row['sign'] = 'row-ref', '', ''
            
        cursor.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"Lỗi SQL: {e}")
        return []
# route index
@app.route('/')
def index():
    stock_list = get_latest_prices()
    # thêm session
    username = session.get('username')
    return render_template('index.html', stocks=stock_list, username=username)

# thêm tài sản, danh mục nắm giữ (danh sách chứng khoán mua)
@app.route('/portfolio')
def portfolio():
    # kiểm tra coi đã đăng nhập chưa
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # lấy dữ liệu: mã ck, số lượng, giá vốn và giá thị trường (Close)
    sql = """
        SELECT p.symbol, p.quantity, p.buy_price, 
               h.close as current_price
        FROM user_portfolio p
        LEFT JOIN (
            SELECT symbol, close 
            FROM stock_history 
            WHERE trading_date = (SELECT MAX(trading_date) FROM stock_history)
        ) h ON p.symbol = h.symbol
        WHERE p.user_id = %s
    """
    cursor.execute(sql, (session['user_id'],))
    my_stocks = cursor.fetchall()
    conn.close()
    
    # gọi biến để tính tổng tiền
    total_cost = 0
    total_market_val = 0

    # tính toán và Format
    for s in my_stocks:
        # Nếu chưa có dữ liệu giá (ví dụ mã mới lên sàn chưa chạy tool update)
        if not s['current_price']:
            s['current_price'] = s['buy_price'] # Giả định giá bằng giá mua để không lỗi

        qty = int(s['quantity'])
        buy_price = float(s['buy_price'])
        cur_price = float(s['current_price'])
        
        # Tính toán cơ bản
        cost_val = qty * buy_price*1000          # Tổng vốn bỏ ra
        market_val = qty * cur_price*1000        # Tổng giá trị hiện tại
        profit_val = market_val - cost_val  # Lãi/Lỗ (Số tiền)
        
        # Tính % Lãi lỗ
        if cost_val > 0:
            percent = (profit_val / cost_val) * 100
        else:
            percent = 0
            
        # Cộng dồn tổng
        total_cost += cost_val
        total_market_val += market_val

        # format dữ liệu để hiển thị
        s['quantity_str'] = "{:,}".format(qty)
        s['buy_price_str'] = "{:,.2f}".format(buy_price)
        s['current_price_str'] = "{:,.2f}".format(cur_price)
        s['profit_str'] = "{:,.0f}".format(abs(profit_val)) # Lấy trị tuyệt đối
        s['percent_profit_str'] = "{:,.2f}%".format(abs(percent))
        
        # Xử lý màu sắc và dấu +/-
        if profit_val > 0:
            s['color'] = 'text-up'   # Class màu xanh
            s['sign'] = '+'
        elif profit_val < 0:
            s['color'] = 'text-down' # Class màu đỏ
            s['sign'] = '-'
        else:
            s['color'] = 'text-ref'  # Class màu vàng
            s['sign'] = ''

    # 4. Tính toán tổng kết cuối bảng
    total_profit_val = total_market_val - total_cost
    total_percent_val = (total_profit_val / total_cost * 100) if total_cost > 0 else 0
    
    footer = {
        'total_profit_str': "{:+,.0f}".format(total_profit_val),
        'total_percent_str': "{:+,.2f}%".format(total_percent_val),
        'total_color': 'text-up' if total_profit_val >= 0 else 'text-down'
    }

    return render_template('portfolio.html', 
                           username=session['username'], 
                           stocks=my_stocks, 
                           **footer)

# route mua bán ( trade)
@app.route('/trade/<symbol>', methods=['GET', 'POST'])
def trade_stock(symbol):
    # kiểm tra coi đã đăng nhập chưa
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Lấy giá hiện tại của mã đó để hiển thị
    cursor.execute("""
        SELECT close FROM stock_history 
        WHERE symbol = %s 
        ORDER BY trading_date DESC LIMIT 1
    """, (symbol,))
    row = cursor.fetchone()
    current_price = float(row['close']) if row else 0

    # xử lý nút mua/ bán
    if request.method == 'POST':
        user_id = session['user_id']
        quantity = int(request.form['quantity'])
        trade_price = float(request.form['price'])
        action = request.form['action'] # 'buy' hoặc 'sell'

        try:
            # Kiểm tra xem User đã có mã này trong danh mục chưa
            cursor.execute("SELECT * FROM user_portfolio WHERE user_id = %s AND symbol = %s", (user_id, symbol))
            existing_stock = cursor.fetchone()

            if action == 'buy':
                # tính trung bình giá nếu mua chung 1 cổ nhiều lần
                if existing_stock:
                    old_qty = existing_stock['quantity']
                    old_price = float(existing_stock['buy_price'])
                    
                    new_qty = old_qty + quantity
                    # Công thức giá vốn trung bình: (Giá cũ * SL cũ + Giá mới * SL mới) / Tổng SL
                    avg_price = ((old_qty * old_price) + (quantity * trade_price)) / new_qty
                    
                    sql = "UPDATE user_portfolio SET quantity = %s, buy_price = %s WHERE id = %s"
                    cursor.execute(sql, (new_qty, avg_price, existing_stock['id']))
                else:
                    # Chưa có thì thêm mới
                    sql = "INSERT INTO user_portfolio (user_id, symbol, quantity, buy_price) VALUES (%s, %s, %s, %s)"
                    cursor.execute(sql, (user_id, symbol, quantity, trade_price))
                
                flash(f'Đã MUA {quantity} cổ phiếu {symbol} thành công!', 'success')

            elif action == 'sell':
                # bán
                if existing_stock and existing_stock['quantity'] >= quantity:
                    new_qty = existing_stock['quantity'] - quantity
                    
                    if new_qty > 0:
                        # Bán thì chỉ giảm số lượng, giá vốn giữ nguyên
                        sql = "UPDATE user_portfolio SET quantity = %s WHERE id = %s"
                        cursor.execute(sql, (new_qty, existing_stock['id']))
                    else:
                        # Nếu bán hết sạch thì xóa dòng đó đi
                        sql = "DELETE FROM user_portfolio WHERE id = %s"
                        cursor.execute(sql, (existing_stock['id'],))
                    
                    flash(f'Đã BÁN {quantity} cổ phiếu {symbol} thành công!', 'success')
                else:
                    flash('Lỗi: Bạn không đủ số lượng cổ phiếu để bán!', 'error')

            conn.commit()
            return redirect(url_for('portfolio')) # Mua xong chuyển ngay về trang danh mục

        except Exception as e:
            print(e)
            flash('Giao dịch thất bại!', 'error')

    conn.close()
    
    # Giao diện hiển thị
    return render_template('trade.html', 
                           symbol=symbol, 
                           price_raw=current_price,
                           price_str="{:,.2f}".format(current_price))
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        conn.close()

        # cấu trúc bảng users: id(0), username(1), email(2), password_hash(3)
        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('index'))
        else:
            flash('Sai tên đăng nhập hoặc mật khẩu!')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            sql = "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)"
            cursor.execute(sql, (username, email, hashed_password))
            conn.commit()
            conn.close()
            flash('Đăng ký thành công! Hãy đăng nhập.')
            return redirect(url_for('login'))
        except mysql.connector.Error:
            flash('Tên đăng nhập hoặc Email đã tồn tại!')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)