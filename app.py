from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Import các file cấu hình và database do mình tự tạo
from config import Config
from models import db, User, Portfolio
from utils import get_live_price

app = Flask(__name__)
app.config.from_object(Config)

# 1. Khởi tạo Database và Login Manager
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Nếu chưa đăng nhập thì chuyển hướng về trang login

# Tạo bảng trong Database nếu chưa có (chạy 1 lần đầu)
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------- ROUTES (ĐƯỜNG DẪN) --------------------

@app.route('/')
@login_required  # Bắt buộc đăng nhập mới xem được
def dashboard():
    # Danh sách các mã chứng khoán muốn theo dõi mặc định
    # Bạn có thể thêm bớt mã ở đây
    watchlist = ['HPG', 'VNM', 'FPT', 'VIC', 'MWG', 'ACB']
    
    # Truyền biến user và watchlist sang file HTML
    return render_template('dashboard.html', user=current_user, watchlist=watchlist)

@app.route('/api/price/<symbol>')
def api_price(symbol):
    """
    API nội bộ: Giao diện JS sẽ gọi vào đây.
    Server Python sẽ gọi tiếp sang CafeF để lấy giá về trả lại cho JS.
    """
    data = get_live_price(symbol)
    if data:
        return jsonify(data)
    return jsonify({'error': 'Not found', 'price': 0, 'change': 0}), 404

@app.route('/trade', methods=['POST'])
@login_required
def trade():
    """
    Xử lý logic MUA và BÁN cổ phiếu
    """
    symbol = request.form.get('symbol').upper()
    action = request.form.get('action') # 'buy' hoặc 'sell'
    
    try:
        quantity = int(request.form.get('quantity'))
    except:
        flash('Số lượng phải là số nguyên!', 'danger')
        return redirect(url_for('dashboard'))

    if quantity <= 0:
        flash('Số lượng phải lớn hơn 0!', 'danger')
        return redirect(url_for('dashboard'))

    # 1. Lấy giá hiện tại thị trường để khớp lệnh
    market_data = get_live_price(symbol)
    if not market_data:
        flash(f'Không lấy được giá thị trường của mã {symbol}!', 'danger')
        return redirect(url_for('dashboard'))
    
    current_price = market_data['price']
    total_value = current_price * quantity
    
    # Tìm xem user đã có mã này trong ví chưa
    portfolio_item = Portfolio.query.filter_by(user_id=current_user.id, symbol=symbol).first()

    # --- LOGIC MUA ---
    if action == 'buy':
        if current_user.balance >= total_value:
            # Trừ tiền
            current_user.balance -= total_value
            
            if portfolio_item:
                # Nếu đã có cổ phiếu -> Tính lại giá trung bình (Average Price)
                # Công thức: (Giá trị cũ + Giá trị mua mới) / Tổng số lượng mới
                old_total_value = portfolio_item.quantity * portfolio_item.average_price
                new_total_qty = portfolio_item.quantity + quantity
                portfolio_item.average_price = (old_total_value + total_value) / new_total_qty
                portfolio_item.quantity = new_total_qty
            else:
                # Nếu chưa có -> Tạo mới
                new_item = Portfolio(user_id=current_user.id, symbol=symbol, quantity=quantity, average_price=current_price)
                db.session.add(new_item)
            
            db.session.commit()
            flash(f'Mua thành công {quantity} mã {symbol} giá {current_price:,.0f}', 'success')
        else:
            flash('Số dư không đủ để thực hiện giao dịch!', 'danger')

    # --- LOGIC BÁN ---
    elif action == 'sell':
        if portfolio_item and portfolio_item.quantity >= quantity:
            # Cộng tiền
            current_user.balance += total_value
            
            # Trừ cổ phiếu
            portfolio_item.quantity -= quantity
            
            # Nếu bán hết sạch thì xóa khỏi database
            if portfolio_item.quantity == 0:
                db.session.delete(portfolio_item)
            
            db.session.commit()
            flash(f'Bán thành công {quantity} mã {symbol} giá {current_price:,.0f}', 'success')
        else:
            flash('Không đủ số lượng cổ phiếu để bán!', 'danger')

    return redirect(url_for('dashboard'))

# -------------------- AUTH (ĐĂNG KÝ / ĐĂNG NHẬP) --------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Kiểm tra user tồn tại chưa
        if User.query.filter_by(username=username).first():
            flash('Tên đăng nhập đã tồn tại!', 'danger')
        else:
            # Mã hóa mật khẩu và lưu
            hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
            new_user = User(username=username, password=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
            return redirect(url_for('login'))
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Sai tên đăng nhập hoặc mật khẩu!', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('login'))

# -------------------- CHẠY APP --------------------
if __name__ == '__main__':
    app.run(debug=True)