from flask import Blueprint, request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from models.database import get_db
from utils.cafef import get_current_price
from models.user import deposit_money 
from decimal import Decimal

trade_bp = Blueprint("trade", __name__)

# NẠP TIỀN
@trade_bp.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    if request.method == 'POST':
        try:
            amount_str = request.form.get('amount', '0').replace(',', '')
            amount = Decimal(amount_str)
            if amount < 10000:
                flash("Số tiền nạp tối thiểu là 10,000 VNĐ", "danger")
            else:
                if deposit_money(current_user.id, amount):
                    flash(f"Nạp thành công {amount:,.0f} VNĐ!", "success")
                    current_user.balance += amount
                    return redirect(url_for('market.market'))
                else:
                    flash("Có lỗi xảy ra, vui lòng thử lại.", "danger")
        except ValueError:
            flash("Số tiền không hợp lệ!", "danger")
    return render_template('deposit.html')

# XỬ LÝ ĐẶT LỆNH 
@trade_bp.route("/trade", methods=["POST"])
@login_required
def trade():
    # Lấy dữ liệu từ Form
    symbol = request.form.get("symbol")
    side = request.form.get("side")          
    order_type = request.form.get("order_type") # Lấy loại lệnh: 'LO' hoặc 'MP'
    
    qty = 0
    price_input = 0

    try:
        qty = int(request.form.get("quantity"))
        
        # Nếu là LO thì bắt buộc phải có giá
        if order_type == 'LO':
            price_input = float(request.form.get("price_limit"))
        
        if qty <= 0: raise ValueError
        if order_type == 'LO' and price_input <= 0: raise ValueError
            
    except:
        flash("Dữ liệu nhập vào không hợp lệ", "danger")
        return redirect(url_for("market.stock_detail", symbol=symbol))

    # Lấy giá thị trường hiện tại (Dùng cho MP)
    market_price = get_current_price(symbol)
    if market_price == 0:
        flash("Lỗi kết nối thị trường!", "danger")
        return redirect(url_for("market.stock_detail", symbol=symbol))

    # Giá đặt lệnh
    if order_type == 'LO':
        my_price = price_input
    else:
        # Nếu là MP (Market Price), giá đặt chính là giá thị trường hiện tại
        my_price = market_price

    total_val = float(my_price * qty)

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # KIỂM TRA SỨC MUA / KHO
        if side == 'BUY':
            if float(current_user.balance) < total_val:
                flash("Số dư không đủ!", "danger")
                return redirect(url_for("market.stock_detail", symbol=symbol))
        else: # SELL
            cursor.execute("SELECT * FROM portfolio WHERE user_id = %s AND symbol = %s", (current_user.id, symbol))
            port = cursor.fetchone()
            
            if not port or port["quantity"] < qty:
                flash("Không đủ cổ phiếu!", "danger")
                return redirect(url_for("market.stock_detail", symbol=symbol))

        # KHÓA TÀI SẢN (LOCK ASSETS)
        if side == 'BUY':
             cursor.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (total_val, current_user.id))
        else: # SELL
             new_qty_port = port["quantity"] - qty
             if new_qty_port == 0:
                 cursor.execute("DELETE FROM portfolio WHERE id = %s", (port["id"],))
             else:
                 cursor.execute("UPDATE portfolio SET quantity = %s WHERE id = %s", (new_qty_port, port["id"]))

        #MATCHING ENGINE 
        match_found = False
        partner_order = None

        # Logic tìm đối tác 
        if side == 'BUY':
            if order_type == 'LO':
                # LO Mua: Tìm người Bán giá <= giá tôi đặt
                cursor.execute("""
                    SELECT * FROM orders 
                    WHERE symbol = %s AND side = 'SELL' AND status = 'PENDING' 
                    AND price <= %s AND quantity = %s
                    ORDER BY price ASC, created_at ASC LIMIT 1
                """, (symbol, my_price, qty))
            else: 
                # MP Mua: Tìm người Bán giá RẺ NHẤT bất kể giá nào (vì tôi chấp nhận giá thị trường)
                # Tuy nhiên để an toàn, thường chỉ khớp trong biên độ trần/sàn, ở đây ta đơn giản hóa là lấy giá tốt nhất
                cursor.execute("""
                    SELECT * FROM orders 
                    WHERE symbol = %s AND side = 'SELL' AND status = 'PENDING' 
                    AND quantity = %s
                    ORDER BY price ASC, created_at ASC LIMIT 1
                """, (symbol, qty))

        elif side == 'SELL':
            if order_type == 'LO':
                # LO Bán: Tìm người Mua giá >= giá tôi đặt
                cursor.execute("""
                    SELECT * FROM orders 
                    WHERE symbol = %s AND side = 'BUY' AND status = 'PENDING' 
                    AND price >= %s AND quantity = %s
                    ORDER BY price DESC, created_at ASC LIMIT 1
                """, (symbol, my_price, qty))
            else:
                # MP Bán: Tìm người Mua giá CAO NHẤT
                cursor.execute("""
                    SELECT * FROM orders 
                    WHERE symbol = %s AND side = 'BUY' AND status = 'PENDING' 
                    AND quantity = %s
                    ORDER BY price DESC, created_at ASC LIMIT 1
                """, (symbol, qty))

        partner_order = cursor.fetchone()

        if partner_order:
            # KHỚP LỆNH (MATCHED)
            match_found = True
            p_id = partner_order['id']
            p_user_id = partner_order['user_id']
            p_price = float(partner_order['price']) # Khớp theo giá Maker
            
            # Cập nhật lệnh đối tác
            cursor.execute("UPDATE orders SET status = 'MATCHED' WHERE id = %s", (p_id,))
            
            # Xử lý tài sản đối tác
            if partner_order['side'] == 'BUY': 
                # Partner Mua -> Cộng CP
                cursor.execute("SELECT * FROM portfolio WHERE user_id = %s AND symbol = %s", (p_user_id, symbol))
                p_port = cursor.fetchone()
                if p_port:
                    pq = int(p_port['quantity'])
                    pavg = float(p_port['avg_price'])
                    pnew_avg = ((pavg * pq) + (p_price * qty)) / (pq + qty)
                    cursor.execute("UPDATE portfolio SET quantity = quantity + %s, avg_price = %s WHERE id = %s", (qty, pnew_avg, p_port['id']))
                else:
                    cursor.execute("INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (%s, %s, %s, %s)", (p_user_id, symbol, qty, p_price))
            else: 
                # Partner Bán -> Cộng tiền
                p_money = p_price * qty
                cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (p_money, p_user_id))

            # Lịch sử đối tác
            cursor.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type, timestamp) VALUES (%s, %s, %s, %s, %s, NOW())",
                           (p_user_id, symbol, qty, p_price, partner_order['side']))

            # Xử lý cho TÔI (Taker)
            real_cost = p_price * qty
            diff = total_val - real_cost 

            if side == 'BUY':
                # Hoàn tiền thừa (nếu khớp giá rẻ hơn dự kiến)
                if diff > 0:
                    cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (diff, current_user.id))
                    current_user.balance += Decimal(str(diff))
                
                # Cộng CP
                cursor.execute("SELECT * FROM portfolio WHERE user_id = %s AND symbol = %s", (current_user.id, symbol))
                my_port = cursor.fetchone()
                if my_port:
                    curr_q = int(my_port["quantity"])
                    curr_avg = float(my_port["avg_price"])
                    new_avg = ((curr_avg * curr_q) + real_cost) / (curr_q + qty)
                    cursor.execute("UPDATE portfolio SET quantity = quantity + %s, avg_price = %s WHERE id = %s", (qty, new_avg, my_port["id"]))
                else:
                    cursor.execute("INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (%s, %s, %s, %s)", (current_user.id, symbol, qty, p_price))
            
            else: # SELL
                # Cộng tiền
                income = p_price * qty
                cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (income, current_user.id))
                current_user.balance += Decimal(str(income))

            # Lưu lệnh của tôi (MATCHED)
            cursor.execute("""
                INSERT INTO orders (user_id, symbol, side, order_type, quantity, price, status) 
                VALUES (%s, %s, %s, %s, %s, %s, 'MATCHED')
            """, (current_user.id, symbol, side, order_type, qty, p_price))

            cursor.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type, timestamp) VALUES (%s, %s, %s, %s, %s, NOW())",
                           (current_user.id, symbol, qty, p_price, side))
            
            # Cập nhật giá thị trường bằng giá vừa khớp
            cursor.execute("UPDATE market_data SET price = %s, last_updated = NOW() WHERE symbol = %s", (p_price, symbol))

            flash(f"Đã khớp lệnh! Giá: {p_price:,.0f}", "success")
        
        else:
            # KHÔNG TÌM THẤY ĐỐI TÁC 
            
            status = 'PENDING'
            execution_price = my_price
            
            # Nếu là lệnh MP -> Khớp ngay với Market Maker (CafeF/Hệ thống)
            if order_type == 'MP':
                status = 'MATCHED'
                execution_price = market_price 
                
                # Xử lý khớp MP với hệ thống
                if side == 'BUY':
                    actual_cost = execution_price * qty
                    diff = total_val - actual_cost
                    if diff > 0:
                        cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (diff, current_user.id))
                        current_user.balance += Decimal(str(diff))
                    
                    cursor.execute("SELECT * FROM portfolio WHERE user_id = %s AND symbol = %s", (current_user.id, symbol))
                    mp = cursor.fetchone()
                    if mp:
                        cq = int(mp['quantity'])
                        ca = float(mp['avg_price'])
                        na = ((ca*cq) + actual_cost)/(cq+qty)
                        cursor.execute("UPDATE portfolio SET quantity = quantity + %s, avg_price = %s WHERE id = %s", (qty, na, mp['id']))
                    else:
                        cursor.execute("INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (%s, %s, %s, %s)", (current_user.id, symbol, qty, execution_price))
                    
                    # Trừ vol hệ thống
                    cursor.execute("UPDATE market_data SET total_vol = total_vol - %s WHERE symbol = %s", (qty, symbol))
                
                else: # SELL
                    inc = execution_price * qty
                    cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (inc, current_user.id))
                    current_user.balance += Decimal(str(inc))
                    cursor.execute("UPDATE market_data SET total_vol = total_vol + %s WHERE symbol = %s", (qty, symbol))

                cursor.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type, timestamp) VALUES (%s, %s, %s, %s, %s, NOW())",
                           (current_user.id, symbol, qty, execution_price, side))
                           
                flash(f"Lệnh MP đã khớp với thị trường! Giá: {execution_price:,.0f}", "success")
            
            else:
                # Nếu là LO -> TREO LỆNH (PENDING)
                flash(f"Lệnh LO giá {my_price:,.0f} đã được treo (PENDING)!", "info")

            # Lưu lệnh vào Database
            cursor.execute("""
                INSERT INTO orders (user_id, symbol, side, order_type, quantity, price, status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (current_user.id, symbol, side, order_type, qty, execution_price, status))

        conn.commit()
        
        # Cập nhật hiển thị tiền trên Header (nếu bị trừ tiền do pending)
        if side == 'BUY' and not match_found and status == 'PENDING':
             current_user.balance -= Decimal(str(total_val))

    except Exception as e:
        conn.rollback()
        print(f"Trade Error: {e}") 
        flash(f"Lỗi: {e}", "danger")
    finally:
        cursor.close()
        conn.close() 

    return redirect(url_for("market.stock_detail", symbol=symbol))

# HỦY LỆNH 
@trade_bp.route("/cancel_order/<int:order_id>", methods=["POST"])
@login_required
def cancel_order(order_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s AND status = 'PENDING'", (order_id, current_user.id))
        order = cursor.fetchone()
        if not order:
            flash("Lỗi hủy lệnh", "danger"); return redirect(request.referrer)
            
        total_val = float(order['price']) * int(order['quantity'])
        if order['side'] == 'BUY':
            cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (total_val, current_user.id))
            current_user.balance += Decimal(str(total_val))
        elif order['side'] == 'SELL':
            cursor.execute("SELECT id FROM portfolio WHERE user_id = %s AND symbol = %s", (current_user.id, order['symbol']))
            port = cursor.fetchone()
            if port: cursor.execute("UPDATE portfolio SET quantity = quantity + %s WHERE id = %s", (order['quantity'], port['id']))
            else: cursor.execute("INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (%s, %s, %s, %s)", (current_user.id, order['symbol'], order['quantity'], 0))
        
        cursor.execute("UPDATE orders SET status = 'CANCELLED' WHERE id = %s", (order_id,))
        conn.commit()
        flash("Đã hủy lệnh!", "success")
    except Exception as e:
        conn.rollback(); print(e); flash("Lỗi hủy", "danger")
    finally:
        cursor.close(); conn.close()
    return redirect(request.referrer)

# TRANG QUẢN LÝ SỔ LỆNH 
@trade_bp.route("/orders")
@login_required
def orders_page():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC", (current_user.id,))
    all_orders = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template("orders.html", orders=all_orders)

# PORTFOLIO 
@trade_bp.route("/portfolio")
@login_required
def portfolio():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM portfolio WHERE user_id = %s AND quantity > 0", (current_user.id,))
    ports = cursor.fetchall(); cursor.close(); conn.close()
    data = []; total_asset = float(current_user.balance); labels=[]; vals=[]
    for p in ports:
        cur = get_current_price(p["symbol"]) or float(p["avg_price"])
        val = cur * p["quantity"]
        total_asset += val
        labels.append(p["symbol"]); vals.append(val)
        data.append({"symbol": p["symbol"], "quantity": p["quantity"], "avg_price": p["avg_price"], "current_price": cur, "profit": val - (float(p["avg_price"])*p["quantity"]), "percent": 0})
    return render_template("portfolio.html", portfolio=data, total_asset=total_asset, chart_labels=labels, chart_values=vals)

# HISTORY 
@trade_bp.route("/history")
@login_required
def history():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM transactions WHERE user_id = %s ORDER BY timestamp DESC", (current_user.id,))
    rows = cursor.fetchall(); cursor.close(); conn.close()
    return render_template("history.html", transactions=rows)
