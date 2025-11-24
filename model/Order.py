from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class OrderType(Enum):
    MARKET = "MARKET"    # Lệnh thị trường (MP)
    LIMIT = "LIMIT"      # Lệnh giới hạn (LO)

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    PENDING = "PENDING"  # Chờ khớp
    PARTIALLY_FILLED = "PARTIALLY_FILLED" # Khớp 1 phần
    FILLED = "FILLED"    # Đã khớp hết
    CANCELLED = "CANCELLED" # Đã hủy
    REJECTED = "REJECTED"   # Bị từ chối (do hết tiền, lỗi sàn...)

@dataclass
class Order:
    """Lệnh đặt mua/bán"""
    id: str
    user_id: int
    symbol: str
    side: OrderSide      # Mua hay Bán
    type: OrderType      # LO hay MP
    quantity: int        # Số lượng đặt ban đầu
    filled_quantity: int # Số lượng đã khớp thực tế
    price: float         # Giá đặt (với lệnh Limit)
    status: OrderStatus
    created_at: datetime
    updated_at: datetime