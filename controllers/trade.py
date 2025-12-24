from flask import Blueprint, request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from models.database import get_db
from utils.cafef import get_current_price
from models.user import deposit_money 
from decimal import Decimal

trade_bp = Blueprint("trade", __name__)

# --- 1. NẠP TIỀN ---
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

# --- 2. XỬ LÝ ĐẶT LỆNH (THUẦN P2P CHO LO) ---
@trade_bp.route("/trade", methods=["POST"])
@login_required
def trade():
    # A. Lấy dữ liệu
    symbol = request.form.get("symbol")
    side = request.form.get("side")          
    order_type = request.form.get("order_type") 
    qty = 0
    price_input = 0

    try:
        qty = int(request.form.get("quantity"))
        if order_type == 'LO':
            price_input = float(request.form.get("price_limit"))
        if qty <= 0: raise ValueError
    except:
        flash("Dữ liệu nhập vào không hợp lệ", "danger")
        return redirect(url_for("market.stock_detail", symbol=symbol))

    # B. Lấy giá thị trường (chỉ để tham khảo hoặc dùng cho MP)
    market_price = get_current_price(symbol)
    if market_price == 0:
        flash("Lỗi kết nối thị trường!", "danger")
        return redirect(url_for("market.stock_detail", symbol=symbol))

    # Nếu là MP thì lấy giá thị trường, LO thì lấy giá người dùng nhập
    my_price = price_input if order_type == 'LO' else market_price
    total_val = float(my_price * qty)

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # C. KIỂM TRA SỨC MUA / KHO
        if side == 'BUY':
            if float(current_user.balance) < total_val:
                flash("Số dư không đủ!", "danger")
                return redirect(url_for("market.stock_detail", symbol=symbol))
        else: # SELL
            # Dùng SELECT * để lấy ID cho việc xóa sau này
            cursor.execute("SELECT * FROM portfolio WHERE user_id = %s AND symbol = %s", (current_user.id, symbol))
            port = cursor.fetchone()
            
            if not port or port["quantity"] < qty:
                flash("Không đủ cổ phiếu!", "danger")
                return redirect(url_for("market.stock_detail", symbol=symbol))

        # D. KHÓA TÀI SẢN (LOCK ASSETS)
        if side == 'BUY':
             cursor.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (total_val, current_user.id))
        else: # SELL
             new_qty_port = port["quantity"] - qty
             if new_qty_port == 0:
                 cursor.execute("DELETE FROM portfolio WHERE id = %s", (port["id"],))
             else:
                 cursor.execute("UPDATE portfolio SET quantity = %s WHERE id = %s", (new_qty_port, port["id"]))

        # --- E. MATCHING ENGINE (P2P) ---
        match_found = False
        partner_order = None

        if side == 'BUY':
            # Tôi mua -> Tìm người BÁN giá RẺ HƠN hoặc BẰNG giá tôi đặt
            cursor.execute("""
                SELECT * FROM orders 
                WHERE symbol = %s AND side = 'SELL' AND status = 'PENDING' 
                AND price <= %s AND quantity = %s
                ORDER BY price ASC, created_at ASC LIMIT 1
            """, (symbol, my_price, qty))
            
        elif side == 'SELL':
            # Tôi bán -> Tìm người MUA giá CAO HƠN hoặc BẰNG giá tôi đặt
            cursor.execute("""
                SELECT * FROM orders 
                WHERE symbol = %s AND side = 'BUY' AND status = 'PENDING' 
                AND price >= %s AND quantity = %s
                ORDER BY price DESC, created_at ASC LIMIT 1
            """, (symbol, my_price, qty))

        partner_order = cursor.fetchone()

        if partner_order:
            # === 1. CÓ NGƯỜI KHỚP (P2P MATCH) ===
            match_found = True
            p_id = partner_order['id']
            p_user_id = partner_order['user_id']
            p_price = float(partner_order['price']) # Khớp theo giá của người đặt trước (Maker)
            
            # Cập nhật lệnh đối tác
            cursor.execute("UPDATE orders SET status = 'MATCHED' WHERE id = %s", (p_id,))
            
            # Xử lý tài sản đối tác
            if partner_order['side'] == 'BUY': 
                # Đối tác Mua -> Cộng CP
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
                # Đối tác Bán -> Cộng tiền
                p_money = p_price * qty
                cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (p_money, p_user_id))

            # Lịch sử đối tác
            cursor.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type, timestamp) VALUES (%s, %s, %s, %s, %s, NOW())",
                           (p_user_id, symbol, qty, p_price, partner_order['side']))

            # Xử lý cho TÔI (người khớp sau - Taker)
            real_cost = p_price * qty
            diff = total_val - real_cost # Tiền thừa (nếu tôi mua giá cao mà khớp được giá thấp)

            if side == 'BUY':
                # Tôi mua -> Cộng CP + Hoàn tiền thừa
                if diff > 0:
                    cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (diff, current_user.id))
                    current_user.balance += Decimal(str(diff))
                
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
                # Tôi bán -> Cộng tiền (theo giá khớp p_price)
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

            flash(f"Đã khớp lệnh P2P! Giá: {p_price:,.0f}", "success")
        
        else:
            # === 2. KHÔNG CÓ P2P ===
            status = 'PENDING'
            execution_price = my_price
            
            # --- CHỈ KHỚP NGAY NẾU LÀ LỆNH MP (THỊ TRƯỜNG) ---
            # Lệnh LO sẽ LUÔN LUÔN vào trạng thái PENDING nếu không tìm thấy đối tác
            
            if order_type == 'MP':
                status = 'MATCHED'
                execution_price = market_price 
                
                # Logic khớp MP với hệ thống (CafeF) để đảm bảo thanh khoản
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
                # Nếu là LO -> Luôn PENDING (kể cả giá đặt có tốt hơn thị trường ngoài)
                flash(f"Lệnh LO đã được treo (PENDING) chờ người chơi khác!", "info")

            # Lưu lệnh vào Database
            cursor.execute("""
                INSERT INTO orders (user_id, symbol, side, order_type, quantity, price, status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (current_user.id, symbol, side, order_type, qty, execution_price, status))

        conn.commit()
        
        # Cập nhật hiển thị tiền trên Header
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

# --- 3. HỦY LỆNH (GIỮ NGUYÊN) ---
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
# --- 5. TRANG QUẢN LÝ SỔ LỆNH RIÊNG (MỚI) ---
@trade_bp.route("/orders")
@login_required
def orders_page():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Lấy toàn bộ lệnh của user, sắp xếp mới nhất lên đầu
    cursor.execute("""
        SELECT * FROM orders 
        WHERE user_id = %s 
        ORDER BY created_at DESC
    """, (current_user.id,))
    
    all_orders = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template("orders.html", orders=all_orders)
# --- 4. PORTFOLIO & HISTORY (GIỮ NGUYÊN) ---
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

@trade_bp.route("/history")
@login_required
def history():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM transactions WHERE user_id = %s ORDER BY timestamp DESC", (current_user.id,))
    rows = cursor.fetchall(); cursor.close(); conn.close()
    return render_template("history.html", transactions=rows)