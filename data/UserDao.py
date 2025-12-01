import bcrypt
from sqlalchemy import create_engine, text

# --- CẤU HÌNH KẾT NỐI ---
# Nhớ thay 123456 bằng mật khẩu của bạn
DB_CONN_STR = 'mysql+pymysql://root:K123456789#@localhost/qlck'
db_engine = create_engine(DB_CONN_STR)

def hash_password(plain_password):
    """Mã hóa mật khẩu"""
    # Chuyển password sang bytes
    password_bytes = plain_password.encode('utf-8')
    # Tạo salt và băm
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    # Trả về dạng string để lưu vào Database
    return hashed.decode('utf-8')

def register_user(username, email, password, phone):
    print(f"\n--- Đang đăng ký cho: {username} ---")
    
    # 1. Mã hóa mật khẩu trước
    hashed_pass = hash_password(password)

    # 2. Kết nối Database
    with db_engine.connect() as conn:
        # Bắt đầu Transaction (Để đảm bảo tạo User xong phải tạo được Wallet)
        trans = conn.begin()
        try:
            # A. Kiểm tra xem Username hoặc Email đã tồn tại chưa
            check_sql = text("SELECT id FROM users WHERE username = :u OR email = :e")
            result = conn.execute(check_sql, {"u": username, "e": email}).fetchone()
            
            if result:
                print("❌ Lỗi: Username hoặc Email đã tồn tại!")
                return False

            # B. Thêm vào bảng USERS
            insert_user_sql = text("""
                INSERT INTO users (username, email, password_hash, phone)
                VALUES (:u, :e, :p, :ph)
            """)
            conn.execute(insert_user_sql, {
                "u": username, 
                "e": email, 
                "p": hashed_pass, # Lưu cái đã mã hóa
                "ph": phone
            })

            # C. Lấy ID của User vừa tạo (để tạo ví)
            # Trong MySQL, dùng hàm LAST_INSERT_ID()
            user_id_result = conn.execute(text("SELECT LAST_INSERT_ID()")).fetchone()
            new_user_id = user_id_result[0]

            # D. Tự động tạo Ví (WALLET) cho user này
            insert_wallet_sql = text("""
                INSERT INTO wallets (user_id, balance, available_balance)
                VALUES (:uid, 0, 0)
            """)
            conn.execute(insert_wallet_sql, {"uid": new_user_id})

            # E. Lưu tất cả thay đổi
            trans.commit()
            print(f"✅ Đăng ký thành công! User ID: {new_user_id}")
            return True

        except Exception as e:
            trans.rollback() # Nếu lỗi thì hủy hết, không lưu gì cả
            print(f"❌ Lỗi hệ thống: {e}")
            return False

# --- CHẠY THỬ ---
if __name__ == "__main__":
    # Giả lập người dùng nhập liệu
    u_name = input("Nhập Username: ")
    u_email = input("Nhập Email: ")
    u_pass = input("Nhập Password: ")
    u_phone = input("Nhập SĐT: ")

    register_user(u_name, u_email, u_pass, u_phone)