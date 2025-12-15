import sqlite3
from flask import g
from datetime import datetime

DATABASE = "python"

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def close_db(e=None):
    db = g.pop("_database", None)
    if db is not None:
        db.close()

def init_db():
    with sqlite3.connect(DATABASE) as con:
        cur = con.cursor()
        
        # 1. TẠO BẢNG
        cur.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                balance REAL DEFAULT 1000000000 -- Cấp 1 tỷ cho user mới test cho sướng
            );

            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symbol TEXT,
                quantity INTEGER DEFAULT 0,
                avg_price REAL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symbol TEXT,
                quantity INTEGER,
                price REAL,
                type TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symbol TEXT,
                type TEXT,          -- 'buy' hoặc 'sell'
                quantity INTEGER,   
                filled INTEGER DEFAULT 0, 
                price REAL,         
                status TEXT DEFAULT 'pending', -- 'pending', 'completed', 'cancelled'
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        ''')

        # 2. TẠO TÀI KHOẢN ADMIN (Market Maker)
        # Pass: 123456 (Hash SHA256)
        cur.execute("INSERT OR IGNORE INTO users (id, username, password, balance) VALUES (1, ?, ?, ?)",
                    ("admin", "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92", 999999999999))
        
        # 3. BƠM THANH KHOẢN (SEED DATA)
        # Danh sách mã cổ phiếu phổ biến để tạo thanh khoản ban đầu
        seed_stocks = [
            ("HPG", 28000), ("TCB", 35000), ("SSI", 32000), 
            ("VND", 22000), ("VIC", 45000), ("VHM", 42000), 
            ("FPT", 98000), ("MWG", 48000), ("ACB", 25000), 
            ("STB", 30000), ("MBB", 24000), ("NVL", 16000)
        ]

        print("--- ĐANG KHỞI TẠO THANH KHOẢN CHO SÀN ---")
        for symbol, price in seed_stocks:
            # A. Cấp cho Admin 1.000.000 cổ phiếu mỗi mã vào Portfolio
            # Kiểm tra xem đã có chưa để tránh duplicate khi chạy lại
            check_port = cur.execute("SELECT * FROM portfolio WHERE user_id = 1 AND symbol = ?", (symbol,)).fetchone()
            if not check_port:
                cur.execute("INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (1, ?, 1000000, ?)",
                            (symbol, price))
            
            # B. Tạo lệnh BÁN (Sell Order) treo sẵn trên sàn
            # Admin đặt bán 10.000 cổ phiếu giá gốc để User khác vào mua là khớp ngay
            # Kiểm tra xem đã có lệnh bán pending của admin chưa
            check_order = cur.execute("SELECT * FROM orders WHERE user_id = 1 AND symbol = ? AND type = 'sell' AND status = 'pending'", (symbol,)).fetchone()
            if not check_order:
                cur.execute('''
                    INSERT INTO orders (user_id, symbol, type, quantity, filled, price, status, timestamp) 
                    VALUES (1, ?, 'sell', 50000, 0, ?, 'pending', ?)
                ''', (symbol, price, datetime.now()))
                print(f"✅ Đã tạo lệnh bán mồi: {symbol} - Giá {price}")

        con.commit()