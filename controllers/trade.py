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

# --- 2. XỬ LÝ ĐẶT LỆNH (CHỈ P2P - LO) ---
@trade_bp.route("/trade", methods=["POST"])
@login_required
def trade():
    # A. Lấy dữ liệu
    symbol = request.form.get("symbol")
    side = request.form.get("side")          
    # Mặc định luôn là LO (Limit Order)
    order_type = 'LO' 
    
    qty = 0
    price_input = 0

    try:
        qty = int(request.form.get("quantity"))
        price_input = float(request.form.get("price_limit")) # Bắt buộc phải có giá
        
        if qty <= 0 or price_input <= 0: raise ValueError
    except:
        flash("Khối lượng hoặc Giá không hợp lệ!", "danger")
        return redirect(url_for("market.stock_detail", symbol=symbol))

    # Giá khớp chính là giá người dùng nhập (Không quan tâm giá thị trường CafeF nữa)
    my_price = price_input 
    total_val = float(my_price * qty)

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # B. KIỂM TRA SỨC MUA / KHO
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

        # C. KHÓA TÀI SẢN (LOCK ASSETS)
        if side == 'BUY':
             cursor.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (total_val, current_user.id))
        else: # SELL
             new_qty_port = port["quantity"] - qty
             if new_qty_port == 0:
                 cursor.execute("DELETE FROM portfolio WHERE id = %s", (port["id"],))
             else:
                 cursor.execute("UPDATE portfolio SET quantity = %s WHERE id = %s", (new_qty_port, port["id"]))

        # --- D. MATCHING ENGINE (P2P ONLY) ---
        match_found = False
        partner_order = None

        if side == 'BUY':
            # Tôi mua -> Tìm người BÁN giá RẺ HƠN hoặc BẰNG giá tôi đặt
            # Ưu tiên giá RẺ NHẤT
            cursor.execute("""
                SELECT * FROM orders 
                WHERE symbol = %s AND side = 'SELL' AND status = 'PENDING' 
                AND price <= %s AND quantity = %s
                ORDER BY price ASC, created_at ASC LIMIT 1
            """, (symbol, my_price, qty))
            
        elif side == 'SELL':
            # Tôi bán -> Tìm người MUA giá CAO HƠN hoặc BẰNG giá tôi đặt
            # Ưu tiên giá CAO NHẤT
            cursor.execute("""
                SELECT * FROM orders 
                WHERE symbol = %s AND side = 'BUY' AND status = 'PENDING' 
                AND price >= %s AND quantity = %s
                ORDER BY price DESC, created_at ASC LIMIT 1
            """, (symbol, my_price, qty))

        partner_order = cursor.fetchone()

        if partner_order:
            # === CÓ NGƯỜI KHỚP (MATCHED) ===
            match_found = True
            p_id = partner_order['id']
            p_user_id = partner_order['user_id']
            p_price = float(partner_order['price']) # Khớp theo giá người đặt trước (Maker)
            
            # 1. Cập nhật lệnh đối tác
            cursor.execute("UPDATE orders SET status = 'MATCHED' WHERE id = %s", (p_id,))
            
            # 2. Xử lý tài sản đối tác (Partner)
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

            # 3. Lịch sử đối tác
            cursor.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type, timestamp) VALUES (%s, %s, %s, %s, %s, NOW())",
                           (p_user_id, symbol, qty, p_price, partner_order['side']))

            # 4. Xử lý cho TÔI (Taker)
            real_cost = p_price * qty
            diff = total_val - real_cost 

            if side == 'BUY':
                # Tôi mua -> Cộng CP + Hoàn tiền thừa (nếu khớp được giá rẻ hơn giá tôi đặt)
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
                # Tôi bán -> Cộng tiền
                income = p_price * qty
                cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (income, current_user.id))
                current_user.balance += Decimal(str(income))

            # 5. Lưu lệnh của tôi (MATCHED)
            cursor.execute("""
                INSERT INTO orders (user_id, symbol, side, order_type, quantity, price, status) 
                VALUES (%s, %s, %s, %s, %s, %s, 'MATCHED')
            """, (current_user.id, symbol, side, order_type, qty, p_price))

            cursor.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type, timestamp) VALUES (%s, %s, %s, %s, %s, NOW())",
                           (current_user.id, symbol, qty, p_price, side))

            flash(f"Đã khớp lệnh P2P! Giá: {p_price:,.0f}", "success")
        
        else:
            # === KHÔNG CÓ NGƯỜI KHỚP -> TREO LỆNH (PENDING) ===
            # Vì không có MP, nên nếu không khớp P2P thì mặc định là TREO.
            
            flash(f"Lệnh đã được treo (PENDING) trên sổ lệnh!", "info")

            # Lưu lệnh vào Database
            cursor.execute("""
                INSERT INTO orders (user_id, symbol, side, order_type, quantity, price, status) 
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')
            """, (current_user.id, symbol, side, order_type, qty, my_price))

        conn.commit()
        
        # Cập nhật hiển thị tiền trên Header (chỉ cần thiết nếu Buy Pending)
        if side == 'BUY' and not match_found:
             current_user.balance -= Decimal(str(total_val))

    except Exception as e:
        conn.rollback()
        print(f"Trade Error: {e}") 
        flash(f"Lỗi: {e}", "danger")
    finally:
        cursor.close()
        conn.close() 

    return redirect(url_for("market.stock_detail", symbol=symbol))

# --- 3. HỦY LỆNH ---
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

# --- 4. PORTFOLIO & HISTORY ---
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