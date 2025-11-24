from dataclasses import dataclass
from datetime import datetime

@dataclass
class Trade:
    """Kết quả khớp lệnh (Match) thành công"""
    id: str
    buy_order_id: str    # ID lệnh mua gốc
    sell_order_id: str   # ID lệnh bán gốc
    symbol: str 
    price: float         # Giá khớp thực tế
    quantity: int        # Số lượng khớp
    total_value: float   # Tổng giá trị (price * quantity)
    commission: float    # Phí giao dịch
    executed_at: datetime 

@dataclass
class Portfolio:
    """Ví cổ phiếu - Lưu trữ số lượng cổ phiếu user đang nắm giữ"""
    user_id: int
    symbol: str          # Mã chứng khoán (VD: FPT)
    quantity: int        # Tổng số lượng đang sở hữu
    available_quantity: int # Số lượng có thể bán (trừ đi hàng chờ bán)
    average_price: float # Giá vốn trung bình
    updated_at: datetime