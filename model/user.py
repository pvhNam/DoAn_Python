from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class TransactionType(Enum):
    DEPOSIT = "DEPOSIT"      # Nạp tiền
    WITHDRAWAL = "WITHDRAW"  # Rút tiền
    TRADE_BUY = "TRADE_BUY"  # Trừ tiền mua
    TRADE_SELL = "TRADE_SELL"# Cộng tiền bán
    FEE = "FEE"              # Phí giao dịch

@dataclass
class User:
    """Thông tin định danh người dùng"""
    id: int 
    username: str
    email: str
    password_hash: str   # Mật khẩu đã mã hóa
    phone: str           
    created_at: datetime

@dataclass
class Wallet:
    """Quản lý tiền mặt (Cash) của người dùng"""
    user_id: int 
    currency: str        # VND, USD
    balance: float       # Tổng tài sản (Available + Locked)
    available_balance: float # Tiền khả dụng để mua
    locked_amount: float # Tiền đang bị giam trong các lệnh treo
    updated_at: datetime

@dataclass
class Transaction:
    """Lịch sử biến động số dư tiền"""
    id: str
    wallet_id: int
    amount: float        # Số tiền (+ hoặc -)
    type: TransactionType
    description: str     # Nội dung giao dịch
    created_at: datetime