import sqlite3
from flask import g

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
        cur.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                balance REAL DEFAULT 100000000
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
        ''')
        # Tạo tài khoản demo: admin / 123456
        # Hash SHA256 của '123456': 8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92
        cur.execute("INSERT OR IGNORE INTO users (username, password, balance) VALUES (?, ?, ?)",
                    ("admin", "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92", 500000000))
        con.commit()
    print("Database đã sẵn sàng!")