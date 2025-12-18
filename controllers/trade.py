from flask import Blueprint, request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from models.database import get_db
from utils.cafef import get_current_price
from models.user import deposit_money 
from decimal import Decimal

trade_bp = Blueprint("trade", __name__)

#  NẠP TIỀN 
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


# TÍNH NĂNG MUA / BÁN  
@trade_bp.route("/trade", methods=["POST"])
@login_required
def trade():
    symbol = request.form.get("symbol")
    action = request.form.get("action")
    
    # Validate input (số lượng)
    try:
        qty = int(request.form.get("quantity"))
        if qty <= 0: raise ValueError
    except:
        flash("Khối lượng không hợp lệ", "danger")
        return redirect(url_for("market.stock_detail", symbol=symbol))

    #  Lấy giá thị trường
    price_float = get_current_price(symbol)
    if price_float == 0: 
        flash("Lỗi lấy giá thị trường!", "danger")
        return redirect(url_for("market.stock_detail", symbol=symbol))
        
    total_val = float(price_float * qty)  
    user_balance = float(current_user.balance) 
    
    # Kết nối DB
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Kiểm tra thông tin thị trường (Market Data) trước
        cursor.execute("SELECT total_vol FROM market_data WHERE symbol = %s", (symbol,))
        market_info = cursor.fetchone()
        
        # Nếu mã này chưa có trong bảng market_data thì báo lỗi (hoặc coi như vol = 0)
        available_vol = int(market_info['total_vol']) if market_info else 0

        if action == "buy":
            # --- MUA ---
            
            #  Kiểm tra khối lượng thị trường (total_vol)
            if qty > available_vol:
                flash(f"Thị trường chỉ còn {available_vol:,} cổ phiếu. Bạn không thể mua {qty:,}.", "danger")
                return redirect(url_for("market.stock_detail", symbol=symbol))

            # Kiểm tra tiền người dùng
            if user_balance < total_val:
                flash("Bạn không đủ tiền trong tài khoản!", "danger")
                return redirect(url_for("market.stock_detail", symbol=symbol))
            
            # THỰC HIỆN GIAO DỊCH MUA 
            
            #Trừ tiền người dùng
            cursor.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (total_val, current_user.id))
            
            # Trừ khối lượng trên thị trường (market_data)
            cursor.execute("UPDATE market_data SET total_vol = total_vol - %s WHERE symbol = %s", (qty, symbol))
            
            #Cộng cổ phiếu vào Portfolio (Danh mục đầu tư)
            cursor.execute("SELECT * FROM portfolio WHERE user_id = %s AND symbol = %s", (current_user.id, symbol))
            port = cursor.fetchone()
            
            if port:
                current_qty = int(port["quantity"])
                current_avg = float(port["avg_price"])
                new_qty = current_qty + qty
                # Tính giá trung bình mới
                new_avg = ((current_avg * current_qty) + total_val) / new_qty
                
                cursor.execute("UPDATE portfolio SET quantity = %s, avg_price = %s WHERE id = %s", 
                               (new_qty, new_avg, port["id"]))
            else:
                cursor.execute("INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (%s, %s, %s, %s)",
                               (current_user.id, symbol, qty, price_float))
            
            #Lưu lịch sử
            cursor.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type, timestamp) VALUES (%s, %s, %s, %s, 'BUY', NOW())",
                           (current_user.id, symbol, qty, price_float))
            
            conn.commit()
            
            # Cập nhật session hiển thị
            current_user.balance -= Decimal(str(total_val)) 
            flash(f"Mua thành công {qty} {symbol}!", "success")

        elif action == "sell":
            # BÁN 
            cursor.execute("SELECT * FROM portfolio WHERE user_id = %s AND symbol = %s", (current_user.id, symbol))
            port = cursor.fetchone()
            
            if not port or port["quantity"] < qty:
                flash("Bạn không đủ cổ phiếu để bán!", "danger")
                return redirect(url_for("market.stock_detail", symbol=symbol))
            else:
                # Cộng tiền cho user
                cursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (total_val, current_user.id))
                
                # Cộng lại khối lượng vào thị trường (Người này bán thì thị trường có thêm hàng)
                cursor.execute("UPDATE market_data SET total_vol = total_vol + %s WHERE symbol = %s", (qty, symbol))

                #Trừ cổ phiếu trong Portfolio
                new_qty = port["quantity"] - qty
                if new_qty == 0:
                    cursor.execute("DELETE FROM portfolio WHERE id = %s", (port["id"],))
                else:
                    cursor.execute("UPDATE portfolio SET quantity = %s WHERE id = %s", (new_qty, port["id"]))
                
                # Lưu lịch sử
                cursor.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type, timestamp) VALUES (%s, %s, %s, %s, 'SELL', NOW())",
                               (current_user.id, symbol, qty, price_float))
                
                conn.commit()
                current_user.balance += Decimal(str(total_val))
                flash(f"Bán thành công {qty} {symbol}!", "success")

    except Exception as e:
        conn.rollback()
        print(f"Lỗi Trade: {e}") 
        flash(f"Giao dịch thất bại: {e}", "danger")
    finally:
        cursor.close()
        conn.close() 

    return redirect(url_for("market.stock_detail", symbol=symbol))

# DANH MỤC ĐẦU TƯ 
@trade_bp.route("/portfolio")
@login_required
def portfolio():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Lấy danh sách đang sở hữu
    cursor.execute("SELECT * FROM portfolio WHERE user_id = %s AND quantity > 0", (current_user.id,))
    ports = cursor.fetchall()
    cursor.close()

    data = []
    
    # Chuẩn bị dữ liệu vẽ biểu đồ
    chart_labels = []
    chart_values = []
    
    total_asset = float(current_user.balance) 
    
    for p in ports:
        avg_price = float(p["avg_price"]) 
        quantity = int(p["quantity"]) 

        cur_price = get_current_price(p["symbol"])
        if cur_price == 0: 
            cur_price = avg_price 

        market_val = cur_price * quantity
        cost_val = avg_price * quantity
        
        profit = market_val - cost_val
        
        if cost_val > 0:
            percent = (profit / cost_val) * 100
        else:
            percent = 0
        
        total_asset += market_val
        
        # Thêm dữ liệu vào list để vẽ biểu đồ
        chart_labels.append(p["symbol"])
        chart_values.append(market_val)

        data.append({
            "symbol": p["symbol"],
            "quantity": quantity,
            "avg_price": avg_price,
            "current_price": cur_price,
            "profit": profit,
            "percent": percent
        })

    # Thêm phần "Tiền mặt" vào biểu đồ
    chart_labels.append("Tiền mặt")
    chart_values.append(float(current_user.balance))
        
    return render_template("portfolio.html", 
                           portfolio=data, 
                           total_asset=total_asset,
                           chart_labels=chart_labels,
                           chart_values=chart_values) 

# TRANG LỊCH SỬ GIAO DỊCH 
@trade_bp.route("/history")
@login_required
def history():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT * FROM transactions 
        WHERE user_id = %s 
        ORDER BY timestamp DESC
    """, (current_user.id,))
    
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template("history.html", transactions=rows)