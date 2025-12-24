# trade.py
from flask import Blueprint, request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from models.database import get_db
from utils.cafef import get_current_price
from datetime import datetime

trade_bp = Blueprint("trade", __name__)

# --- 1. HÀM XỬ LÝ KHỚP LỆNH (Matching Engine) ---
def process_matching(db, symbol):
    # Lấy lệnh Mua (Giá cao trước, Thời gian sớm trước)
    buy_orders = db.execute('''
        SELECT * FROM orders 
        WHERE symbol = ? AND type = 'buy' AND status = 'pending'
        ORDER BY price DESC, timestamp ASC
    ''', (symbol,)).fetchall()

    # Lấy lệnh Bán (Giá thấp trước, Thời gian sớm trước)
    sell_orders = db.execute('''
        SELECT * FROM orders 
        WHERE symbol = ? AND type = 'sell' AND status = 'pending'
        ORDER BY price ASC, timestamp ASC
    ''', (symbol,)).fetchall()

    buys = [dict(b) for b in buy_orders]
    sells = [dict(s) for s in sell_orders]
    print(f"--- MATCHING {symbol} ---")
    print(f"Buys: {len(buy_orders)} | Sells: {len(sell_orders)}")

    if len(buy_orders) > 0 and len(sell_orders) > 0:
        best_buy = buy_orders[0]['price']
        best_sell = sell_orders[0]['price']
        print(f"Best Buy: {best_buy} vs Best Sell: {best_sell}")
        
        if best_buy < best_sell:
            print("=> Spread quá lớn, chưa thể khớp.")
    for buy in buys:
        for sell in sells:
            # Nếu lệnh đã khớp xong hoặc hủy thì bỏ qua
            if buy['status'] != 'pending' or sell['status'] != 'pending':
                continue

            # Điều kiện khớp: Giá mua >= Giá bán
            if buy['price'] >= sell['price']:
                match_price = sell['price'] # Khớp theo giá người bán
                
                # Tính số lượng khớp
                rem_buy = buy['quantity'] - buy['filled']
                rem_sell = sell['quantity'] - sell['filled']
                match_qty = min(rem_buy, rem_sell)

                if match_qty > 0:
                    print(f"⚡ KHỚP: {match_qty} {symbol} giá {match_price}")

                    # A. Cập nhật lệnh Mua
                    new_filled_buy = buy['filled'] + match_qty
                    status_buy = 'completed' if new_filled_buy >= buy['quantity'] else 'pending'
                    db.execute("UPDATE orders SET filled = ?, status = ? WHERE id = ?", 
                               (new_filled_buy, status_buy, buy['id']))
                    buy['filled'] = new_filled_buy
                    buy['status'] = status_buy

                    # B. Cập nhật lệnh Bán
                    new_filled_sell = sell['filled'] + match_qty
                    status_sell = 'completed' if new_filled_sell >= sell['quantity'] else 'pending'
                    db.execute("UPDATE orders SET filled = ?, status = ? WHERE id = ?", 
                               (new_filled_sell, status_sell, sell['id']))
                    sell['filled'] = new_filled_sell
                    sell['status'] = status_sell

                    # C. GIAO DỊCH TÀI SẢN
                    # Cộng CP cho người Mua
                    buyer_port = db.execute("SELECT * FROM portfolio WHERE user_id = ? AND symbol = ?", 
                                          (buy['user_id'], symbol)).fetchone()
                    if buyer_port:
                        new_qty = buyer_port['quantity'] + match_qty
                        # Tính lại giá vốn trung bình
                        old_val = buyer_port['quantity'] * buyer_port['avg_price']
                        new_val = old_val + (match_qty * match_price)
                        new_avg = new_val / new_qty
                        db.execute("UPDATE portfolio SET quantity = ?, avg_price = ? WHERE id = ?",
                                   (new_qty, new_avg, buyer_port['id']))
                    else:
                        db.execute("INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (?, ?, ?, ?)",
                                   (buy['user_id'], symbol, match_qty, match_price))
                    
                    # Hoàn tiền thừa cho người Mua (nếu khớp giá thấp hơn giá đặt)
                    excess_cash = (buy['price'] - match_price) * match_qty
                    if excess_cash > 0:
                        db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (excess_cash, buy['user_id']))

                    # Cộng tiền cho người Bán
                    total_money = match_qty * match_price
                    db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (total_money, sell['user_id']))

                    # D. Ghi log Transaction
                    db.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type) VALUES (?, ?, ?, ?, ?)",
                               (buy['user_id'], symbol, match_qty, match_price, "BUY_MATCH"))
                    db.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type) VALUES (?, ?, ?, ?, ?)",
                               (sell['user_id'], symbol, match_qty, match_price, "SELL_MATCH"))

    db.commit()

