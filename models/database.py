import mysql.connector
from flask import g

# Cấu hình kết nối MySQL (Phải khớp với thông tin trong Workbench của bạn)
db_config = {
    'user': 'root',           # Hoặc 'stock_admin' nếu bạn đã tạo user riêng
    'password': '123456', # Thay bằng mật khẩu MySQL của bạn
    'host': '127.0.0.1',
    'database': 'python',     # Tên database bạn đã tạo trong Workbench
    'raise_on_warnings': False
}

def get_db():
    if 'db' not in g:
        # Kết nối tới MySQL
        g.db = mysql.connector.connect(**db_config)
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Hàm init_db này không cần thiết phải chạy lệnh tạo bảng nữa 
# vì bạn đã tạo bảng bên MySQL Workbench rồi. 
# Giữ lại hàm này để tránh lỗi import bên app.py thôi.
def init_db():
    try:
        conn = get_db()
        if conn.is_connected():
            print("Kết nối MySQL thành công!")
    except Exception as e:
        print(f"Lỗi kết nối MySQL: {e}")