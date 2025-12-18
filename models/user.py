import mysql.connector
from flask import g
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Hàm lấy kết nối DB (đảm bảo bạn đã có hàm get_db bên models/database.py)
from models.database import get_db

# Class User kế thừa UserMixin để dùng cho Flask-Login
class User(UserMixin):
    def __init__(self, id, username, balance):
        self.id = id
        self.username = username
        self.balance = balance

# Hàm tạo user mới (Có mã hóa mật khẩu)
def create_user(username, password):
    conn = get_db()
    cursor = conn.cursor()
    
    # Mã hóa mật khẩu trước khi lưu
    hashed_password = generate_password_hash(password)
    
    try:
        sql = "INSERT INTO users (username, password, balance) VALUES (%s, %s, %s)"
        # Mặc định balance 0
        cursor.execute(sql, (username, hashed_password, 0))
        conn.commit()
        cursor.close()
        return True
    except mysql.connector.Error as err:
        print("Lỗi tạo user:", err)
        return False

# nạp tiền và ghi lại lịch sử nạp    
def deposit_money(user_id, amount):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 1. Cập nhật số dư cho user (Cộng thêm tiền)
        sql_update = "UPDATE users SET balance = balance + %s WHERE id = %s"
        cursor.execute(sql_update, (amount, user_id))
        
        # 2. Ghi vào lịch sử giao dịch (Bảng transactions)
        # Type là 'deposit', symbol để là 'VND', quantity là 1, price là số tiền nạp
        sql_history = """
            INSERT INTO transactions (user_id, symbol, quantity, price, type) 
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(sql_history, (user_id, 'VND', 1, amount, 'deposit'))
        
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        print(f"Lỗi nạp tiền: {e}")
        conn.rollback() # Hoàn tác nếu lỗi để tránh mất dữ liệu
        return False

# Hàm kiểm tra đăng nhập (So sánh hash)
def verify_user(username, password):
    conn = get_db()
    # dictionary=True giúp lấy dữ liệu dạng {'id': 1, ...} thay vì (1, ...)
    cursor = conn.cursor(dictionary=True) 
    
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()

    if user and check_password_hash(user['password'], password):
        return user # Trả về dictionary thông tin user
    return None

# Hàm lấy user theo ID (Dùng cho @login_manager.user_loader)
def get_user_by_id(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    data = cursor.fetchone()
    cursor.close()
    
    if data:
        # Trả về đối tượng User (Object) chứ không phải dict
        return User(data['id'], data['username'], data['balance'])
    return None