# --- 2. ROUTE ĐẶT LỆNH ---
@trade_bp.route("/trade", methods=["POST"])
@login_required
def trade():
    symbol = request.form["symbol"]
    try:
        qty = int(request.form["quantity"])
        # LẤY GIÁ TỪ FORM NGƯỜI DÙNG NHẬP
        input_price = float(request.form["price"]) 
    except:
        flash("Dữ liệu nhập vào không hợp lệ", "danger")
        return redirect(url_for("market.stock_detail", symbol=symbol))

    action = request.form["action"]
    
    # Logic cũ: price = get_current_price(symbol) -> XÓA DÒNG NÀY
    price = input_price # Dùng giá người dùng nhập

    db = get_db()
    
    if action == "buy":
        total_cost = price * qty
        if current_user.balance < total_cost:
            flash("Số dư không đủ để đặt lệnh!", "danger")
            return redirect(url_for("market.stock_detail", symbol=symbol))
        
        # Trừ tiền tạm giữ
        db.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (total_cost, current_user.id))
        # Tạo lệnh Mua
        db.execute("INSERT INTO orders (user_id, symbol, type, quantity, filled, price, status) VALUES (?, ?, 'buy', ?, 0, ?, 'pending')",
                   (current_user.id, symbol, qty, price))
        flash(f"Đã đặt MUA {qty} {symbol}. Đang chờ khớp...", "info")

    elif action == "sell":
        port = db.execute("SELECT * FROM portfolio WHERE user_id = ? AND symbol = ?", 
                        (current_user.id, symbol)).fetchone()
        if not port or port['quantity'] < qty:
            flash("Không đủ cổ phiếu để bán!", "danger")
            return redirect(url_for("market.stock_detail", symbol=symbol))

        # Trừ cổ phiếu tạm giữ
        new_qty = port['quantity'] - qty
        if new_qty == 0:
            db.execute("DELETE FROM portfolio WHERE id = ?", (port['id'],))
        else:
            db.execute("UPDATE portfolio SET quantity = ? WHERE id = ?", (new_qty, port['id']))
            
        # Tạo lệnh Bán
        db.execute("INSERT INTO orders (user_id, symbol, type, quantity, filled, price, status) VALUES (?, ?, 'sell', ?, 0, ?, 'pending')",
                   (current_user.id, symbol, qty, price))
        flash(f"Đã đặt BÁN {qty} {symbol}. Đang chờ khớp...", "info")

    db.commit()
    
    # Kích hoạt khớp lệnh ngay sau khi đặt
    process_matching(db, symbol)
    
    return redirect(url_for("market.stock_detail", symbol=symbol))

