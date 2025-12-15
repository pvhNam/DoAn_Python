from flask import Blueprint, request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from models.database import get_db
from utils.cafef import get_current_price

trade_bp = Blueprint("trade", __name__)

@trade_bp.route("/trade", methods=["POST"])
@login_required
def trade():
    symbol = request.form["symbol"]
    qty = int(request.form["quantity"])
    action = request.form["action"]
    price = get_current_price(symbol)
    
    if price == 0: price = 10000 # Fallback

    db = get_db()
    total = price * qty

    if action == "buy":
        if current_user.balance < total:
            flash("Số dư không đủ!", "danger")
        else:
            db.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (total, current_user.id))
            
            # Check portfolio
            port = db.execute("SELECT * FROM portfolio WHERE user_id = ? AND symbol = ?", 
                            (current_user.id, symbol)).fetchone()
            if port:
                new_qty = port["quantity"] + qty
                # Tính giá trung bình mới
                new_avg = ((port["quantity"] * port["avg_price"]) + (qty * price)) / new_qty
                db.execute("UPDATE portfolio SET quantity = ?, avg_price = ? WHERE id = ?",
                          (new_qty, new_avg, port["id"]))
            else:
                db.execute("INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (?, ?, ?, ?)",
                          (current_user.id, symbol, qty, price))
            
            db.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type) VALUES (?, ?, ?, ?, ?)",
                      (current_user.id, symbol, qty, price, "BUY"))
            flash(f"Mua thành công {qty:,} cp {symbol} giá {price:,.0f}", "success")

    else:  # sell
        port = db.execute("SELECT * FROM portfolio WHERE user_id = ? AND symbol = ?", 
                         (current_user.id, symbol)).fetchone()
        if not port or port["quantity"] < qty:
            flash("Không đủ cổ phiếu để bán", "danger")
        else:
            db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (total, current_user.id))
            db.execute("UPDATE portfolio SET quantity = quantity - ? WHERE id = ?",
                      (qty, port["id"]))
            db.execute("INSERT INTO transactions (user_id, symbol, quantity, price, type) VALUES (?, ?, ?, ?, ?)",
                      (current_user.id, symbol, qty, price, "SELL"))
            flash(f"Bán thành công {qty:,} cp {symbol} giá {price:,.0f}", "success")

    db.commit()
    return redirect(url_for("market.stock_detail", symbol=symbol))

@trade_bp.route("/portfolio")
@login_required
def portfolio():
    db = get_db()
    ports = db.execute("SELECT * FROM portfolio WHERE user_id = ? AND quantity > 0", (current_user.id,)).fetchall()
    data = []
    total_asset = current_user.balance
    
    for p in ports:
        cur_price = get_current_price(p["symbol"])
        if cur_price == 0: cur_price = p["avg_price"]
        
        market_val = cur_price * p["quantity"]
        profit = market_val - (p["avg_price"] * p["quantity"])
        percent = (profit / (p["avg_price"] * p["quantity"]) * 100) if p["avg_price"] > 0 else 0
        
        total_asset += market_val
        
        data.append({
            "symbol": p["symbol"],
            "quantity": p["quantity"],
            "avg_price": p["avg_price"],
            "current_price": cur_price,
            "profit": profit,
            "percent": percent
        })
        
    return render_template("portfolio.html", portfolio=data, total_asset=total_asset)