import hashlib
from flask_login import UserMixin
from .database import get_db

class User(UserMixin):
    def __init__(self, id, username, balance):
        self.id = id
        self.username = username
        self.balance = balance

def hash_pass(p):
    return hashlib.sha256(p.encode()).hexdigest()

def create_user(username, password):
    db = get_db()
    try:
        db.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                   (username, hash_pass(password)))
        db.commit()
        return True
    except:
        return False

def get_user_by_username(username):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        return dict(row)
    return None

def get_user_by_id(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row:
        return User(row["id"], row["username"], row["balance"])
    return None

def verify_user(username, password):
    user_data = get_user_by_username(username)
    if user_data and user_data["password"] == hash_pass(password):
        return user_data
    return None