# --- 3. ROUTE PORTFOLIO (Đã sửa lỗi) ---
@trade_bp.route("/portfolio")
@login_required
def portfolio():
    db = get_db()
    
    # 1. Lấy danh mục sở hữu (Cổ phiếu đã về tài khoản)
    ports = db.execute("SELECT * FROM portfolio WHERE user_id = ? AND quantity > 0", (current_user.id,)).fetchall()
    portfolio_data = []
    total_asset = current_user.balance # Tiền mặt hiện có
    
    for p in ports:
        cur_price = get_current_price(p["symbol"])
        if cur_price == 0: cur_price = p["avg_price"] # Fallback
        
        market_val = cur_price * p["quantity"]
        profit = market_val - (p["avg_price"] * p["quantity"])
        percent = (profit / (p["avg_price"] * p["quantity"]) * 100) if p["avg_price"] > 0 else 0
        
        total_asset += market_val # Cộng giá trị cổ phiếu vào tổng tài sản
        
        portfolio_data.append({
            "symbol": p["symbol"],
            "quantity": p["quantity"],
            "avg_price": p["avg_price"],
            "current_price": cur_price,
            "profit": profit,
            "percent": percent
        })

    # 2. Lấy danh sách LỆNH ĐANG CHỜ (Pending Orders)
    # Để user biết tiền/cổ phiếu của mình đang bị "giam" ở đâu
    pending_orders = db.execute('''
        SELECT * FROM orders 
        WHERE user_id = ? AND status = 'pending' 
        ORDER BY timestamp DESC
    ''', (current_user.id,)).fetchall()

    return render_template("portfolio.html", 
                           portfolio=portfolio_data, 
                           total_asset=total_asset,
                           orders=pending_orders) # Truyền thêm biến orders
# Thêm vào trong trade.py

@trade_bp.route("/cancel_order/<int:order_id>", methods=["POST"])
@login_required
def cancel_order(order_id):
    db = get_db()
    
    # 1. Lấy thông tin lệnh cần hủy (Phải đúng ID và đúng chủ sở hữu)
    order = db.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, current_user.id)).fetchone()

    if not order:
        flash("Không tìm thấy lệnh hoặc bạn không có quyền hủy.", "danger")
        return redirect(url_for("trade.portfolio"))

    if order["status"] != "pending":
        flash("Chỉ có thể hủy lệnh đang chờ khớp!", "warning")
        return redirect(url_for("trade.portfolio"))

    # Tính toán phần còn lại chưa khớp (để hoàn trả)
    remaining_qty = order["quantity"] - order["filled"]
    
    # 2. Xử lý hoàn trả tài sản
    try:
        if order["type"] == "buy":
            # Nếu hủy lệnh MUA -> Trả lại TIỀN
            refund_money = remaining_qty * order["price"]
            db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (refund_money, current_user.id))
            flash(f"Đã hủy lệnh mua. Hoàn lại {refund_money:,.0f} VNĐ", "success")

        elif order["type"] == "sell":
            # Nếu hủy lệnh BÁN -> Trả lại CỔ PHIẾU
            # Kiểm tra xem user đã có record trong portfolio chưa (thường là có rồi mới đặt bán được)
            check_port = db.execute("SELECT * FROM portfolio WHERE user_id = ? AND symbol = ?", (current_user.id, order["symbol"])).fetchone()
            
            if check_port:
                db.execute("UPDATE portfolio SET quantity = quantity + ? WHERE user_id = ? AND symbol = ?", 
                           (remaining_qty, current_user.id, order["symbol"]))
            else:
                # Trường hợp hiếm: nếu record bị xóa, tạo lại (thường không xảy ra)
                db.execute("INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (?, ?, ?, ?)",
                           (current_user.id, order["symbol"], remaining_qty, 0)) # Giá vốn coi như 0 hoặc cần logic phức tạp hơn
            
            flash(f"Đã hủy lệnh bán. Hoàn lại {remaining_qty:,} cổ phiếu {order['symbol']}", "success")

        # 3. Cập nhật trạng thái lệnh thành 'cancelled'
        db.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"Lỗi hủy lệnh: {e}")
        flash("Có lỗi xảy ra khi hủy lệnh.", "danger")

    return redirect(url_for("trade.portfolio"))