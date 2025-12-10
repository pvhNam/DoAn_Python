import os

class Config:
    # Thay đổi 'root' và 'password' thành thông tin MySQL của bạn
# Thay chữ 'password' bằng mật khẩu thật của bạn
    SQLALCHEMY_DATABASE_URI = 'mysql+mysqlconnector://root:123456@localhost/stock_trading_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'secret_key_bao_mat'